import os
import sqlite3
import threading
import time
import httpx
import pytesseract
import telebot
import requests
from telebot import types
from pdf2image import convert_from_path
from docx import Document
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=10000)


# 1. RÉCUPÉRATION SÉCURISÉE DES SECRETS
TOKEN_BOT = os.getenv("TOKEN_BOT") 
API_TOKEN = os.getenv('TOKEN_BOT')
ADMIN_ID_STR = os.getenv("ADMIN_ID") 
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None
USDT_ADDRESS = os.getenv('TOKEN_CRYPTO', 'UQBmDgki-lArmVLT_pxGktyqmm4zlfXf5iHoZcSgBDPVYPs9 ') 
OCR_SPACE_KEY = os.getenv('OCR_API_KEY', 'helloworld') # 'helloworld' est la clé par défaut

bot = telebot.TeleBot(API_TOKEN)


# --- 2. GESTION DE LA BASE DE DONNÉES (SQLITE) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions 
                      (tx_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)''')
    conn.commit()
    conn.close()

def get_credits(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id, credits) VALUES (?, ?)", (user_id, 1))
        conn.commit()
        conn.close()
        return 1

# --- 3. COMMANDES ET PAIEMENT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        f"👋 *Bienvenue sur HZLMaminirinaRHbot !*\n\n"
        f"Assistant OCR professionnel.\n"
        f"🎁 *Cadeau :* 1ère conversion GRATUITE (si < 10 Mo) !\n"
        f"💰 *Tarif :* 0.001 USDT par conversion.\n\n"
        f"Utilisez /buy pour acheter des crédits ou envoyez un document."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['buy'])
def buy_credits(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Payer 10 USDT (50 OCR)", callback_data="pay_10"))
    bot.send_message(message.chat.id, "Choisissez votre pack de crédits :", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "pay_10")
def process_payment(call):
    msg = (
        f"💳 *PAIEMENT USDT (TRC20)*\n\n"
        f"Envoyez **10 USDT** à :\n`{USDT_ADDRESS}`\n\n"
        f"Répondez avec le **TxID (Hash)** de la transaction."
    )
    sent_msg = bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    bot.register_next_step_handler(sent_msg, confirm_tx_to_admin)

def confirm_tx_to_admin(message):
    tx_id = message.text
    user_id = message.from_user.id
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO transactions VALUES (?, ?, 'pending')", (tx_id, user_id))
        conn.commit()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Valider", callback_data=f"approve_{tx_id}"),
                   types.InlineKeyboardButton("❌ Refuser", callback_data=f"reject_{tx_id}"))
        bot.send_message(ADMIN_ID, f"🔔 *Paiement reçu !*\nUser: {user_id}\nTxID: `{tx_id}`", reply_markup=markup, parse_mode='Markdown')
        bot.reply_to(message, "✅ TxID transmis à l'administrateur.")
    except sqlite3.IntegrityError:
        bot.reply_to(message, "⚠️ Ce TxID a déjà été soumis.")
    finally:
        conn.close()

# --- 4. TRAITEMENT OCR ET RESTRICTIONS ---
@bot.message_handler(content_types=['document', 'photo'])
def handle_docs(message):
    user_id = message.from_user.id
    credits = get_credits(user_id)

    if user_id == ADMIN_ID or credits > 0:
        bot.reply_to(message, "⏳ Analyse OCR en cours...")
        
        try:
            # --- LOGIQUE OCR ---
            file_info = bot.get_file(message.document.file_id if message.document else message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            payload = {
                'apikey': OCR_SPACE_KEY,
                'language': 'fre',
            }
            files = {'file': downloaded_file}
            response = requests.post('https://api.ocr.space/parse/image', files=files, data=payload)
            result = response.json()

            if result.get('ParsedResults'):
                extracted_text = result['ParsedResults'][0].get('ParsedText')
                bot.reply_to(message, f"✅ *Texte extrait :*\n\n{extracted_text}")
                
                # Déduction du crédit si succès (hors admin)
                if user_id != ADMIN_ID:
                    conn = sqlite3.connect('users.db')
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
            else:
                bot.reply_to(message, "⚠️ Erreur lors de la lecture du document.")
        except Exception as e:
            bot.reply_to(message, f"❌ Erreur technique : {str(e)}")
    else:
        bot.reply_to(message, "❌ Crédits épuisés ! Tapez /buy pour recharger.")

# --- 5. VALIDATION ADMIN ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def admin_validation(call):
    action, tx_id = call.data.split('_')
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM transactions WHERE tx_id = ?", (tx_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        if action == 'approve':
            cursor.execute("UPDATE users SET credits = credits + 50 WHERE user_id = ?", (user_id,))
            bot.send_message(user_id, "🎉 Paiement validé ! 50 crédits ajoutés.")
        else:
            bot.send_message(user_id, "❌ Paiement refusé.")
        cursor.execute("DELETE FROM transactions WHERE tx_id = ?", (tx_id,))
    
    conn.commit()
    conn.close()
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

if __name__ == "__main__":
    init_db()
     # On lance le serveur web sur le port 10000 dans un fil séparé
    Thread(target=run).start() 
    print("Bot is live...")
    bot.polling() 
