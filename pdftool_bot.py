import os
import logging
import asyncio
import zipfile
import shutil
import fitz  # PyMuPDF
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode

# Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
FORCE_SUB_CHANNEL_ID = -1002975585458
FORCE_SUB_CHANNEL_LINK = "https://t.me/freepyquizbot"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

class PDFStates(StatesGroup):
    waiting_for_pages_to_extract = State()
    waiting_for_pages_to_delete = State()
    waiting_for_pages_to_rotate = State()
    waiting_for_watermark_text = State()
    waiting_for_link_url = State()
    waiting_for_pdfs_to_merge = State()
    waiting_for_images_to_pdf = State()
    waiting_for_password_protect = State()
    waiting_for_password_unlock = State()

user_data = {}  # user_id -> dict

async def check_force_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL_ID, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logging.error(f"Force sub check error: {e}")
        return False

def force_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Channel", url=FORCE_SUB_CHANNEL_LINK)],
        [InlineKeyboardButton(text="I have joined", callback_data="check_sub")]
    ])

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Page Tools", callback_data="menu_pages"),
         InlineKeyboardButton(text="🔗 Links & Watermark", callback_data="menu_links")],
        [InlineKeyboardButton(text="🔒 Security", callback_data="menu_security"),
         InlineKeyboardButton(text="🔄 Conversions", callback_data="menu_conversions")],
        [InlineKeyboardButton(text="📦 Compress PDF", callback_data="pdf_compress"),
         InlineKeyboardButton(text="ℹ️ Metadata", callback_data="pdf_meta")]
    ])

def pages_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Extract Pages", callback_data="pdf_extract"),
         InlineKeyboardButton(text="Delete Pages", callback_data="pdf_delete")],
        [InlineKeyboardButton(text="Rotate Pages", callback_data="pdf_rotate"),
         InlineKeyboardButton(text="Split PDF", callback_data="pdf_split")],
        [InlineKeyboardButton(text="« Back to Main", callback_data="menu_main")]
    ])

def links_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Full Page Link", callback_data="pdf_addlink"),
         InlineKeyboardButton(text="Remove All Links", callback_data="pdf_remlinks")],
        [InlineKeyboardButton(text="Add Text Watermark", callback_data="pdf_watermark")],
        [InlineKeyboardButton(text="« Back to Main", callback_data="menu_main")]
    ])

def security_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Password", callback_data="pdf_protect"),
         InlineKeyboardButton(text="Remove Password", callback_data="pdf_unlock")],
        [InlineKeyboardButton(text="« Back to Main", callback_data="menu_main")]
    ])

def conversions_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PDF to Images", callback_data="pdf_to_img")],
        [InlineKeyboardButton(text="Extract Text", callback_data="pdf_to_txt")],
        [InlineKeyboardButton(text="« Back to Main", callback_data="menu_main")]
    ])

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    if not await check_force_sub(message.from_user.id):
        await message.answer("Hello! Please join our channel to use this bot.", reply_markup=force_sub_keyboard())
        return
    await message.answer(
        "Welcome to the **Ultimate PDF Utility Bot**!\n\n"
        "Send me a **PDF file** to access tools like Extract, Delete, Rotate, Split, Compress, Security, and more.\n\n"
        "Other Commands:\n"
        "/merge - Merge multiple PDFs\n"
        "/img2pdf - Convert images to PDF",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: CallbackQuery):
    if await check_force_sub(callback.from_user.id):
        await callback.message.edit_text("Thank you for joining! Send me a PDF file to get started.")
    else:
        await callback.answer("You haven't joined the channel yet!", show_alert=True)

@router.message(F.document)
async def handle_document(message: Message, state: FSMContext):
    if not await check_force_sub(message.from_user.id):
        await message.answer("Please join our channel first.", reply_markup=force_sub_keyboard())
        return
    
    current_state = await state.get_state()
    user_id = message.from_user.id
    
    if current_state == PDFStates.waiting_for_pdfs_to_merge.state:
        if message.document.mime_type != 'application/pdf':
            await message.answer("Please send a PDF file.")
            return
            
        data = await state.get_data()
        pdf_list = data.get('pdf_list', [])
        file_path = f"temp_merge_{user_id}_{len(pdf_list)}.pdf"
        await bot.download(message.document, destination=file_path)
        pdf_list.append(file_path)
        await state.update_data(pdf_list=pdf_list)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Merge Now", callback_data="merge_now")]])
        await message.answer(f"Received {len(pdf_list)} PDF(s). Send more or click 'Merge Now'.", reply_markup=kb)
        return
        
    if message.document.mime_type == 'application/pdf':
        msg = await message.answer("Downloading PDF...")
        file_path = f"temp_{user_id}.pdf"
        await bot.download(message.document, destination=file_path)
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['pdf_path'] = file_path
        
        # Check if password protected
        doc = fitz.open(file_path)
        if doc.needs_pass:
            await msg.edit_text(f"File: {message.document.file_name}\n\n🔒 This PDF is password protected. You must remove the password first using the Security menu.", reply_markup=security_keyboard())
        else:
            await msg.edit_text(f"File: {message.document.file_name}\nSelect a category:", reply_markup=main_menu_keyboard())
        doc.close()
    else:
        await message.answer("Please send a valid PDF file.")

@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    current_state = await state.get_state()
    user_id = message.from_user.id
    if current_state == PDFStates.waiting_for_images_to_pdf.state:
        data = await state.get_data()
        img_list = data.get('img_list', [])
        file_path = f"temp_img_{user_id}_{len(img_list)}.jpg"
        # Download highest quality photo
        await bot.download(message.photo[-1], destination=file_path)
        img_list.append(file_path)
        await state.update_data(img_list=img_list)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Create PDF", callback_data="create_img_pdf")]])
        await message.answer(f"Received {len(img_list)} Image(s). Send more or click 'Create PDF'.", reply_markup=kb)

@router.message(Command("merge"))
async def merge_command(message: Message, state: FSMContext):
    await state.set_state(PDFStates.waiting_for_pdfs_to_merge)
    await state.update_data(pdf_list=[])
    await message.answer("Merge Mode Activated!\nSend me the PDF files you want to merge one by one. Once done, click the 'Merge Now' button.")

@router.message(Command("img2pdf"))
async def img2pdf_command(message: Message, state: FSMContext):
    await state.set_state(PDFStates.waiting_for_images_to_pdf)
    await state.update_data(img_list=[])
    await message.answer("Image to PDF Mode Activated!\nSend me the images one by one. Once done, click the 'Create PDF' button.")

@router.callback_query(F.data.startswith("menu_"))
async def process_menus(callback: CallbackQuery):
    menu = callback.data.split("_")[1]
    if menu == "main":
        await callback.message.edit_text("Select a category:", reply_markup=main_menu_keyboard())
    elif menu == "pages":
        await callback.message.edit_text("📄 Page Tools:", reply_markup=pages_keyboard())
    elif menu == "links":
        await callback.message.edit_text("🔗 Links & Watermark:", reply_markup=links_keyboard())
    elif menu == "security":
        await callback.message.edit_text("🔒 Security Tools:", reply_markup=security_keyboard())
    elif menu == "conversions":
        await callback.message.edit_text("🔄 Conversions:", reply_markup=conversions_keyboard())

@router.callback_query(F.data == "merge_now")
async def process_merge(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pdf_list = data.get('pdf_list', [])
    if len(pdf_list) < 2:
        await callback.answer("You need at least 2 PDFs to merge.", show_alert=True)
        return
    
    await callback.message.edit_text("Merging PDFs...")
    try:
        merged_pdf = fitz.open()
        for pdf_file in pdf_list:
            if os.path.exists(pdf_file):
                with fitz.open(pdf_file) as doc:
                    merged_pdf.insert_pdf(doc)
        
        out_path = f"merged_{callback.from_user.id}.pdf"
        merged_pdf.save(out_path)
        merged_pdf.close()
        
        await callback.message.answer_document(FSInputFile(out_path), caption="Here is your merged PDF.")
        for p in pdf_list:
            if os.path.exists(p): os.remove(p)
        if os.path.exists(out_path): os.remove(out_path)
        await state.clear()
    except Exception as e:
        await callback.message.edit_text(f"An error occurred during merge: {e}")

@router.callback_query(F.data == "create_img_pdf")
async def process_img2pdf(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    img_list = data.get('img_list', [])
    if not img_list:
        await callback.answer("No images received.", show_alert=True)
        return
        
    await callback.message.edit_text("Creating PDF from images...")
    try:
        doc = fitz.open()
        for img_file in img_list:
            img = fitz.open(img_file)
            rect = img[0].rect
            pdfbytes = img.convert_to_pdf()
            img.close()
            imgPDF = fitz.open("pdf", pdfbytes)
            page = doc.new_page(width=rect.width, height=rect.height)
            page.show_pdf_page(rect, imgPDF, 0)
            imgPDF.close()
            
        out_path = f"images_{callback.from_user.id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await callback.message.answer_document(FSInputFile(out_path), caption="Here is your PDF.")
        for p in img_list:
            if os.path.exists(p): os.remove(p)
        if os.path.exists(out_path): os.remove(out_path)
        await state.clear()
    except Exception as e:
        await callback.message.edit_text(f"An error occurred: {e}")

@router.callback_query(F.data.startswith("pdf_"))
async def process_pdf_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if user_id not in user_data or 'pdf_path' not in user_data[user_id] or not os.path.exists(user_data[user_id]['pdf_path']):
        await callback.answer("PDF not found. Please send your PDF again.", show_alert=True)
        return

    pdf_path = user_data[user_id]['pdf_path']

    if action == "extract":
        await state.set_state(PDFStates.waiting_for_pages_to_extract)
        await callback.message.answer("Enter page numbers to extract (e.g., 1, 3, 5-7):")
    elif action == "delete":
        await state.set_state(PDFStates.waiting_for_pages_to_delete)
        await callback.message.answer("Enter page numbers to delete (e.g., 1, 3, 5-7):")
    elif action == "rotate":
        await state.set_state(PDFStates.waiting_for_pages_to_rotate)
        await callback.message.answer("Enter rotation angle for all pages (90, 180, or 270):")
    elif action == "watermark":
        await state.set_state(PDFStates.waiting_for_watermark_text)
        await callback.message.answer("Enter the text for the watermark:")
    elif action == "addlink":
        await state.set_state(PDFStates.waiting_for_link_url)
        await callback.message.answer("Enter the URL to add as a full page link:")
    elif action == "protect":
        await state.set_state(PDFStates.waiting_for_password_protect)
        await callback.message.answer("Enter the password to protect this PDF:")
    elif action == "unlock":
        await state.set_state(PDFStates.waiting_for_password_unlock)
        await callback.message.answer("Enter the current password to unlock this PDF:")
        
    # Immediate execution actions
    elif action == "split":
        await callback.message.edit_text("Splitting PDF... This might take a moment.")
        try:
            doc = fitz.open(pdf_path)
            for i in range(len(doc)):
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=i, to_page=i)
                out_path = f"split_{user_id}_page_{i+1}.pdf"
                new_doc.save(out_path)
                new_doc.close()
                await callback.message.answer_document(FSInputFile(out_path), caption=f"Page {i+1}")
                os.remove(out_path)
            doc.close()
            await callback.message.answer("Splitting complete.", reply_markup=main_menu_keyboard())
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")
            
    elif action == "remlinks":
        await callback.message.edit_text("Removing all links from the PDF...")
        try:
            doc = fitz.open(pdf_path)
            count = 0
            for page in doc:
                links = page.get_links()
                for link in links:
                    page.delete_link(link)
                    count += 1
            out_path = f"nolinks_{user_id}.pdf"
            doc.save(out_path)
            doc.close()
            await callback.message.answer_document(FSInputFile(out_path), caption=f"Removed {count} links from the PDF.")
            os.remove(out_path)
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")

    elif action == "compress":
        await callback.message.edit_text("Compressing PDF... This might take a while.")
        try:
            doc = fitz.open(pdf_path)
            out_path = f"compressed_{user_id}.pdf"
            doc.save(out_path, garbage=4, deflate=True)
            doc.close()
            
            orig_size = os.path.getsize(pdf_path) / (1024*1024)
            new_size = os.path.getsize(out_path) / (1024*1024)
            
            await callback.message.answer_document(FSInputFile(out_path), caption=f"Compression Complete!\nOriginal: {orig_size:.2f} MB\nCompressed: {new_size:.2f} MB")
            os.remove(out_path)
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")

    elif action == "to_img":
        await callback.message.edit_text("Converting PDF to Images... Please wait.")
        try:
            doc = fitz.open(pdf_path)
            temp_dir = f"temp_imgs_{user_id}"
            os.makedirs(temp_dir, exist_ok=True)
            for i in range(len(doc)):
                page = doc[i]
                pix = page.get_pixmap(dpi=150)
                pix.save(f"{temp_dir}/page_{i+1}.png")
            doc.close()
            
            zip_path = f"images_{user_id}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        zipf.write(os.path.join(root, file), arcname=file)
                        
            await callback.message.answer_document(FSInputFile(zip_path), caption="Here are your images (Zipped).")
            shutil.rmtree(temp_dir)
            os.remove(zip_path)
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")

    elif action == "to_txt":
        await callback.message.edit_text("Extracting Text from PDF...")
        try:
            doc = fitz.open(pdf_path)
            text_content = ""
            for i, page in enumerate(doc):
                text_content += f"--- Page {i+1} ---\n{page.get_text()}\n\n"
            doc.close()
            
            out_path = f"extracted_text_{user_id}.txt"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            await callback.message.answer_document(FSInputFile(out_path), caption="Here is the extracted text.")
            os.remove(out_path)
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")

    elif action == "meta":
        try:
            doc = fitz.open(pdf_path)
            meta = doc.metadata
            pages = len(doc)
            size = os.path.getsize(pdf_path) / (1024*1024)
            doc.close()
            
            meta_text = f"**Metadata**\n"
            meta_text += f"Pages: {pages}\n"
            meta_text += f"Size: {size:.2f} MB\n"
            for k, v in meta.items():
                if v:
                    meta_text += f"{k.capitalize()}: {v}\n"
            await callback.message.answer(meta_text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
        except Exception as e:
            await callback.message.answer(f"Error fetching metadata: {e}")

    await callback.answer()

def parse_page_numbers(text, max_pages):
    pages = set()
    parts = text.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                if 1 <= start <= end <= max_pages:
                    pages.update(range(start - 1, end))
            except ValueError:
                pass
        else:
            try:
                page = int(part)
                if 1 <= page <= max_pages:
                    pages.add(page - 1)
            except ValueError:
                pass
    return sorted(list(pages))

@router.message(PDFStates.waiting_for_pages_to_extract)
async def extract_pages_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()

    doc = fitz.open(pdf_path)
    pages = parse_page_numbers(message.text, len(doc))
    if not pages:
        await message.answer("Invalid page numbers.")
        return doc.close()
        
    try:
        new_doc = fitz.open()
        for p in pages: new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out_path = f"extracted_{user_id}.pdf"
        new_doc.save(out_path)
        new_doc.close(); doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Extracted pages.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_pages_to_delete)
async def delete_pages_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()

    doc = fitz.open(pdf_path)
    pages_to_delete = parse_page_numbers(message.text, len(doc))
    if not pages_to_delete:
        await message.answer("Invalid page numbers.")
        return doc.close()
        
    try:
        pages_to_keep = [i for i in range(len(doc)) if i not in pages_to_delete]
        if not pages_to_keep:
            await message.answer("You cannot delete all pages.")
            return doc.close()
            
        new_doc = fitz.open()
        for p in pages_to_keep: new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out_path = f"deleted_{user_id}.pdf"
        new_doc.save(out_path)
        new_doc.close(); doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="PDF with specified pages removed.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_pages_to_rotate)
async def rotate_pages_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()
    
    try:
        angle = int(message.text)
        if angle not in [90, 180, 270]: raise ValueError
    except ValueError:
        return await message.answer("Please enter a valid angle: 90, 180, or 270.")

    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            current_rot = page.rotation
            page.set_rotation((current_rot + angle) % 360)
            
        out_path = f"rotated_{user_id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption=f"PDF rotated by {angle} degrees.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_watermark_text)
async def watermark_text_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()
    
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            rect = page.rect
            pt = fitz.Point(rect.width / 4, rect.height / 2)
            page.insert_text(
                pt,
                message.text,
                fontsize=50,
                color=(0.5, 0.5, 0.5),
                morph=(pt, fitz.Matrix(-45)),
                fill_opacity=0.3
            )
        out_path = f"watermarked_{user_id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Watermarked PDF.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_link_url)
async def add_link_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()
    url = message.text.strip()
    if not url.startswith("http"): url = "https://" + url
        
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            rect = page.rect
            page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": url})
        out_path = f"linked_{user_id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="PDF with full page links.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_password_protect)
async def password_protect_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()
    pwd = message.text.strip()
        
    try:
        doc = fitz.open(pdf_path)
        out_path = f"protected_{user_id}.pdf"
        doc.save(out_path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=pwd, user_pw=pwd)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Password protected PDF.")
        os.remove(out_path)
        # Delete message to hide password
        await message.delete()
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_password_unlock)
async def password_unlock_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_data.get(user_id, {}).get('pdf_path')
    if not pdf_path: return await state.clear()
    pwd = message.text.strip()
        
    try:
        doc = fitz.open(pdf_path)
        if doc.authenticate(pwd):
            out_path = f"unlocked_{user_id}.pdf"
            doc.save(out_path, encryption=fitz.PDF_ENCRYPT_NONE)
            await message.answer_document(FSInputFile(out_path), caption="Unlocked PDF.")
            os.remove(out_path)
        else:
            await message.answer("Incorrect password.")
        doc.close()
        # Delete message to hide password
        await message.delete()
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

async def main():
    print("Bot is starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
