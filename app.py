import os
import re
import requests
import telebot
from telebot import types
from flask import Flask
from threading import Thread
from pymongo import MongoClient

# --- CONFIGURATION DU SERVEUR WEB ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and connected to MongoDB"

def run():
    app.run(host='0.0.0.0', port=10000)

# --- 1. RÉCUPÉRATION DES SECRETS ---
API_TOKEN = os.getenv('TOKEN_BOT')
ADMIN_ID_STR = os.getenv("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None
USDT_ADDRESS = os.getenv('TOKEN_CRYPTO', 'UQBmDgki-lArmVLT_pxGktyqmm4zlfXf5iHoZcSgBDPVYPs9') 
OCR_SPACE_KEY = os.getenv('OCR_API_KEY', 'helloworld')
MONGO_URI = os.getenv('MONGO_URI')

bot = telebot.TeleBot(API_TOKEN)

# --- 2. GESTION DE LA BASE DE DONNÉES (MONGODB) ---
# Connexion au cluster
client = MongoClient(MONGO_URI)
db = client['bot_ocr_db']  # Nom de la base
users_col = db['users']    # Collection des utilisateurs
tx_col = db['transactions'] # Collection des transactions

def get_credits(user_id):
    user = users_col.find_one({"user_id": user_id})
    if user:
        return user.get('credits', 0)
    else:
        # Création du nouvel utilisateur avec 1 crédit gratuit
        users_col.insert_one({"user_id": user_id, "credits": 1})
        return 1

# --- 3. COMMANDES ET PAIEMENT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        f"👋 *Bienvenue sur HZLMaminirinaRHbot !*\n\n"
        f"Assistant OCR professionnel.\n"
        f"🎁 *Cadeau :* 1ère conversion GRATUITE !\n"
        f"💰 *Pack :* 5 USDT = 50 Crédits.\n\n"
        f"Envoyez un fichier scanné/ un fichier non éditable ou tapez /help."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def send_help(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_buy = types.InlineKeyboardButton("💳 Acheter des crédits", callback_data="pay_5")
    btn_status = types.InlineKeyboardButton("📊 Mon Solde", callback_data="check_balance")
    btn_contact = types.InlineKeyboardButton("💬 Contacter l'Admin", url="https://t.me/HZLMaminirinaRH")
    markup.add(btn_buy, btn_status)
    markup.add(btn_contact)
    
    help_text = (
        "❓ *Besoin d'aide ?*\n\n"
        "1️⃣ **OCR** : Envoyez une photo nette.\n"
        "2️⃣ **Crédits** : 1 crédit = 1 conversion.\n"
        "3️⃣ **Paiement** : Envoyez le TxID après votre transfert."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def show_status(message):
    user_id = message.from_user.id
    credits = get_credits(user_id)
    bot.reply_to(message, f"📊 *État de votre compte :*\n\nID : `{user_id}`\nCrédits restants : *{credits}*", parse_mode='Markdown')

@bot.message_handler(commands=['buy'])
def buy_credits(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Payer 5 USDT (50 OCR)", callback_data="pay_5"))
    bot.send_message(message.chat.id, "🛒 Choisissez votre pack :", reply_markup=markup)

# --- GESTION DES CLICS BOUTONS ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "check_balance":
        credits = get_credits(call.from_user.id)
        bot.answer_callback_query(call.id, f"Vous avez {credits} crédit(s).", show_alert=True)
    
    elif call.data == "pay_5":
        msg = (
            f"💳 *PAIEMENT USDT (TRC20)*\n\n"
            f"Envoyez **5 USDT** à :\n`{USDT_ADDRESS}`\n\n"
            f"👉 Répondez à ce message avec le **TxID (Hash)**."
        )
        sent_msg = bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        bot.register_next_step_handler(sent_msg, confirm_tx_to_admin)
        
    elif call.data.startswith(('approve_', 'reject_')):
        admin_validation(call)

# --- PROTECTION ET VALIDATION DU TXID ---
def confirm_tx_to_admin(message):
    tx_id = message.text.strip() if message.text else ""
    
    if tx_id.startswith('/') or not tx_id:
        bot.reply_to(message, "❌ Opération annulée. Veuillez renvoyer le TxID correct via /buy.")
        return

    if len(tx_id) < 10:
        bot.reply_to(message, "⚠️ Ce TxID semble trop court. Veuillez vérifier.")
        return

    user_id = message.from_user.id
    
    # Vérifier si le TxID existe déjà dans MongoDB
    if tx_col.find_one({"tx_id": tx_id}):
        bot.reply_to(message, "⚠️ Ce TxID a déjà été soumis.")
        return

    # Insérer la transaction
    tx_col.insert_one({"tx_id": tx_id, "user_id": user_id, "status": "pending"})
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Valider", callback_data=f"approve_{tx_id}"),
               types.InlineKeyboardButton("❌ Refuser", callback_data=f"reject_{tx_id}"))
    
    bot.send_message(ADMIN_ID, f"🔔 *Nouveau Paiement !*\nUser: `{user_id}`\nTxID: `{tx_id}`", reply_markup=markup, parse_mode='Markdown')
    bot.reply_to(message, "✅ TxID transmis. Validation en cours par l'administrateur.")

# --- 4. TRAITEMENT OCR ---
@bot.message_handler(content_types=['document', 'photo'])
def handle_docs(message):
    user_id = message.from_user.id
    credits = get_credits(user_id)

    if user_id == ADMIN_ID or credits > 0:
        bot.reply_to(message, "⏳ Analyse OCR en cours...")
        try:
            file_id = message.document.file_id if message.document else message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
            
            payload = {
                'apikey': OCR_SPACE_KEY,
                'language': 'fre',
                'url': file_url
            }
            response = requests.post('https://api.ocr.space/parse/image', data=payload)
            result = response.json()

            if result.get('ParsedResults'):
                text = result['ParsedResults'][0].get('ParsedText')
                bot.reply_to(message, f"✅ *Texte extrait :*\n\n`{text}`", parse_mode='Markdown')
                
                if user_id != ADMIN_ID:
                    users_col.update_one({"user_id": user_id}, {"$inc": {"credits": -1}})
            else:
                bot.reply_to(message, "⚠️ Impossible de lire ce document. Assurez-vous qu'il contient du texte clair.")
        except Exception as e:
            bot.reply_to(message, f"❌ Erreur technique : {str(e)}")
    else:
        bot.reply_to(message, "❌ Crédits épuisés ! Tapez /buy pour recharger.")

# --- 5. LOGIQUE ADMIN ---
def admin_validation(call):
    data = call.data.split('_')
    action = data[0]
    tx_id = data[1]
    
    transaction = tx_col.find_one({"tx_id": tx_id})
    
    if transaction:
        user_id = transaction['user_id']
        if action == 'approve':
            users_col.update_one({"user_id": user_id}, {"$inc": {"credits": 50}})
            bot.send_message(user_id, "🎉 Félicitations ! Votre paiement a été validé. 50 crédits ont été ajoutés.")
            bot.answer_callback_query(call.id, "✅ Utilisateur crédité.")
        else:
            bot.send_message(user_id, "❌ Votre preuve de paiement a été refusée par l'administrateur.")
            bot.answer_callback_query(call.id, "❌ Paiement rejeté.")
        
        tx_col.delete_one({"tx_id": tx_id})
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

# --- LANCEMENT ---
if __name__ == "__main__":
    Thread(target=run).start()
    print("Bot is live with MongoDB...")
    bot.infinity_polling()
