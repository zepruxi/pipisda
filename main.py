import os
import telebot
from flask import Flask, request
import logging
import requests

# ============================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ============================================
TOKEN = os.environ.get('BOT_TOKEN')
BASE_URL = os.environ.get('BASE_URL')

if not TOKEN or not BASE_URL:
    raise ValueError("❌ BOT_TOKEN или BASE_URL не установлены!")

# ============================================
# СОЗДАЁМ ЭКЗЕМПЛЯРЫ (НА ВЕРХНЕМ УРОВНЕ!)
# ============================================
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)  # <-- ЭТО САМОЕ ГЛАВНОЕ!

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# ПРОСТЕЙШИЙ ОБРАБОТЧИК
# ============================================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "✅ БОТ РАБОТАЕТ!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.send_message(message.chat.id, f"Эхо: {message.text}")

# ============================================
# ВЕБХУК (НА ВЕРХНЕМ УРОВНЕ!)
# ============================================
@app.route('/webhook/main', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def home():
    return "Бот запущен", 200

@app.route('/health')
def health():
    return "OK", 200

# ============================================
# УСТАНОВКА ВЕБХУКА ПРИ ЗАПУСКЕ
# ============================================
webhook_url = f"{BASE_URL}/webhook/main"
requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", json={"url": webhook_url})
logger.info(f"✅ Вебхук установлен на {webhook_url}")

# ============================================
# БЛОК ЗАПУСКА (НУЖЕН ТОЛЬКО ДЛЯ ЛОКАЛЬНОГО ТЕСТА)
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
