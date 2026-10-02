# Telegram PDF Tools Bot

A complete Telegram bot for PDF operations, built with [aiogram 3.x](https://docs.aiogram.dev/) and [PyMuPDF](https://pymupdf.readthedocs.io/).

## Features

- **Force Subscribe Check**: Ensures users are subscribed to a specific channel before using the bot.
- **Extract Pages**: Extract specific pages or a range of pages from a PDF.
- **Delete Pages**: Remove specific pages from a PDF.
- **Rotate Pages**: Rotate all pages in a PDF by 90, 180, or 270 degrees.
- **Split PDF**: Split a PDF into multiple single-page PDFs.
- **Merge PDFs**: Combine multiple PDF files into one using the `/merge` command.
- **Text Watermark**: Add a diagonal gray text watermark to all pages.
- **Add Full Page Link**: Add an invisible, clickable URL link covering every page of the PDF.
- **Get Metadata**: View metadata information such as page count, author, and title.

## Requirements

- Python 3.8+
- `aiogram` >= 3.x
- `PyMuPDF` (fitz)

## Installation

1. Clone this repository or download the files.
2. Install the required dependencies:
   ```bash
   pip install aiogram PyMuPDF
   ```

## Configuration

Open `pdftool_bot.py` and update the following variables at the top of the file:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Your bot token from @BotFather
FORCE_SUB_CHANNEL_ID = -1002975585458  # The ID of your required channel
FORCE_SUB_CHANNEL_LINK = "https://t.me/freepyquizbot"  # Link to your channel
```

## Usage

Run the bot script:

```bash
python3 pdftool_bot.py
```

- Send a **PDF file** to the bot to access tools like Extract, Delete, Rotate, Split, Watermark, and Links.
- Send the `/merge` command to merge multiple PDFs into one.
