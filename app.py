import os
import threading
import pytesseract
from pdf2image import convert_from_path
from docx import Document
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
# Remarque : assurez-vous que aiocryptopay est bien installé via requirements.txt

# 1. RÉCUPÉRATION SÉCURISÉE DES SECRETS
TOKEN_BOT = os.getenv("TOKEN_BOT") 
TOKEN_CRYPTO = os.getenv("TOKEN_CRYPTO") 
ADMIN_ID_STR = os.getenv("ADMIN_ID") 
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None

# 2. CONFIGURATION DES DOSSIERS
DOWNLOAD_DIR = "/tmp" 
LOG_FILE = os.path.join(DOWNLOAD_DIR, "utilisateurs_ocr.txt")

# 3. SERVEUR FLASK (Indispensable pour Render Port 10000)
app = Flask(__name__)
@app.route('/')
def home(): return "Le Bot OCR est opérationnel sur Render !"

def run_flask():
    # Render exige le port 10000 pour le plan gratuit
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask, daemon=True).start()

# ... (Le reste de votre logique de fonctions reste inchangé) ...

# --- MODIFICATION DANS LE LANCEMENT FINAL ---
from telegram.request import HTTPXRequest

if __name__ == "__main__":
    td_request = HTTPXRequest(connect_timeout=60, read_timeout=60)
    application = ApplicationBuilder().token(TOKEN_BOT).request(td_request).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(CallbackQueryHandler(check_pay, pattern='^check_'))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("Bot en ligne...")
    application.run_polling(poll_interval=2.0)
