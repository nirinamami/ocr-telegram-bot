import os
import threading
import time
import httpx
import pytesseract
from pdf2image import convert_from_path
from docx import Document
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest

# 1. RÉCUPÉRATION SÉCURISÉE DES SECRETS
TOKEN_BOT = os.getenv("TOKEN_BOT") 
ADMIN_ID_STR = os.getenv("ADMIN_ID") 
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None

# 2. CONFIGURATION DES DOSSIERS
DOWNLOAD_DIR = "/tmp" 

# 3. SERVEUR FLASK (Indispensable pour Render Port 10000)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Le Bot OCR est opérationnel sur Render !"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# --- NOUVELLE FONCTION START DÉFINIE AVANT L'APPEL ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réponse à la commande /start"""
    await update.message.reply_text("Bonjour ! Je suis votre bot OCR. Envoyez-moi un PDF ou une image.")

# --- AUTRES FONCTIONS (STUBS) ---
# Assurez-vous d'ajouter ici vos fonctions handle_document et button_callback si vous en avez
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Document reçu, traitement en cours...")

# 4. SYSTÈME DE PING POUR MAINTENIR RENDER ÉVEILLÉ
def self_ping():
    # Remplacez l'URL par votre URL exacte affichée sur Render
    url = "https://ocr-telegram-bot-tss7.onrender.com/"
    while True:
        try:
            with httpx.Client() as client:
                client.get(url)
            print("Ping réussi pour maintenir Render éveillé")
        except Exception as e:
            print(f"Erreur lors du ping: {e}")
        time.sleep(900)

# LANCEMENT DES THREADS
threading.Thread(target=run_flask, daemon=True).start()
threading.Thread(target=self_ping, daemon=True).start()

# 5. LANCEMENT FINAL DU BOT
if __name__ == "__main__":
    if not TOKEN_BOT:
        print("Erreur : TOKEN_BOT non trouvé dans les variables d'environnement.")
    else:
        td_request = HTTPXRequest(connect_timeout=60, read_timeout=60)
        application = ApplicationBuilder().token(TOKEN_BOT).request(td_request).build()

        # AJOUT DES HANDLERS (La fonction 'start' est maintenant connue)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.Document.PDF, handle_document))

        print("Bot en ligne...")
        application.run_polling(poll_interval=2.0)
