import os
import sqlite3
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
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, conversion_count INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

def get_user_conversions(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT conversion_count FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_user_conversions(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, conversion_count) VALUES (?, (SELECT IFNULL(conversion_count, 0) + 1 FROM users WHERE user_id = ?))", (user_id, user_id))
    c.execute("INSERT OR IGNORE INTO users (user_id, conversion_count) VALUES (?, 1)", (user_id,))
    conn.commit()
    conn.close()
# 3. SERVEUR FLASK (Indispensable pour Render Port 10000)
app = Flask(__name__)
@app.route('/')
def home(): 
    return "Le Bot OCR est opérationnel sur Render !"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# --- NOUVELLE FONCTION START DÉFINIE AVANT L'APPEL ---
async def start(update, context):
    welcome_text = (
        "👋 **Bienvenue sur HZLMaminirinaRHbot !**\n\n"
        "Assistant OCR professionnel.\n"
        "🎁 **Cadeau** : 1ère conversion GRATUITE (si < 10 Mo) !\n"
        "💰 Tarif : 0.001 USDT.\n\n"
        "Envoyez un PDF pour commencer!!!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
# --- AUTRES FONCTIONS (STUBS) ---
# Assurez-vous d'ajouter ici vos fonctions handle_document et button_callback si vous en avez
async def handle_document(update, context):
    user_id = update.effective_user.id
    file = await update.message.document.get_file()
    file_size_mb = update.message.document.file_size / (1024 * 1024)
    
    # 1. Vérification Admin (Gratuité Totale)
    if str(user_id) == str(ADMIN_ID):
        await update.message.reply_text("✨ Mode Admin : Traitement gratuit illimité.")
        return await process_ocr(update, context) # Lance l'OCR directement

    # 2. Vérification de l'historique
    conversions = get_user_conversions(user_id)

    if conversions == 0:
        # Première fois : Vérifier la taille (Cadeau < 3 Mo)
        if file_size_mb <= 3:
            await update.message.reply_text("🎁 Première conversion gratuite (< 3 Mo) !")
            increment_user_conversions(user_id)
            return await process_ocr(update, context)
        else:
            await update.message.reply_text("⚠️ Votre premier fichier est > 3 Mo. Un paiement est requis.")
    
    # 3. Passage au payant (0.001 USDT)
    await update.message.reply_text("💰 Service payant : 0.001 USDT requis pour continuer.")
    # Ici, insérez votre logique d'appel à aiocryptopay
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
