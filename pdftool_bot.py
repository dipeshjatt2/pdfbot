import os
import logging
import asyncio
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

# FSM States
class PDFStates(StatesGroup):
    waiting_for_pages_to_extract = State()
    waiting_for_pages_to_delete = State()
    waiting_for_pages_to_rotate = State()
    waiting_for_watermark_text = State()
    waiting_for_link_url = State()
    waiting_for_pdfs_to_merge = State()

# In-memory store for active PDF paths
user_pdf_data = {}

async def check_force_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL_ID, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logging.error(f"Force sub check error: {e}")
        # If bot is not in channel or other error, you might want to return False
        return False

def force_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Channel", url=FORCE_SUB_CHANNEL_LINK)],
        [InlineKeyboardButton(text="I have joined", callback_data="check_sub")]
    ])

def pdf_options_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Extract Pages", callback_data="pdf_extract"),
            InlineKeyboardButton(text="Delete Pages", callback_data="pdf_delete")
        ],
        [
            InlineKeyboardButton(text="Rotate Pages", callback_data="pdf_rotate"),
            InlineKeyboardButton(text="Split PDF", callback_data="pdf_split")
        ],
        [
            InlineKeyboardButton(text="Add Text Watermark", callback_data="pdf_watermark"),
            InlineKeyboardButton(text="Add Full Page Link", callback_data="pdf_link")
        ],
        [
            InlineKeyboardButton(text="Get Metadata", callback_data="pdf_meta")
        ]
    ])

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    if not await check_force_sub(message.from_user.id):
        await message.answer(
            "Hello! Please join our channel to use this bot.",
            reply_markup=force_sub_keyboard()
        )
        return
    await message.answer(
        "Welcome to PDF Tools Bot! \n\n"
        "Send me a **PDF file** to access tools like Extract, Delete, Rotate, Split, Watermark, and Links.\n"
        "Or send /merge to merge multiple PDFs into one.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: CallbackQuery):
    if await check_force_sub(callback.from_user.id):
        await callback.message.edit_text("Thank you for joining! Send me a PDF file to get started, or send /merge to merge multiple PDFs.")
    else:
        await callback.answer("You haven't joined the channel yet! Please join first.", show_alert=True)

@router.message(F.document)
async def handle_document(message: Message, state: FSMContext):
    if not await check_force_sub(message.from_user.id):
        await message.answer("Please join our channel first.", reply_markup=force_sub_keyboard())
        return
    
    current_state = await state.get_state()
    if current_state == PDFStates.waiting_for_pdfs_to_merge.state:
        if message.document.mime_type != 'application/pdf':
            await message.answer("Please send a PDF file.")
            return
        
        data = await state.get_data()
        pdf_list = data.get('pdf_list', [])
        
        file_path = f"temp_merge_{message.from_user.id}_{len(pdf_list)}.pdf"
        await bot.download(message.document, destination=file_path)
        
        pdf_list.append(file_path)
        await state.update_data(pdf_list=pdf_list)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Merge Now", callback_data="merge_now")]])
        await message.answer(f"Received {len(pdf_list)} PDF(s). Send more or click 'Merge Now'.", reply_markup=kb)
        return
        
    if message.document.mime_type == 'application/pdf':
        msg = await message.answer("Downloading PDF...")
        file_path = f"temp_{message.from_user.id}.pdf"
        await bot.download(message.document, destination=file_path)
        user_pdf_data[message.from_user.id] = file_path
        await msg.edit_text(f"File: {message.document.file_name}\nSelect an action:", reply_markup=pdf_options_keyboard())
    else:
        await message.answer("Please send a valid PDF file.")

@router.message(Command("merge"))
async def merge_command(message: Message, state: FSMContext):
    if not await check_force_sub(message.from_user.id):
        await message.answer("Please join our channel first.", reply_markup=force_sub_keyboard())
        return
    await state.set_state(PDFStates.waiting_for_pdfs_to_merge)
    await state.update_data(pdf_list=[])
    await message.answer("Merge Mode Activated!\nSend me the PDF files you want to merge one by one. Once done, click the 'Merge Now' button.")

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
        
        # Cleanup
        for pdf_file in pdf_list:
            if os.path.exists(pdf_file):
                os.remove(pdf_file)
        if os.path.exists(out_path):
            os.remove(out_path)
            
        await state.clear()
    except Exception as e:
        await callback.message.edit_text(f"An error occurred during merge: {e}")

@router.callback_query(F.data.startswith("pdf_"))
async def process_pdf_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if user_id not in user_pdf_data or not os.path.exists(user_pdf_data[user_id]):
        await callback.answer("PDF not found. Please send your PDF again.", show_alert=True)
        return

    if action == "extract":
        await state.set_state(PDFStates.waiting_for_pages_to_extract)
        await callback.message.answer("Enter page numbers to extract (e.g., 1, 3, 5-7):")
    elif action == "delete":
        await state.set_state(PDFStates.waiting_for_pages_to_delete)
        await callback.message.answer("Enter page numbers to delete (e.g., 1, 3, 5-7):")
    elif action == "rotate":
        await state.set_state(PDFStates.waiting_for_pages_to_rotate)
        await callback.message.answer("Enter rotation angle for all pages (90, 180, or 270):")
    elif action == "split":
        await callback.message.edit_text("Splitting PDF... This might take a moment.")
        try:
            pdf_path = user_pdf_data[user_id]
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
            await callback.message.answer("Splitting complete.")
        except Exception as e:
            await callback.message.answer(f"An error occurred: {e}")
    elif action == "watermark":
        await state.set_state(PDFStates.waiting_for_watermark_text)
        await callback.message.answer("Enter the text for the watermark:")
    elif action == "link":
        await state.set_state(PDFStates.waiting_for_link_url)
        await callback.message.answer("Enter the URL to add as a full page link:")
    elif action == "meta":
        try:
            pdf_path = user_pdf_data[user_id]
            doc = fitz.open(pdf_path)
            meta = doc.metadata
            pages = len(doc)
            doc.close()
            
            meta_text = f"**Metadata**\n"
            meta_text += f"Pages: {pages}\n"
            for k, v in meta.items():
                if v:
                    meta_text += f"{k.capitalize()}: {v}\n"
            await callback.message.answer(meta_text, parse_mode=ParseMode.MARKDOWN)
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
    pdf_path = user_pdf_data.get(user_id)
    
    if not pdf_path or not os.path.exists(pdf_path):
        await message.answer("PDF not found. Please send it again.")
        await state.clear()
        return

    doc = fitz.open(pdf_path)
    pages = parse_page_numbers(message.text, len(doc))
    
    if not pages:
        await message.answer("Invalid page numbers. Please try again or send /start to cancel.")
        doc.close()
        return
        
    try:
        new_doc = fitz.open()
        for p in pages:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
        
        out_path = f"extracted_{user_id}.pdf"
        new_doc.save(out_path)
        new_doc.close()
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Here are your extracted pages.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_pages_to_delete)
async def delete_pages_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_pdf_data.get(user_id)
    
    if not pdf_path or not os.path.exists(pdf_path):
        await message.answer("PDF not found. Please send it again.")
        await state.clear()
        return

    doc = fitz.open(pdf_path)
    pages_to_delete = parse_page_numbers(message.text, len(doc))
    
    if not pages_to_delete:
        await message.answer("Invalid page numbers. Please try again or send /start to cancel.")
        doc.close()
        return
        
    try:
        pages_to_keep = [i for i in range(len(doc)) if i not in pages_to_delete]
        if not pages_to_keep:
            await message.answer("You cannot delete all pages.")
            doc.close()
            return
            
        new_doc = fitz.open()
        for p in pages_to_keep:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
            
        out_path = f"deleted_{user_id}.pdf"
        new_doc.save(out_path)
        new_doc.close()
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="PDF with specified pages removed.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_pages_to_rotate)
async def rotate_pages_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_pdf_data.get(user_id)
    
    try:
        angle = int(message.text)
        if angle not in [90, 180, 270]:
            raise ValueError
    except ValueError:
        await message.answer("Please enter a valid angle: 90, 180, or 270.")
        return

    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            page.set_rotation(page.rotation + angle)
            
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
    pdf_path = user_pdf_data.get(user_id)
    text = message.text
    
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            rect = page.rect
            # Add watermark diagonally across the center
            page.insert_text(
                fitz.Point(rect.width / 4, rect.height / 2),
                text,
                fontsize=50,
                color=(0.5, 0.5, 0.5), # Gray
                rotate=45,
                fill_opacity=0.3
            )
            
        out_path = f"watermarked_{user_id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Here is your watermarked PDF.")
        os.remove(out_path)
    except Exception as e:
        await message.answer(f"Error: {e}")
    await state.clear()

@router.message(PDFStates.waiting_for_link_url)
async def add_link_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pdf_path = user_pdf_data.get(user_id)
    url = message.text.strip()
    
    if not url.startswith("http"):
        url = "https://" + url
        
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            rect = page.rect
            page.insert_link({
                "kind": fitz.LINK_URI,
                "from": rect,
                "uri": url
            })
            
        out_path = f"linked_{user_id}.pdf"
        doc.save(out_path)
        doc.close()
        
        await message.answer_document(FSInputFile(out_path), caption="Here is your PDF with full page links added.")
        os.remove(out_path)
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
