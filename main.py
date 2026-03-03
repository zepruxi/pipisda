import os
import telebot
import time
import requests
from datetime import datetime
import pytz
from telebot import types
from flask import Flask, request
import threading
import json
import logging

# Получаем переменные окружения
TOKEN = os.environ.get('')
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения!")

ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID не установлен в переменных окружения!")

BASE_URL = os.environ.get('https://grinch-i4gw.onrender.com')
if not BASE_URL:
    raise ValueError("BASE_URL не установлен в переменных окружения!")

# Создаем экземпляр основного бота
bot = telebot.TeleBot(TOKEN)

# Flask приложение для вебхуков
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменная для хранения статуса работы
work_status = "остановлен"

# Словарь для хранения данных пользователей
users_data = {}

# Словарь для хранения зеркальных ботов {bot_token: {"owner_id": user_id, "bot_username": username, "status": "active"}}
mirror_bots = {}

# Словарь для хранения временных данных при создании бота
temp_bot_data = {}

# Список забаненных пользователей
banned_users = []

# Процент реферальных отчислений
REFERRAL_PERCENT = 5  # 5%

# Файлы для сохранения данных
DATA_FILE = "users_data.json"
MIRROR_BOTS_FILE = "mirror_bots.json"


# Загрузка данных из файлов
def load_data():
    global users_data, mirror_bots
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
                # Конвертируем строковые ключи обратно в int
                users_data = {int(k): v for k, v in users_data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки users_data: {e}")

    try:
        if os.path.exists(MIRROR_BOTS_FILE):
            with open(MIRROR_BOTS_FILE, 'r', encoding='utf-8') as f:
                mirror_bots = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки mirror_bots: {e}")


# Сохранение данных в файлы
def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения users_data: {e}")

    try:
        with open(MIRROR_BOTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(mirror_bots, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения mirror_bots: {e}")


# Загружаем данные при старте
load_data()


# Функция для получения курса доллара
def get_usd_rub_rate():
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=10)
        data = response.json()
        return data['rates']['RUB']
    except:
        return 77.41


# Функция для получения текущего времени по Москве
def get_moscow_time():
    tz = pytz.timezone('Europe/Moscow')
    return datetime.now(tz).strftime("%d.%m.%Y – %H:%M:%S")


# Функция для определения цены в зависимости от уровня
def get_price_by_level(level):
    if level >= 2:
        return 4.0
    return 3.5


# Функция для получения данных пользователя
def get_user_data(user_id):
    if str(user_id) not in users_data:
        users_data[str(user_id)] = {
            "balance": 0.0,
            "level": 1,
            "numbers": 0,
            "warns": 0,
            "banned": False,
            "total_earned": 0.0,
            "referrer": None,
            "referrals": [],
            "referral_earnings": 0.0,
            "numbers_history": [],
            "mirror_bots": [],
            "mirror_earned": 0.0,
            "mirror_turnover": 0.0
        }
        save_data()
    return users_data[str(user_id)]


# Функция для проверки и повышения уровня
def check_level_up(user_id):
    user = get_user_data(user_id)

    if user["level"] == 1 and user["numbers"] >= 15:
        user["level"] = 2
        save_data()
        return True, f"🎉 Поздравляем! Вы достигли 2 уровня! Теперь цена за номер: ${get_price_by_level(2)}"
    return False, ""


# Функция для проверки и применения бана
def check_and_apply_ban(user_id):
    user = get_user_data(user_id)
    if user["warns"] >= 5 and not user["banned"]:
        user["banned"] = True
        if user_id not in banned_users:
            banned_users.append(user_id)
        save_data()
        return True
    return False


# Функция для начисления реферальных бонусов
def add_referral_earnings(user_id, amount):
    user = get_user_data(user_id)
    if user["referrer"]:
        referrer_id = user["referrer"]
        referrer = get_user_data(referrer_id)
        if not referrer["banned"]:
            referral_bonus = amount * (REFERRAL_PERCENT / 100)
            referrer["balance"] += referral_bonus
            referrer["referral_earnings"] += referral_bonus
            referrer["total_earned"] += referral_bonus
            save_data()

            try:
                bot.send_message(
                    referrer_id,
                    f"👥 Реферальный бонус!\n"
                    f"Ваш реферал заработал ${amount}\n"
                    f"Вам начислено ${referral_bonus:.2f} (5%)"
                )
            except:
                pass


# Функция для добавления номера в историю
def add_number_to_history(user_id, price):
    user = get_user_data(user_id)
    moscow_time = get_moscow_time()

    history_entry = {
        "date": moscow_time,
        "price": price,
        "status": "✅ Принят"
    }
    user["numbers_history"].append(history_entry)

    if len(user["numbers_history"]) > 20:
        user["numbers_history"] = user["numbers_history"][-20:]
    save_data()


# Функция для создания главного меню
def get_main_menu_text(user_id):
    user = get_user_data(user_id)

    if user["banned"]:
        return f"""⛔ <b>ВЫ ЗАБАНЕНЫ</b> ⛔

Причина: превышение лимита варнов (5/5)
Для разблокировки обратитесь к администратору."""

    current_price = get_price_by_level(user["level"])
    moscow_time = get_moscow_time()
    usd_rate = get_usd_rub_rate()
    rubles = int(user["balance"] * usd_rate)

    level_text = "первый" if user['level'] == 1 else "второй"

    return f"""💰 <a href="https://t.me/GrinchMoneyBot">Grinch Money</a>: главное меню

<blockquote>╔ MAX ({current_price}$/0min)
╚ Статус работы: {work_status}
(оплата момент)</blockquote>

╔ Баланс: {user["balance"]}$ ({rubles}₽)
╠ Уровень: {level_text} ({user['numbers']} номеров)
╚ Варны: {user['warns']}/5 (5 варнов = бан)
({moscow_time})"""


# Функция для создания профиля пользователя
def get_profile_text(user_id):
    user = get_user_data(user_id)
    usd_rate = get_usd_rub_rate()

    balance_rub = int(user["balance"] * usd_rate)
    earned_rub = int(user["total_earned"] * usd_rate)
    referral_rub = int(user["referral_earnings"] * usd_rate)

    if user['level'] == 1:
        level_text = "первый"
        progress = f"{user['numbers']}/15"
    else:
        level_text = "второй"
        progress = "макс"

    return f"""💼 <a href="https://t.me/MoneyTeamTgBot">GrinchTeam</a>: профиль пользователя

╔ Баланс: {user["balance"]}$ ({balance_rub}₽)
╠ Уровень: {level_text} (след: {progress} номеров)
╠ Заработано: {user["total_earned"]}$ ({earned_rub}₽)
╚ С рефералов: {user["referral_earnings"]}$ ({referral_rub}₽)

MAX: {user["numbers"]} номеров"""


# Функция для создания текста истории номеров
def get_history_text(user_id):
    user = get_user_data(user_id)

    if not user["numbers_history"]:
        text = f"""📋 <b>История номеров</b>

ℹ️ На данный момент история пуста, но вы можете это исправить!

⚡️ Сдайте свой 🇷🇺 Max аккаунт в аренду (/menu –> сдать аккаунт)"""
    else:
        text = f"""📋 <b>История номеров</b>\n\n"""
        for i, entry in enumerate(reversed(user["numbers_history"][-10:]), 1):
            text += f"{i}. {entry['date']} | {entry['status']} | ${entry['price']}\n"

        if len(user["numbers_history"]) > 10:
            text += f"\n<i>Показаны последние 10 из {len(user['numbers_history'])} записей</i>"

    return text


# Функция для создания текста реферальной программы
def get_referral_text(user_id):
    user = get_user_data(user_id)
    bot_username = "MoneyTeamTgBot"
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    usd_rate = get_usd_rub_rate()
    referral_rub = int(user["referral_earnings"] * usd_rate)

    text = f"""👥 <b>Реферальная программа</b>

<blockquote>💕 Как это работает?
  — После того как пользователь зарегистрируется по вашей ссылке вы будете получать 5% от любого его дохода (Сдача Max, конкурс, реферальная программа и т.д.)</blockquote>

<b>Ваша реферальная ссылка:</b>
<code>{referral_link}</code>

📊 <b>Ваша статистика:</b>
👥 Приглашено: {len(user['referrals'])} чел.
💰 Заработано с рефералов: ${user["referral_earnings"]} ({referral_rub}₽)"""

    return text


# Функция для создания текста "Создать копию"
def get_copy_intro_text():
    return """🤖 <b>Добро пожаловать в создание зеркало-бота!</b>

👨‍💻 Мы даем вам возможность создать своего бота в которого вы можете звать людей, они будут зарабатывать и вы будете получать процент, а также дополнительные бонусы

😎 Вы ничего не делаете — мы работаем и выплачиваем за вас. Вам всего лишь нужно звать людей в своего бота и зарабатывать на этом!

1️⃣ Функционал бота будет точно таким же как и в этом.
2️⃣ Мы не показываем ссылки на наши проекты вашим пользователям.
3️⃣ Вы можете настраивать дизайн, цены, проценты самостоятельно в настройках вашего бота.

🚀 Вы готовы перейти на новый уровень заработка? Если да, то вперед!"""


# Функция для создания текста меню зеркальных ботов
def get_mirror_menu_text(user_id):
    user = get_user_data(user_id)
    usd_rate = get_usd_rub_rate()

    earned_rub = int(user["mirror_earned"] * usd_rate)
    turnover_rub = int(user["mirror_turnover"] * usd_rate)

    return f"""🪞 <b>Зеркальные боты: меню</b>

💰 Заработано — ${user["mirror_earned"]} ({earned_rub}₽)
⚖️ Оборот — ${user["mirror_turnover"]} ({turnover_rub}₽)
🤖 Ботов — {len(user['mirror_bots'])} штук"""


# Функция для создания текста создания зеркала
def get_create_mirror_text():
    return """👨‍💻 <b>Отправьте токен от вашего бота</b>

<blockquote>❓ Как его получить:
1. Перейдите в t.me/BotFather
2. Напишите /start
3. Введите название для бота (в будущем его можно будет изменить)
4. Придумайте и введите @username для своего бота
  * У юзернейма на конце должна быть приставка «bot»
  * Юзернейм должен быть уникальным
  * Примеры: @GroupHelpBot, @grouphelp_bot
5. Отправьте мне токен который вы получили от BotFather (пример: 21871418:bai71bsi-jasosb)</blockquote>"""


# Создание инлайн клавиатуры для главного меню
def get_main_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    profile_button = types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile")
    keyboard.add(profile_button)
    return keyboard


# Клавиатура для профиля
def get_profile_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    history_button = types.InlineKeyboardButton(text="📋 История номеров", callback_data="history")
    ref_button = types.InlineKeyboardButton(text="👥 Реф. система", callback_data="referral")
    copy_button = types.InlineKeyboardButton(text="📋 Создать копию", callback_data="copy_intro")

    keyboard.add(history_button)
    keyboard.add(ref_button)
    keyboard.add(copy_button)

    return keyboard


# Клавиатура для истории номеров
def get_history_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_button = types.InlineKeyboardButton(text="◀ Назад в профиль", callback_data="back_to_profile")
    keyboard.add(back_button)
    return keyboard


# Клавиатура для реферальной системы
def get_referral_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    bot_username = "MoneyTeamTgBot"
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    back_button = types.InlineKeyboardButton(text="◀ Назад", callback_data="back_to_profile")
    copy_button = types.InlineKeyboardButton(text="📋 Копировать", callback_data=f"copy_{referral_link}")

    keyboard.add(back_button, copy_button)

    return keyboard


# Клавиатура для введения в создание копии
def get_copy_intro_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    back_button = types.InlineKeyboardButton(text="◀ Назад", callback_data="back_to_profile")
    next_button = types.InlineKeyboardButton(text="Далее ▶", callback_data="mirror_menu")

    keyboard.add(back_button, next_button)

    return keyboard


# Клавиатура для меню зеркальных ботов
def get_mirror_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    create_button = types.InlineKeyboardButton(text="➕ Создать зеркало", callback_data="create_mirror")
    back_button = types.InlineKeyboardButton(text="◀ Назад в профиль", callback_data="back_to_profile")

    keyboard.add(create_button)
    keyboard.add(back_button)

    return keyboard


# Клавиатура для создания зеркала (только назад)
def get_create_mirror_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_button = types.InlineKeyboardButton(text="◀ Назад", callback_data="mirror_menu")
    keyboard.add(back_button)
    return keyboard


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    args = message.text.split()

    # Проверяем, есть ли реферальный параметр
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            if referrer_id != user_id and str(referrer_id) in users_data:
                user_data = get_user_data(user_id)
                if user_data["referrer"] is None:
                    user_data["referrer"] = referrer_id
                    referrer = get_user_data(referrer_id)
                    referrer["referrals"].append(user_id)
                    save_data()

                    try:
                        bot.send_message(
                            referrer_id,
                            f"🎉 У вас новый реферал!\n"
                            f"Пользователь {user_id} присоединился по вашей ссылке"
                        )
                    except:
                        pass
        except:
            pass

    get_user_data(user_id)

    bot.send_message(
        user_id,
        get_main_menu_text(user_id),
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=get_main_keyboard()
    )


# Обработчик инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    user = get_user_data(user_id)

    if user["banned"]:
        bot.answer_callback_query(call.id, "⛔ Вы забанены!", show_alert=True)
        return

    if call.data == "profile":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_profile_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_profile_keyboard()
        )

    elif call.data == "history":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_history_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_history_keyboard()
        )

    elif call.data == "referral":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_referral_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_referral_keyboard(user_id)
        )

    elif call.data == "copy_intro":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_copy_intro_text(),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_copy_intro_keyboard()
        )

    elif call.data == "mirror_menu":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_mirror_menu_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_mirror_menu_keyboard()
        )

    elif call.data == "create_mirror":
        # Сохраняем состояние ожидания токена
        temp_bot_data[user_id] = {"state": "waiting_token"}

        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_create_mirror_text(),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_create_mirror_keyboard()
        )

    elif call.data == "back_to_main":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_main_menu_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_main_keyboard()
        )

    elif call.data == "back_to_profile":
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=get_profile_text(user_id),
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=get_profile_keyboard()
        )

    elif call.data.startswith("copy_"):
        text_to_copy = call.data[5:]
        bot.answer_callback_query(
            call.id,
            text=f"📋 Скопировано: {text_to_copy}",
            show_alert=True
        )


# Обработчик текстовых сообщений для ожидания токена
@bot.message_handler(func=lambda message: message.chat.id != ADMIN_ID and
                                          message.chat.id in temp_bot_data and
                                          temp_bot_data[message.chat.id]["state"] == "waiting_token")
def handle_token(message):
    user_id = message.chat.id
    token = message.text.strip()

    # Простая валидация токена
    if len(token) < 30 or ':' not in token:
        bot.reply_to(message, "❌ Неверный формат токена. Попробуйте еще раз.")
        return

    try:
        # Проверяем токен, пытаясь получить информацию о боте
        test_bot = telebot.TeleBot(token)
        me = test_bot.get_me()

        # Сохраняем зеркальный бот
        mirror_bots[token] = {
            "owner_id": user_id,
            "bot_username": me.username,
            "bot_name": me.first_name,
            "status": "active",
            "created_at": get_moscow_time(),
            "stats": {
                "users": 0,
                "total_earned": 0.0,
                "owner_earned": 0.0
            }
        }

        # Добавляем в список ботов пользователя
        user = get_user_data(user_id)
        user["mirror_bots"].append(token)
        save_data()

        # Устанавливаем вебхук
        webhook_url = f"{BASE_URL}/webhook/{token}"
        test_bot.remove_webhook()
        test_bot.set_webhook(url=webhook_url)

        bot.reply_to(
            message,
            f"✅ Зеркальный бот @{me.username} успешно создан!\n\n"
            f"Теперь все заработанные средства в этом боте будут приносить вам процент."
        )

        # Удаляем временные данные
        del temp_bot_data[user_id]

        # Отправляем меню зеркальных ботов
        bot.send_message(
            user_id,
            get_mirror_menu_text(user_id),
            parse_mode='HTML',
            reply_markup=get_mirror_menu_keyboard()
        )

    except Exception as e:
        logger.error(f"Ошибка создания зеркального бота: {e}")
        bot.reply_to(
            message,
            "❌ Не удалось создать зеркального бота. Проверьте правильность токена."
        )


# Обработчик для администратора
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID)
def admin_commands(message):
    global work_status
    text = message.text.lower()

    if text == 'включен':
        work_status = "включен"
        bot.reply_to(message, f"✅ Статус изменен на: {work_status}")

    elif text == 'остановлен':
        work_status = "остановлен"
        bot.reply_to(message, f"✅ Статус изменен на: {work_status}")

    elif text.startswith('баланс '):
        try:
            parts = text.split()
            target_user = int(parts[1])
            amount = float(parts[2])

            user = get_user_data(target_user)
            if not user["banned"]:
                user["balance"] += amount
                user["total_earned"] += amount

                add_referral_earnings(target_user, amount)
                save_data()

                bot.reply_to(message, f"✅ Баланс пользователя {target_user} пополнен на ${amount}")

                try:
                    bot.send_message(
                        target_user,
                        f"💰 Ваш баланс пополнен на ${amount}!\n"
                        f"Текущий баланс: ${user['balance']}"
                    )
                except:
                    bot.reply_to(message, "⚠️ Не удалось уведомить пользователя")
            else:
                bot.reply_to(message, "❌ Пользователь забанен")
        except:
            bot.reply_to(message, "❌ Неверный формат. Используйте: баланс [user_id] [сумма]")

    elif text.startswith('номер '):
        try:
            parts = text.split()
            target_user = int(parts[1])

            user = get_user_data(target_user)
            if not user["banned"]:
                user["numbers"] += 1

                price = get_price_by_level(user["level"])
                user["balance"] += price
                user["total_earned"] += price

                add_number_to_history(target_user, price)
                add_referral_earnings(target_user, price)

                leveled_up, level_msg = check_level_up(target_user)
                save_data()

                bot.reply_to(message, f"✅ Номер засчитан пользователю {target_user}\n"
                                      f"Начислено: ${price}\n"
                                      f"Всего номеров: {user['numbers']}")

                try:
                    notification = f"✅ Ваш номер принят!\n💰 Начислено: ${price}\n"
                    notification += f"📊 Всего номеров: {user['numbers']}\n"
                    notification += f"💰 Баланс: ${user['balance']}"

                    if leveled_up:
                        notification += f"\n\n{level_msg}"

                    bot.send_message(target_user, notification)
                except:
                    bot.reply_to(message, "⚠️ Не удалось уведомить пользователя")
            else:
                bot.reply_to(message, "❌ Пользователь забанен")
        except:
            bot.reply_to(message, "❌ Неверный формат. Используйте: номер [user_id]")

    elif text.startswith('варн '):
        try:
            parts = text.split()
            target_user = int(parts[1])

            user = get_user_data(target_user)
            if not user["banned"]:
                user["warns"] += 1
                warns = user["warns"]

                bot.reply_to(message, f"⚠️ Варн выдан пользователю {target_user}\n"
                                      f"Варны: {warns}/5")

                banned = check_and_apply_ban(target_user)
                save_data()

                try:
                    if banned:
                        warn_msg = f"⚠️ Вам выдан варн!\nВарны: {warns}/5\n\n"
                        warn_msg += "🔨 ВЫ ЗАБАНЕНЫ за превышение лимита варнов (5/5)!\n"
                        warn_msg += "Для разблокировки обратитесь к администратору."
                        bot.send_message(target_user, warn_msg)

                        bot.send_message(
                            ADMIN_ID,
                            f"🔨 Пользователь {target_user} автоматически забанен (5/5 варнов)"
                        )
                    else:
                        bot.send_message(
                            target_user,
                            f"⚠️ Вам выдан варн!\nВарны: {warns}/5"
                        )
                except:
                    bot.reply_to(message, "⚠️ Не удалось уведомить пользователя")
            else:
                bot.reply_to(message, "❌ Пользователь не найден или уже забанен")
        except:
            bot.reply_to(message, "❌ Неверный формат. Используйте: варн [user_id]")

    elif text.startswith('разбан '):
        try:
            parts = text.split()
            target_user = int(parts[1])

            user = get_user_data(target_user)
            if user["banned"]:
                user["banned"] = False
                user["warns"] = 0

                if target_user in banned_users:
                    banned_users.remove(target_user)
                save_data()

                bot.reply_to(message, f"✅ Пользователь {target_user} разбанен")

                try:
                    bot.send_message(
                        target_user,
                        "✅ Вы были разбанены!\n"
                        "Варны сброшены. Пожалуйста, соблюдайте правила в дальнейшем."
                    )
                except:
                    pass
            else:
                bot.reply_to(message, "❌ Пользователь не найден или не забанен")
        except:
            bot.reply_to(message, "❌ Неверный формат. Используйте: разбан [user_id]")

    elif text == 'забаненные':
        if banned_users:
            users_list = "\n".join([f"• {user_id}" for user_id in banned_users])
            bot.reply_to(message, f"📋 Забаненные пользователи:\n{users_list}")
        else:
            bot.reply_to(message, "✅ Нет забаненных пользователей")

    elif text == 'зеркальные боты':
        total_bots = len(mirror_bots)
        active_bots = sum(1 for b in mirror_bots.values() if b["status"] == "active")

        stats = f"📊 Статистика зеркальных ботов:\n"
        stats += f"🤖 Всего ботов: {total_bots}\n"
        stats += f"✅ Активных: {active_bots}\n\n"

        for token, data in list(mirror_bots.items())[:10]:
            stats += f"• @{data['bot_username']} - владелец: {data['owner_id']}\n"

        bot.reply_to(message, stats)

    elif text == 'статистика':
        total_users = len(users_data)
        active_users = sum(1 for u in users_data.values() if not u["banned"])
        total_numbers = sum(u["numbers"] for u in users_data.values())
        total_balance = sum(u["balance"] for u in users_data.values())
        total_earned = sum(u["total_earned"] for u in users_data.values())
        total_referral = sum(u["referral_earnings"] for u in users_data.values())
        total_banned = len(banned_users)
        total_referrals = sum(len(u["referrals"]) for u in users_data.values())
        total_mirror_bots = sum(len(u["mirror_bots"]) for u in users_data.values())
        total_mirror_earned = sum(u["mirror_earned"] for u in users_data.values())

        level_1_users = sum(1 for u in users_data.values() if u["level"] == 1 and not u["banned"])
        level_2_users = sum(1 for u in users_data.values() if u["level"] == 2 and not u["banned"])

        stats = f"📊 Статистика бота:\n"
        stats += f"👥 Всего пользователей: {total_users}\n"
        stats += f"✅ Активных: {active_users}\n"
        stats += f"🔨 Забанено: {total_banned}\n"
        stats += f"📊 Уровень 1: {level_1_users} пользователей\n"
        stats += f"📊 Уровень 2: {level_2_users} пользователей\n"
        stats += f"👥 Всего рефералов: {total_referrals}\n"
        stats += f"🤖 Зеркальных ботов: {total_mirror_bots}\n"
        stats += f"📞 Всего номеров: {total_numbers}\n"
        stats += f"💰 Текущий баланс: ${total_balance}\n"
        stats += f"💵 Всего заработано: ${total_earned}\n"
        stats += f"👥 Реферальные выплаты: ${total_referral}\n"
        stats += f"🪞 Заработано с зеркал: ${total_mirror_earned}\n"
        stats += f"⚡ Статус работы: {work_status}"

        bot.reply_to(message, stats)

    else:
        bot.reply_to(message, "Доступные команды:\n"
                              "'включен' / 'остановлен' - статус работы\n"
                              "'баланс [user_id] [сумма]' - пополнить баланс\n"
                              "'номер [user_id]' - засчитать номер\n"
                              "'варн [user_id]' - выдать варн\n"
                              "'разбан [user_id]' - разбанить пользователя\n"
                              "'забаненные' - список забаненных\n"
                              "'зеркальные боты' - список зеркальных ботов\n"
                              "'статистика' - общая статистика")


# Обработчик для обычных пользователей (не в режиме ожидания токена)
@bot.message_handler(func=lambda message: message.chat.id != ADMIN_ID and
                                          (message.chat.id not in temp_bot_data or
                                           temp_bot_data[message.chat.id]["state"] != "waiting_token"))
def echo_all(message):
    user_id = message.chat.id
    bot.send_message(
        user_id,
        get_main_menu_text(user_id),
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=get_main_keyboard()
    )


# Flask routes для вебхуков
@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    return "OK", 200


@app.route(f'/webhook/<token>', methods=['POST'])
def webhook_handler(token):
    """Обработчик вебхуков для зеркальных ботов"""
    if token not in mirror_bots:
        return "Bot not found", 404

    bot_data = mirror_bots[token]

    # Проверяем, активен ли бот
    if bot_data["status"] != "active":
        return "Bot is not active", 403

    try:
        # Получаем обновление от Telegram
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))

        # Создаем экземпляр бота
        mirror_bot = telebot.TeleBot(token)

        # Здесь будет логика обработки команд зеркального бота
        if update.message and update.message.text == '/start':
            owner_id = bot_data["owner_id"]
            owner = get_user_data(owner_id)

            welcome_text = f"""🤖 Добро пожаловать в зеркальный бот!

Этот бот создан пользователем {owner_id}
Функционал полностью аналогичен основному боту.

Начните зарабатывать прямо сейчас!"""

            mirror_bot.send_message(update.message.chat.id, welcome_text)

        return "OK", 200

    except Exception as e:
        logger.error(f"Ошибка в вебхуке для токена {token}: {e}")
        return "Error", 500


# Функция для установки вебхука основного бота
def setup_main_webhook():
    """Устанавливает вебхук для основного бота"""
    try:
        webhook_url = f"{BASE_URL}/webhook/main"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен для основного бота: {webhook_url}")
    except Exception as e:
        logger.error(f"Ошибка установки вебхука для основного бота: {e}")


# Функция для проверки и переустановки вебхуков для зеркальных ботов
def setup_mirror_webhooks():
    """Переустанавливает вебхуки для всех зеркальных ботов при запуске"""
    for token, bot_data in mirror_bots.items():
        if bot_data["status"] == "active":
            try:
                webhook_url = f"{BASE_URL}/webhook/{token}"
                mirror_bot = telebot.TeleBot(token)
                mirror_bot.remove_webhook()
                mirror_bot.set_webhook(url=webhook_url)
                logger.info(f"Webhook установлен для @{bot_data['bot_username']}")
            except Exception as e:
                logger.error(f"Ошибка установки вебхука для токена {token}: {e}")
                bot_data["status"] = "error"


# Запуск приложения
if __name__ == '__main__':
    print("Бот запущен и готов к работе...")
    print(f"ID администратора: {ADMIN_ID}")
    print(f"Базовый URL: {BASE_URL}")
    print("Нажмите Ctrl+C для остановки")

    # Устанавливаем вебхук для основного бота
    setup_main_webhook()

    # Устанавливаем вебхуки для существующих зеркальных ботов
    setup_mirror_webhooks()

    # Получаем порт из переменных окружения Render
    port = int(os.environ.get('PORT', 5000))

    # Запускаем Flask приложение
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # Этот блок выполняется при запуске через gunicorn
    # Устанавливаем вебхуки при инициализации
    setup_main_webhook()
    setup_mirror_webhooks()