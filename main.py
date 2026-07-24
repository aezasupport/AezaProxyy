import subprocess
import sys
def install_dependencies():
    required = ['aiogram', 'aiohttp', 'aiosqlite', 'python-dotenv']
    missing = []
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    if missing:
        print(f"📦 Устанавливаю: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
install_dependencies()

import os
import json
import asyncio
import logging
import aiohttp
import aiosqlite
import time
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.sqlite import SqliteStorage  # ✅ ИСПРАВЛЕНО: SQLite вместо Memory
from datetime import datetime, timedelta

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WG_PANEL_URL = os.getenv("WG_PANEL_URL", "http://89.208.104.215:51821")
WG_PASSWORD = os.getenv("WG_PASSWORD", "admin123")
ADMIN_ID = int(os.getenv("ADMIN_ID", 8753184165))

DEFAULT_CONFIG = {
    "tariffs": {
        "1_month": {"name": "1 месяц", "stars": 150, "days": 30},
        "3_months": {"name": "3 месяца", "stars": 400, "days": 90},
        "6_months": {"name": "6 месяцев", "stars": 700, "days": 180},
    },
    "welcome_text": " <b>TRUST-VPN - анонимность превыше всего!</b>\n\n🔥 Наши преимущества:\n- Подписка до 5-ти устройств\n- Смена локаций\n- Высокая скорость\n- Отсутствует реклама\n- Поддержка Android, iOS, Windows, MacOS, AndroidTV, Linux\n\n 📢 Подписывайтесь на наш канал!\n🎉 Получи пробную подписку VPN на 3 дня абсолютно бесплатно!",
    "purchase_success_text": "✅ <b>Оплата прошла успешно!</b>\n\n Тариф '{tariff_name}' активирован\nДействует до: {expiry_date}\n\n📥 Скачайте конфигурацию ниже",
    "help_text": "📚 <b>Как пользоваться:</b>\n\n1. Выберите тариф в разделе 'Купить VPN'\n2. Оплатите подписку\n3. Скачайте файл конфигурации\n4. Установите приложение WireGuard\n5. Импортируйте файл в приложение\n6. Подключайтесь!\n\nВопросы: @nocaponeNGG",
    "referral_text": "👥 <b>Приглашай друзей и получай бонусы!</b>\n\n <b>Ты получаешь:</b> {bonus} дней за каждого друга\n🎁 <b>Друг получает:</b> бонус при первой покупке\n\n <b>Твоя ссылка:</b>\n<code>{referral_link}</code>\n\nНажми «Поделиться» чтобы отправить ссылку другу!",
    "referral_bonus_days": 3,
    "mandatory_channels": [],
    "trial_days": 3,
    "support_username": "nocaponeNGG"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
router = Router()

# ================= FSM STATES =================
class PurchaseStates(StatesGroup):
    selecting_tariff = State()

class BroadcastStates(StatesGroup):
    waiting_message = State()

class AdminEditStates(StatesGroup):
    editing_price_1month = State()
    editing_price_3months = State()
    editing_price_6months = State()
    editing_days_1month = State()
    editing_days_3months = State()
    editing_days_6months = State()
    editing_welcome_text = State()
    editing_purchase_text = State()
    editing_help_text = State()
    editing_referral_bonus = State()
    editing_referral_text = State()
    editing_trial_days = State()
    editing_support_username = State()
    creating_promo = State()
    editing_promo_days = State()
    editing_promo_balance = State()
    editing_promo_uses = State()

class AdminChannelStates(StatesGroup):
    waiting_channel = State()

# ================= БАЗА ДАННЫХ - НАСТРОЙКИ =================
async def get_setting(key: str, default=None):
    """Получить настройку из БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except:
                    return row['value']
            return default if default is not None else DEFAULT_CONFIG.get(key)
    except Exception as e:
        logging.error(f"Ошибка get_setting: {e}")
        return DEFAULT_CONFIG.get(key, default)

async def set_setting(key: str, value):
    """Сохранить настройку в БД"""
    try:
        logging.info(f"Попытка сохранить настройку {key}")
        async with aiosqlite.connect("bot.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value) if isinstance(value, (dict, list)) else str(value))
            )
            await db.commit()
            logging.info(f"✅ Настройка {key} сохранена в БД")
            return True
    except Exception as e:
        logging.error(f"❌ Ошибка set_setting: {e}")
        return False

async def get_all_tariffs():
    """Получить все тарифы из БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tariffs")
            rows = await cursor.fetchall()
            return {row['key']: {"name": row['name'], "stars": row['stars'], "days": row['days']} for row in rows}
    except Exception as e:
        logging.error(f"Ошибка get_all_tariffs: {e}")
        return DEFAULT_CONFIG['tariffs']

async def update_tariff_db(key: str, **kwargs):
    """Обновить тариф в БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            for field, value in kwargs.items():
                await db.execute(f"UPDATE tariffs SET {field} = ? WHERE key = ?", (value, key))
            await db.commit()
            logging.info(f"✅ Тариф {key} обновлен: {kwargs}")
            return True
    except Exception as e:
        logging.error(f" Ошибка update_tariff_db: {e}")
        return False

async def get_mandatory_channels_db():
    """Получить каналы из БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM mandatory_channels")
            rows = await cursor.fetchall()
            return [{"chat_id": row['chat_id'], "username": row['username']} for row in rows]
    except Exception as e:
        logging.error(f"Ошибка get_mandatory_channels_db: {e}")
        return []

async def add_channel_db(chat_id: int, username: str):
    """Добавить канал в БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            await db.execute(
                "INSERT OR IGNORE INTO mandatory_channels (chat_id, username) VALUES (?, ?)",
                (chat_id, username)
            )
            await db.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка add_channel_db: {e}")
        return False

async def remove_channel_db(chat_id: int):
    """Удалить канал из БД"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            await db.execute("DELETE FROM mandatory_channels WHERE chat_id = ?", (chat_id,))
            await db.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка remove_channel_db: {e}")
        return False

# ================= ИНИЦИАЛИЗАЦИЯ БД =================
async def init_db():
    async with aiosqlite.connect("bot.db") as db:
        # Таблица пользователей
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            wg_client_name TEXT,
            wg_client_id TEXT,
            subscription_start TEXT,
            subscription_end TEXT,
            is_active INTEGER DEFAULT 0,
            trial_used INTEGER DEFAULT 0,
            referral_code TEXT,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0
        )
        """)
        
        # Таблица настроек
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        
        # Таблица тарифов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tariffs (
            key TEXT PRIMARY KEY,
            name TEXT,
            stars INTEGER,
            days INTEGER
        )
        """)
        
        # Таблица каналов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS mandatory_channels (
            chat_id INTEGER PRIMARY KEY,
            username TEXT
        )
        """)
        
        # Таблица промокодов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            bonus_days INTEGER DEFAULT 0,
            bonus_balance INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT
        )
        """)
        
        # Таблица использованных промокодов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS used_promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_code TEXT,
            user_id INTEGER,
            used_at TEXT
        )
        """)
        
        # Инициализация настроек
        for key, value in DEFAULT_CONFIG.items():
            if key not in ['tariffs', 'mandatory_channels']:
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, json.dumps(value) if isinstance(value, (dict, list)) else str(value))
                )
        
        # Инициализация тарифов
        for key, tariff in DEFAULT_CONFIG['tariffs'].items():
            await db.execute(
                "INSERT OR IGNORE INTO tariffs (key, name, stars, days) VALUES (?, ?, ?, ?)",
                (key, tariff['name'], tariff['stars'], tariff['days'])
            )
        
        # Обновляем referral_code
        await db.execute("""
        UPDATE users
        SET referral_code = 'ref' || tg_id || '0000'
        WHERE referral_code IS NULL OR referral_code = ''
        """)
        
        await db.commit()
    logging.info("✅ База данных инициализирована")

# ================= ПОЛЬЗОВАТЕЛИ =================
async def get_user(tg_id: int):
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
            user = await cursor.fetchone()
            if user:
                return dict(user)
            return None
    except Exception as e:
        logging.error(f"Ошибка get_user: {e}")
        return None

async def ensure_referral_code(tg_id: int):
    try:
        async with aiosqlite.connect("bot.db") as db:
            cursor = await db.execute("SELECT referral_code FROM users WHERE tg_id = ?", (tg_id,))
            user = await cursor.fetchone()
            if user and user['referral_code']:
                return user['referral_code']
            referral_code = f"ref{tg_id}0000"
            await db.execute("UPDATE users SET referral_code = ? WHERE tg_id = ?", (referral_code, tg_id))
            await db.commit()
            return referral_code
    except Exception as e:
        logging.error(f"Ошибка ensure_referral_code: {e}")
        return f"ref{tg_id}0000"

async def create_user(tg_id: int, referred_by: int = None):
    try:
        async with aiosqlite.connect("bot.db") as db:
            cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
            existing = await cursor.fetchone()
            if existing:
                return {'new_user': False, 'existing_user': True}
            
            referral_code = f"ref{tg_id}{int(time.time()) % 10000}"
            await db.execute(
                "INSERT INTO users (tg_id, referral_code, referred_by, referrals_count, balance) VALUES (?, ?, ?, 0, 0)",
                (tg_id, referral_code, referred_by)
            )
            if referred_by:
                await db.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = ?", (referred_by,))
                bonus = await get_setting('referral_bonus_days', 3)
                bonus = int(bonus)
                cursor = await db.execute("SELECT balance FROM users WHERE tg_id = ?", (referred_by,))
                ref_result = await cursor.fetchone()
                current_balance = int(ref_result['balance']) if ref_result else 0
                new_balance = current_balance + bonus
                await db.execute("UPDATE users SET balance = ? WHERE tg_id = ?", (new_balance, referred_by))
                logging.info(f"✅ Реферальный бонус: {bonus} дней пользователю {referred_by}")
                await db.commit()
                return {'new_user': True, 'referred_by': referred_by, 'bonus': bonus, 'new_balance': new_balance}
            await db.commit()
            return {'new_user': True}
    except Exception as e:
        logging.error(f"Ошибка create_user: {e}")
        return None

async def get_user_by_referral_code(code: str):
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
            user = await cursor.fetchone()
            if user:
                return dict(user)
            return None
    except Exception as e:
        logging.error(f"Ошибка get_user_by_referral_code: {e}")
        return None

async def update_subscription(tg_id: int, client_name: str, client_id: str, days: int):
    try:
        start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect("bot.db") as db:
            await db.execute(
                "UPDATE users SET wg_client_name = ?, wg_client_id = ?, subscription_start = ?, subscription_end = ?, is_active = 1 WHERE tg_id = ?",
                (client_name, str(client_id), start, end, tg_id)
            )
            await db.commit()
            logging.info(f"✅ Подписка обновлена для {tg_id}")
    except Exception as e:
        logging.error(f"Ошибка update_subscription: {e}")

async def get_all_users():
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users")
            users = await cursor.fetchall()
            return [dict(u) for u in users]
    except Exception as e:
        logging.error(f"Ошибка get_all_users: {e}")
        return []

# ================= ПРОМОКОДЫ =================
async def activate_promo_code(promo_code: str, user_id: int):
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (promo_code.upper(),))
            promo = await cursor.fetchone()
            
            if not promo:
                return {'success': False, 'message': '❌ Промокод не найден'}
            
            promo_dict = dict(promo)
            if promo_dict['used_count'] >= promo_dict['max_uses']:
                return {'success': False, 'message': '❌ Лимит использований'}
            
            cursor = await db.execute("SELECT * FROM used_promo_codes WHERE promo_code = ? AND user_id = ?", (promo_code.upper(), user_id))
            if await cursor.fetchone():
                return {'success': False, 'message': '❌ Уже использовали'}
            
            cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (user_id,))
            user = await cursor.fetchone()
            if not user:
                return {'success': False, 'message': '❌ Пользователь не найден'}
            
            user_dict = dict(user)
            bonus_days = int(promo_dict['bonus_days'])
            bonus_balance = int(promo_dict['bonus_balance'])
            
            if bonus_days > 0:
                if user_dict.get('is_active') and user_dict.get('subscription_end'):
                    current_end = datetime.strptime(user_dict['subscription_end'], "%Y-%m-%d %H:%M:%S")
                    new_end = current_end + timedelta(days=bonus_days)
                    await db.execute("UPDATE users SET subscription_end = ? WHERE tg_id = ?", (new_end.strftime("%Y-%m-%d %H:%M:%S"), user_id))
                else:
                    start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    end = (datetime.now() + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                    await db.execute("UPDATE users SET subscription_start = ?, subscription_end = ?, is_active = 1 WHERE tg_id = ?", (start, end, user_id))
            
            if bonus_balance > 0:
                current_balance = int(user_dict.get('balance', 0))
                new_balance = current_balance + bonus_balance
                await db.execute("UPDATE users SET balance = ? WHERE tg_id = ?", (new_balance, user_id))
            
            await db.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (promo_code.upper(),))
            await db.execute("INSERT INTO used_promo_codes (promo_code, user_id, used_at) VALUES (?, ?, ?)", (promo_code.upper(), user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            await db.commit()
            
            message = "✅ <b>Промокод активирован!</b>\n\n"
            if bonus_days > 0:
                message += f"📅 Добавлено дней: {bonus_days}\n"
            if bonus_balance > 0:
                message += f"💎 Начислено на баланс: {bonus_balance} дней\n"
            return {'success': True, 'message': message}
    except Exception as e:
        logging.error(f"Ошибка activate_promo_code: {e}")
        return {'success': False, 'message': '❌ Ошибка'}

async def create_promo_code(code: str, bonus_days: int, bonus_balance: int, max_uses: int, created_by: int):
    try:
        async with aiosqlite.connect("bot.db") as db:
            await db.execute(
                "INSERT INTO promo_codes (code, bonus_days, bonus_balance, max_uses, used_count, is_active, created_by, created_at) VALUES (?, ?, ?, ?, 0, 1, ?, ?)",
                (code.upper(), bonus_days, bonus_balance, max_uses, created_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            await db.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка create_promo_code: {e}")
        return False

async def get_all_promo_codes():
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
            promos = await cursor.fetchall()
            return [dict(p) for p in promos]
    except Exception as e:
        logging.error(f"Ошибка get_all_promo_codes: {e}")
        return []

# ================= WIREGUARD API =================
class WireGuardAPI:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url
        self.password = password
        self.cookies = {}
        self.session = None
    
    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def login(self):
        session = await self._get_session()
        try:
            async with session.post(f"{self.base_url}/api/session", json={"password": self.password}) as resp:
                if resp.status == 200:
                    for cookie_name, cookie in resp.cookies.items():
                        self.cookies[cookie_name] = cookie.value
                    logging.info("✅ WireGuard API: авторизация успешна")
                    return True
                return False
        except Exception as e:
            logging.error(f"WireGuard API error: {e}")
            return False
    
    async def create_client(self, name: str):
        if not self.cookies:
            await self.login()
        session = await self._get_session()
        try:
            async with session.post(f"{self.base_url}/api/wireguard/client", json={"name": name}, cookies=self.cookies) as resp:
                if resp.status == 200:
                    async with session.get(f"{self.base_url}/api/wireguard/client", cookies=self.cookies) as list_resp:
                        if list_resp.status == 200:
                            clients_data = await list_resp.json()
                            for client in clients_data:
                                if client.get('name') == name:
                                    return client.get('id')
                return None
        except Exception as e:
            logging.error(f"WireGuard create_client error: {e}")
            return None
    
    async def get_config(self, client_id):
        if not self.cookies:
            await self.login()
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/api/wireguard/client/{client_id}/configuration", cookies=self.cookies) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None
        except Exception as e:
            logging.error(f"WireGuard get_config error: {e}")
            return None

wg_api = WireGuardAPI(WG_PANEL_URL, WG_PASSWORD)

# ================= ПРОВЕРКА ПОДПИСКИ =================
async def get_unsubscribed_channels(bot: Bot, user_id: int):
    channels = await get_mandatory_channels_db()
    unsubscribed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch['chat_id'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unsubscribed.append(ch)
        except Exception as e:
            logging.warning(f"Не удалось проверить канал {ch['chat_id']}: {e}")
    return unsubscribed

async def require_subscription(event, bot: Bot, user_id: int) -> bool:
    unsubscribed = await get_unsubscribed_channels(bot, user_id)
    if not unsubscribed:
        return True
    
    kb = []
    for ch in unsubscribed:
        url = ch['username'] if ch['username'].startswith('http') else f"https://t.me/{ch['username'].replace('@', '')}"
        kb.append([InlineKeyboardButton(text=f"🔗 Подписаться {ch['username']}", url=url)])
    kb.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    
    text = "⚠️ <b>Для использования бота необходимо подписаться:</b>"
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    return False

# ================= КЛАВИАТУРЫ =================
async def get_main_keyboard():
    support_username = await get_setting('support_username', 'nocaponeNGG')
    support_url = f"https://t.me/{support_username}" if not support_username.startswith('http') else support_username
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎉 Бесплатный тест VPN!", callback_data="free_trial")],
        [
            InlineKeyboardButton(text=" Личный кабинет", callback_data="profile"),
            InlineKeyboardButton(text="🔐 Подключить VPN", callback_data="connect_vpn")
        ],
        [
            InlineKeyboardButton(text="📚 Инструкция", callback_data="help"),
            InlineKeyboardButton(text="🆘 Поддержка", url=support_url)
        ],
        [InlineKeyboardButton(text="🎁 Активировать промокод", callback_data="activate_promo")],
        [InlineKeyboardButton(text=" Купить VPN 🚀", callback_data="buy_vpn")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📢 Обязательная подписка", callback_data="admin_channels")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text=" Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="️ Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])

async def get_admin_channels_keyboard():
    channels = await get_mandatory_channels_db()
    kb = []
    for ch in channels:
        kb.append([InlineKeyboardButton(text=f"❌ Удалить {ch['username']}", callback_data=f"admin_ch_rem_{ch['chat_id']}")])
    kb.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_ch_add")])
    kb.append([InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_start")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def get_tariff_keyboard():
    tariffs = await get_all_tariffs()
    keyboard = []
    for key, tariff in tariffs.items():
        keyboard.append([InlineKeyboardButton(text=f"{tariff['name']} - {tariff['stars']}⭐", callback_data=f"tariff_{key}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Редактировать тарифы", callback_data="admin_edit_tariffs_menu")],
        [InlineKeyboardButton(text="📝 Текст приветствия", callback_data="admin_edit_welcome_text")],
        [InlineKeyboardButton(text="📝 Текст покупки", callback_data="admin_edit_purchase_text")],
        [InlineKeyboardButton(text="📝 Текст помощи", callback_data="admin_edit_help_text")],
        [InlineKeyboardButton(text="📝 Текст рефералки", callback_data="admin_edit_referral_text")],
        [InlineKeyboardButton(text="⭐ Реферальный бонус", callback_data="admin_edit_referral_bonus")],
        [InlineKeyboardButton(text="🎁 Дни тестового периода", callback_data="admin_edit_trial_days")],
        [InlineKeyboardButton(text="💬 Кнопка поддержки", callback_data="admin_edit_support")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]
    ])

async def get_edit_tariffs_keyboard():
    tariffs = await get_all_tariffs()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 месяц: {tariffs['1_month']['stars']}⭐ / {tariffs['1_month']['days']}дн", callback_data="admin_edit_1month")],
        [InlineKeyboardButton(text=f"3 месяца: {tariffs['3_months']['stars']}⭐ / {tariffs['3_months']['days']}дн", callback_data="admin_edit_3months")],
        [InlineKeyboardButton(text=f"6 месяцев: {tariffs['6_months']['stars']}⭐ / {tariffs['6_months']['days']}дн", callback_data="admin_edit_6months")],
        [InlineKeyboardButton(text=" Назад", callback_data="admin_settings")]
    ])

def get_edit_tariff_options_keyboard(tariff_key):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"admin_change_price_{tariff_key}")],
        [InlineKeyboardButton(text="📅 Изменить дни", callback_data=f"admin_change_days_{tariff_key}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_edit_tariffs_menu")]
    ])

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История", callback_data="history")],
        [InlineKeyboardButton(text="💎 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])

def get_promo_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo_create")],
        [InlineKeyboardButton(text=" Список промокодов", callback_data="admin_promo_list")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_start")]
    ])

# ================= ОБРАБОТЧИКИ =================
@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    try:
        logging.info(f"/start от {message.from_user.id}")
        args = message.text.split()
        referral_code = args[1] if len(args) > 1 else None
        referred_by = None
        
        if referral_code:
            referrer = await get_user_by_referral_code(referral_code)
            if referrer and referrer['tg_id'] != message.from_user.id:
                referred_by = referrer['tg_id']
        
        referral_info = await create_user(message.from_user.id, referred_by=referred_by)
        if referral_info and referral_info.get('existing_user'):
            if referred_by:
                referrer_user = await get_user(referred_by)
                referrer_name = referrer_user.get('wg_client_name', f"ID {referred_by}") if referrer_user else "неизвестно"
                await message.answer(f"ℹ️ <b>Вы уже зарегистрированы!</b>\nВы перешли по ссылке: {referrer_name}\nНо бонус не начислен.", parse_mode="HTML")
                return
        
        if referral_info and referral_info.get('new_user') and referral_info.get('referred_by'):
            bonus = int(referral_info['bonus'])
            referrer_data = await get_user(referred_by)
            referrer_balance = int(referrer_data.get('balance', bonus)) if referrer_data else bonus
            await message.answer(f"🎁 <b>Вам начислен бонус!</b>\n💰 Начислено: {bonus} дней\n💵 Баланс: {bonus} дней", parse_mode="HTML")
            try:
                username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{message.from_user.id}"
                await bot.send_message(referred_by, f"🎉 <b>Новый реферал!</b>\nПользователь {username} зарегистрировался!\n💰 Начислено: {bonus} дней\n💵 Баланс: {referrer_balance} дней", parse_mode="HTML")
            except Exception as e:
                logging.error(f"❌ Ошибка уведомления: {e}")
        
        if not await require_subscription(message, bot, message.from_user.id):
            return
        
        welcome_text = await get_setting('welcome_text', DEFAULT_CONFIG['welcome_text'])
        if message.from_user.id == ADMIN_ID:
            await message.answer("Привет, Админ! \nДобро пожаловать в панель управления.", reply_markup=get_admin_keyboard())
        else:
            await message.answer(welcome_text.format(name=message.from_user.first_name), reply_markup=await get_main_keyboard(), parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ Ошибка cmd_start: {e}", exc_info=True)
        await message.answer("Произошла ошибка.")

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    is_sub = await require_subscription(callback, callback.bot, callback.from_user.id)
    if is_sub:
        welcome_text = await get_setting('welcome_text', DEFAULT_CONFIG['welcome_text'])
        if callback.from_user.id == ADMIN_ID:
            await callback.message.edit_text("✅ Спасибо!\n\nПривет, Админ!", reply_markup=get_admin_keyboard())
        else:
            await callback.message.edit_text(f"✅ Спасибо!\n\n{welcome_text}", reply_markup=await get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        welcome_text = await get_setting('welcome_text', DEFAULT_CONFIG['welcome_text'])
        await callback.message.edit_text(welcome_text, reply_markup=await get_main_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_main_menu: {e}")

@router.callback_query(F.data == "start")
async def cb_start(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        welcome_text = await get_setting('welcome_text', DEFAULT_CONFIG['welcome_text'])
        await callback.message.edit_text(welcome_text, reply_markup=await get_main_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_start: {e}")

@router.callback_query(F.data == "free_trial")
async def cb_free_trial(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        
        user = await get_user(callback.from_user.id)
        if not user:
            await create_user(callback.from_user.id)
            user = await get_user(callback.from_user.id)
        
        if user.get('trial_used', 0):
            await callback.answer("❌ Вы уже использовали тест!", show_alert=True)
            return
        
        trial_days = int(await get_setting('trial_days', 3))
        await callback.message.answer(f"<b>Бесплатный тест!</b>\nАктивирован доступ на {trial_days} дня!\n📥 Сейчас получите конфигурацию.", parse_mode="HTML")
        
        try:
            user_chat = await callback.bot.get_chat(callback.from_user.id)
            username = user_chat.username
            client_name = f"trial_{username}" if username else f"trial_{callback.from_user.id}"
        except Exception:
            client_name = f"trial_{callback.from_user.id}"
        
        client_name = f"{client_name}_{int(time.time())}"
        logging.info(f"🔧 Создание тестового клиента {client_name}...")
        client_id = await wg_api.create_client(client_name)
        
        if client_id:
            config_text = await wg_api.get_config(client_id)
            if config_text:
                await update_subscription(callback.from_user.id, client_name, client_id, trial_days)
                async with aiosqlite.connect("bot.db") as db:
                    await db.execute("UPDATE users SET trial_used = 1 WHERE tg_id = ?", (callback.from_user.id,))
                    await db.commit()
                
                file_name = f"wg_{callback.from_user.id}.conf"
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(config_text)
                await callback.message.answer_document(FSInputFile(file_name, filename=file_name))
                os.remove(file_name)
                logging.info(f"✅ Тестовая конфигурация отправлена {callback.from_user.id}")
        
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_free_trial: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        
        user = await get_user(callback.from_user.id)
        if not user:
            await create_user(callback.from_user.id)
            user = await get_user(callback.from_user.id)
        
        is_active = user.get('is_active', 0)
        wg_client_id = user.get('wg_client_id')
        referrals_count = user.get('referrals_count', 0)
        balance = int(user.get('balance', 0))
        
        if is_active and wg_client_id:
            status_text = "🟢 Активен"
            end_date = datetime.strptime(user['subscription_end'], "%Y-%m-%d %H:%M:%S")
            remaining = end_date - datetime.now()
            if remaining.total_seconds() > 0:
                days_left = remaining.days
                status_text += f" (осталось {days_left} дн.)"
            else:
                status_text = "🔴 Не активен"
        else:
            status_text = "🔴 Не активен"
        
        devices_count = 1 if wg_client_id else 0
        profile_text = (
            f"💼 <b>Личный кабинет</b>\n\n"
            f"├ VPN статус: {status_text}\n"
            f"├ Подключено устройств: {devices_count} шт.\n"
            f"├ Лимит моб. трафик: 50 GB\n"
            f"└ Приглашено друзей: {referrals_count} чел.\n\n"
            f"💎 Ваш баланс: {balance} дней"
        )
        await callback.message.answer(profile_text, parse_mode="HTML", reply_markup=get_profile_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_profile: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "connect_vpn")
async def cb_connect_vpn(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        
        user = await get_user(callback.from_user.id)
        if not user or not user.get('wg_client_id'):
            await callback.message.answer("🔐 <b>Подключить VPN</b>\n\n❌ Нет активной подписки!", parse_mode="HTML", reply_markup=await get_main_keyboard())
            await callback.answer()
            return
        
        config_text = await wg_api.get_config(user['wg_client_id'])
        if not config_text:
            await callback.message.answer("❌ Не удалось получить конфигурацию.")
            await callback.answer()
            return
        
        file_name = f"wg_{user['tg_id']}.conf"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(config_text)
        await callback.message.answer_document(FSInputFile(file_name, filename=file_name), caption="<b>Ваша конфигурация VPN</b>", parse_mode="HTML")
        os.remove(file_name)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_connect_vpn: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "activate_promo")
async def cb_activate_promo(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        await callback.message.answer(" <b>Активировать промокод</b>\n\nОтправьте промокод:\n\n/cancel для отмены", parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_activate_promo: {e}")

@router.message(F.text & ~F.text.startswith('/'))
async def process_promo_activation(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
    
    promo_code = message.text.strip().upper()
    if not promo_code or len(promo_code) < 3:
        return
    
    result = await activate_promo_code(promo_code, message.from_user.id)
    await message.answer(result['message'], parse_mode="HTML")

@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        await callback.message.answer(" <b>История</b>\nВ разработке...", parse_mode="HTML", reply_markup=get_profile_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_history: {e}")

@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        
        user = await get_user(callback.from_user.id)
        if not user:
            await create_user(callback.from_user.id)
            user = await get_user(callback.from_user.id)
        
        referral_code = await ensure_referral_code(callback.from_user.id)
        user = await get_user(callback.from_user.id)
        balance = int(user.get('balance', 0)) if user else 0
        referrals_count = user.get('referrals_count', 0) if user else 0
        bonus = int(await get_setting('referral_bonus_days', 3))
        bot_info = await callback.bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start={referral_code}"
        
        referral_text = await get_setting('referral_text', DEFAULT_CONFIG['referral_text'])
        referral_text = referral_text.format(bonus=bonus, referral_link=referral_link)
        
        stats_text = f"👥 <b>Ваша статистика:</b>\n\n Баланс: {balance} дней\n👥 Приглашено: {referrals_count}\n💰 За друга: {bonus} дней\n\n"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=" Поделиться!", url=f"https://t.me/share/url?url={referral_link}&text=Приглашаю в VPN бот!")]])
        
        await callback.message.answer(stats_text + referral_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ Ошибка cb_referral: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "buy_vpn")
async def cb_buy_vpn(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        text = "<b>Купить VPN подписку</b>\n\nВыберите тариф:"
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=await get_tariff_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_buy_vpn: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

# ================= АДМИНКА - ПРОМОКОДЫ =================
@router.callback_query(F.data == "admin_promo")
async def cb_admin_promo(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("🎟️ <b>Управление промокодами</b>\n\nВыберите действие:", reply_markup=get_promo_menu_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_promo_create")
async def cb_admin_promo_create(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("️ <b>Создание промокода</b>\n\nОтправьте код (латиница, цифры):\n\n/cancel для отмены", parse_mode="HTML")
    await state.set_state(AdminEditStates.creating_promo)
    await callback.answer()

@router.message(AdminEditStates.creating_promo, F.text)
async def process_create_promo_code(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Только латиница и цифры!")
        return
    await state.update_data(promo_code=code)
    await message.answer(f"📅 <b>Промокод: {code}</b>\n\nКоличество дней подписки (0 если не нужно):\n\n/cancel для отмены", parse_mode="HTML")
    await state.set_state(AdminEditStates.editing_promo_days)

@router.message(AdminEditStates.editing_promo_days, F.text)
async def process_promo_days(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        days = int(message.text)
        if days < 0:
            await message.answer("❌ Не может быть отрицательным!")
            return
        await state.update_data(bonus_days=days)
        await message.answer("💎 Дней на баланс (0 если не нужно):\n\n/cancel для отмены")
        await state.set_state(AdminEditStates.editing_promo_balance)
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_promo_balance, F.text)
async def process_promo_balance(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        balance = int(message.text)
        if balance < 0:
            await message.answer("❌ Не может быть отрицательным!")
            return
        await state.update_data(bonus_balance=balance)
        await message.answer("🔢 Макс. использований (1 = одноразовый):\n\n/cancel для отмены")
        await state.set_state(AdminEditStates.editing_promo_uses)
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_promo_uses, F.text)
async def process_promo_uses(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        max_uses = int(message.text)
        if max_uses < 1:
            await message.answer("❌ Минимум 1!")
            return
        data = await state.get_data()
        code = data.get('promo_code')
        days = data.get('bonus_days', 0)
        balance = data.get('bonus_balance', 0)
        
        if await create_promo_code(code, days, balance, max_uses, message.from_user.id):
            await message.answer(f"✅ <b>Промокод создан!</b>\n\n️ Код: <code>{code}</code>\n📅 Дней подписки: {days}\n💎 Дней на баланс: {balance}\n🔢 Макс. использований: {max_uses}", parse_mode="HTML", reply_markup=get_promo_menu_keyboard())
        else:
            await message.answer("❌ Ошибка!")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.callback_query(F.data == "admin_promo_list")
async def cb_admin_promo_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    promos = await get_all_promo_codes()
    if not promos:
        text = "️ <b>Промокоды</b>\n\nНе созданы."
    else:
        text = "🎟️ <b>Список промокодов:</b>\n\n"
        for promo in promos[:10]:
            status = "✅" if promo['is_active'] else "❌"
            text += f"{status} <code>{promo['code']}</code>\n   📅 {promo['bonus_days']}дн | 💎 {promo['bonus_balance']}дн | Использовано: {promo['used_count']}/{promo['max_uses']}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Создать", callback_data="admin_promo_create")], [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_promo")]])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

# ================= РЕДАКТИРОВАНИЕ ПОДДЕРЖКИ =================
@router.callback_query(F.data == "admin_edit_support")
async def cb_admin_edit_support(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    current_support = await get_setting('support_username', 'nocaponeNGG')
    await callback.message.answer(f"💬 <b>Кнопка поддержки</b>\n\nТекущий: <code>@{current_support}</code>\n\nОтправьте новый username (без @):\n\n/cancel для отмены", parse_mode="HTML")
    await state.set_state(AdminEditStates.editing_support_username)
    await callback.answer()

@router.message(AdminEditStates.editing_support_username, F.text)
async def process_edit_support(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    support_username = message.text.strip()
    if support_username.startswith('@'):
        support_username = support_username[1:]
    await set_setting('support_username', support_username)
    await message.answer(f"✅ Обновлено!\n\nТеперь: https://t.me/{support_username}", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@router.callback_query(F.data == "admin_start")
async def cb_admin_start(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        await callback.message.edit_text("Панель администратора:", reply_markup=get_admin_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_start: {e}")

@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        await callback.message.answer("⚙️ <b>Настройки бота</b>\n\nВыберите:", reply_markup=get_admin_settings_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_settings: {e}")

# ================= ОБЯЗАТЕЛЬНАЯ ПОДПИСКА =================
@router.callback_query(F.data == "admin_channels")
async def cb_admin_channels(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    channels = await get_mandatory_channels_db()
    if not channels:
        text = "📢 <b>Обязательная подписка</b>\n\nКаналы не добавлены."
    else:
        text = f" <b>Обязательная подписка</b>\n\nКаналов: {len(channels)}"
    await callback.message.edit_text(text, reply_markup=await get_admin_channels_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_ch_rem_"))
async def cb_admin_ch_remove(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    chat_id = int(callback.data.replace("admin_ch_rem_", ""))
    await remove_channel_db(chat_id)
    await cb_admin_channels(callback)

@router.callback_query(F.data == "admin_ch_add")
async def cb_admin_ch_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("<b>Добавление канала</b>\n\nОтправьте username (например: @durov) или ссылку.\n⚠️ Бот должен быть АДМИНИСТРАТОРОМ!\n\n/cancel для отмены", parse_mode="HTML")
    await state.set_state(AdminChannelStates.waiting_channel)
    await callback.answer()

@router.message(AdminChannelStates.waiting_channel)
async def process_channel_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
        return
    
    username = message.text.strip()
    if not username.startswith('@') and not username.startswith('http'):
        username = '@' + username
    if username.startswith('http'):
        username = username.split('/')[-1]
        if not username.startswith('@'):
            username = '@' + username
    
    try:
        chat = await message.bot.get_chat(username)
        await add_channel_db(chat.id, username)
        await message.answer(f"✅ Канал {username} добавлен!", reply_markup=await get_admin_channels_keyboard())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}\n\nУбедитесь что:\n1. Канал существует\n2. Бот - администратор", reply_markup=await get_admin_channels_keyboard())
    await state.clear()

# ================= РЕДАКТИРОВАНИЕ ТЕКСТА РЕФЕРАЛКИ =================
@router.callback_query(F.data == "admin_edit_referral_text")
async def cb_admin_edit_referral_text(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        current_text = await get_setting('referral_text', DEFAULT_CONFIG['referral_text'])
        await callback.message.answer(f"<b>Текущий текст:</b>\n\n{current_text}\n\nОтправьте новый (HTML, используйте {{bonus}} и {{referral_link}})\n\n/cancel для отмены", parse_mode="HTML")
        await state.set_state(AdminEditStates.editing_referral_text)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_referral_text: {e}")

@router.message(AdminEditStates.editing_referral_text)
async def process_edit_referral_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await set_setting('referral_text', message.text)
    await message.answer("✅ Текст обновлен!", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@router.callback_query(F.data == "admin_edit_referral_bonus")
async def cb_admin_edit_referral_bonus(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        current_bonus = int(await get_setting('referral_bonus_days', 3))
        await callback.message.answer(f"⭐ <b>Реферальный бонус</b>\n\nТекущий: <b>{current_bonus} дней</b>\n\nОтправьте новое количество:\n\n/cancel для отмены", parse_mode="HTML")
        await state.set_state(AdminEditStates.editing_referral_bonus)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_referral_bonus: {e}")

@router.message(AdminEditStates.editing_referral_bonus, F.text)
async def process_edit_referral_bonus(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_bonus = int(message.text)
        if new_bonus < 0:
            await message.answer("❌ Не может быть отрицательным!")
            return
        await set_setting('referral_bonus_days', new_bonus)
        await message.answer(f"✅ Бонус изменен на {new_bonus} дней", reply_markup=get_admin_settings_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        
        users = await get_all_users()
        total_users = len(users)
        active_count = sum(1 for u in users if u.get('is_active'))
        total_referrals = sum(u.get('referrals_count', 0) for u in users)
        total_balance = sum(int(u.get('balance', 0)) for u in users)
        tariffs = await get_all_tariffs()
        
        text = f"📊 <b>Статистика бота</b>\n\n👥 <b>Пользователи:</b>\n   Всего: {total_users}\n   Активных: {active_count}\n\n👥 <b>Рефералы:</b>\n   Всего приглашений: {total_referrals}\n\n <b>Балансы:</b>\n   Всего выдано: {total_balance} дней\n\n💰 <b>Тарифы:</b>\n"
        for key, tariff in tariffs.items():
            text += f"   {tariff['name']}: {tariff['stars']}⭐ / {tariff['days']}дн\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]])
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_stats: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "admin_edit_tariffs_menu")
async def cb_admin_edit_tariffs(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        await callback.message.answer("💰 <b>Редактирование тарифов</b>\n\nВыберите тариф:", reply_markup=await get_edit_tariffs_keyboard(), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_tariffs: {e}")

@router.callback_query(F.data.startswith("admin_edit_") & (F.data.endswith("month") | F.data.endswith("months")))
async def cb_admin_edit_tariff(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        tariff_key = callback.data.replace("admin_edit_", "")
        await callback.message.answer("Выберите что изменить:", reply_markup=get_edit_tariff_options_keyboard(tariff_key))
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_tariff: {e}")

@router.callback_query(F.data == "admin_edit_welcome_text")
async def cb_admin_edit_welcome(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        current_text = await get_setting('welcome_text', DEFAULT_CONFIG['welcome_text'])
        await callback.message.answer(f"📝 <b>Текущий текст:</b>\n\n{current_text}\n\nОтправьте новый (используйте {{name}})\n\n/cancel для отмены", parse_mode="HTML")
        await state.set_state(AdminEditStates.editing_welcome_text)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_welcome: {e}")

@router.callback_query(F.data == "admin_edit_purchase_text")
async def cb_admin_edit_purchase(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        current_text = await get_setting('purchase_success_text', DEFAULT_CONFIG['purchase_success_text'])
        await callback.message.answer(f"<b>Текущий текст:</b>\n\n{current_text}\n\nОтправьте новый (HTML, {{tariff_name}} и {{expiry_date}})\n\n/cancel для отмены", parse_mode="HTML")
        await state.set_state(AdminEditStates.editing_purchase_text)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_purchase: {e}")

@router.callback_query(F.data == "admin_edit_help_text")
async def cb_admin_edit_help(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        current_text = await get_setting('help_text', DEFAULT_CONFIG['help_text'])
        await callback.message.answer(f"📝 <b>Текущий текст:</b>\n\n{current_text}\n\nОтправьте новый (HTML)\n\n/cancel для отмены", parse_mode="HTML")
        await state.set_state(AdminEditStates.editing_help_text)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_help: {e}")

@router.callback_query(F.data.startswith("admin_change_price_"))
async def cb_admin_change_price(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        tariff_key = callback.data.replace("admin_change_price_", "")
        await state.set_state(getattr(AdminEditStates, f'editing_price_{tariff_key}', AdminEditStates.editing_price_1month))
        await callback.message.answer("💰 Введите новую цену в звездах:")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_change_price: {e}")

@router.callback_query(F.data.startswith("admin_change_days_"))
async def cb_admin_change_days(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        tariff_key = callback.data.replace("admin_change_days_", "")
        await state.set_state(getattr(AdminEditStates, f'editing_days_{tariff_key}', AdminEditStates.editing_days_1month))
        await callback.message.answer(" Введите количество дней:")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_change_days: {e}")

@router.message(AdminEditStates.editing_welcome_text, F.text)
async def process_edit_welcome(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    logging.info(f"Редактирование welcome_text от пользователя {message.from_user.id}")
    success = await set_setting('welcome_text', message.text)
    if success:
        await message.answer("✅ Текст приветствия обновлен!", reply_markup=get_admin_settings_keyboard())
        logging.info("✅ Текст приветствия успешно сохранен")
    else:
        await message.answer("❌ Ошибка при сохранении в БД")
        logging.error("❌ Ошибка при сохранении текста приветствия")
    await state.clear()

@router.message(AdminEditStates.editing_purchase_text, F.text)
async def process_edit_purchase(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    logging.info(f"Редактирование purchase_text от пользователя {message.from_user.id}")
    success = await set_setting('purchase_success_text', message.text)
    if success:
        await message.answer("✅ Текст покупки обновлен!", reply_markup=get_admin_settings_keyboard())
        logging.info("✅ Текст покупки успешно сохранен")
    else:
        await message.answer("❌ Ошибка при сохранении в БД")
    await state.clear()

@router.message(AdminEditStates.editing_help_text, F.text)
async def process_edit_help(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    logging.info(f"Редактирование help_text от пользователя {message.from_user.id}")
    success = await set_setting('help_text', message.text)
    if success:
        await message.answer("✅ Текст помощи обновлен!", reply_markup=get_admin_settings_keyboard())
        logging.info("✅ Текст помощи успешно сохранен")
    else:
        await message.answer("❌ Ошибка при сохранении в БД")
    await state.clear()

@router.message(AdminEditStates.editing_price_1month, F.text)
async def process_edit_price_1month(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        await update_tariff_db('1_month', stars=new_price)
        await message.answer(f"✅ Цена для 1 месяца: {new_price}⭐", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_price_3months, F.text)
async def process_edit_price_3months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        await update_tariff_db('3_months', stars=new_price)
        await message.answer(f"✅ Цена для 3 месяцев: {new_price}⭐", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_price_6months, F.text)
async def process_edit_price_6months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        await update_tariff_db('6_months', stars=new_price)
        await message.answer(f"✅ Цена для 6 месяцев: {new_price}⭐", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_1month, F.text)
async def process_edit_days_1month(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        await update_tariff_db('1_month', days=new_days)
        await message.answer(f"✅ Срок для 1 месяца: {new_days} дней", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_3months, F.text)
async def process_edit_days_3months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        await update_tariff_db('3_months', days=new_days)
        await message.answer(f"✅ Срок для 3 месяцев: {new_days} дней", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_6months, F.text)
async def process_edit_days_6months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        await update_tariff_db('6_months', days=new_days)
        await message.answer(f"✅ Срок для 6 месяцев: {new_days} дней", reply_markup=await get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery, state: FSMContext):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        tariff_key = callback.data.replace("tariff_", "")
        tariffs = await get_all_tariffs()
        tariff = tariffs[tariff_key]
        
        await state.set_state(PurchaseStates.selecting_tariff)
        await state.update_data(tariff_key=tariff_key, stars=tariff['stars'], days=tariff['days'], name=tariff['name'])
        await callback.message.answer(f"<b>Покупка тарифа '{tariff['name']}'</b>\n\n Стоимость: {tariff['stars']} \n📅 Срок: {tariff['days']} дней\n\nДля подтверждения нажмите кнопку", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💳 Оплатить {tariff['stars']} ⭐", callback_data=f"pay_{tariff_key}")], [InlineKeyboardButton(text="🔙 Отмена", callback_data="buy_vpn")]]), parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_tariff_selected: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("pay_"))
async def cb_pay(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        tariff_key = data.get('tariff_key')
        if not tariff_key:
            await callback.answer("Сессия истекла.", show_alert=True)
            return
        
        tariffs = await get_all_tariffs()
        tariff = tariffs[tariff_key]
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"VPN Подписка - {tariff['name']}",
            description=f"Оплата подписки WireGuard VPN на {tariff['days']} дней",
            payload=f"wg_{tariff_key}_{callback.from_user.id}_{int(time.time())}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=tariff['name'], amount=tariff['stars'])],
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_pay: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    try:
        logging.info(f"✅ Pre-checkout query от {pre_checkout_query.from_user.id}")
        await pre_checkout_query.answer(ok=True)
    except Exception as e:
        logging.error(f"Ошибка pre_checkout: {e}")
        await pre_checkout_query.answer(ok=False)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext):
    try:
        successful_payment = message.successful_payment
        payload = successful_payment.invoice_payload
        parts = payload.split('_')
        
        if len(parts) >= 3:
            tariff_key = parts[1]
            user_id = int(parts[2])
            tariffs = await get_all_tariffs()
            tariff = tariffs[tariff_key]
            logging.info(f"💰 Успешная оплата от {user_id}: {tariff['name']}, {tariff['stars']}⭐")
            
            try:
                user_chat = await message.bot.get_chat(user_id)
                username = user_chat.username
                client_name = f"{username}" if username else f"tg{user_id}"
            except Exception:
                client_name = f"tg{user_id}"
            
            client_name = f"{client_name}_{int(time.time())}"
            logging.info(f" Создание клиента {client_name}...")
            client_id = await wg_api.create_client(client_name)
            
            if client_id:
                config_text = await wg_api.get_config(client_id)
                if config_text:
                    await update_subscription(user_id, client_name, client_id, tariff['days'])
                    file_name = f"wg_{user_id}.conf"
                    with open(file_name, "w", encoding="utf-8") as f:
                        f.write(config_text)
                    
                    expiry_date = (datetime.now() + timedelta(days=tariff['days'])).strftime('%d.%m.%Y')
                    purchase_text = await get_setting('purchase_success_text', DEFAULT_CONFIG['purchase_success_text'])
                    purchase_text = purchase_text.format(tariff_name=tariff['name'], expiry_date=expiry_date)
                    await message.answer(purchase_text, parse_mode="HTML")
                    await message.answer_document(FSInputFile(file_name, filename=file_name))
                    os.remove(file_name)
                    await state.clear()
                    logging.info(f"✅ Конфигурация отправлена {user_id}")
            else:
                await message.answer("❌ Ошибка при активации.")
    except Exception as e:
        logging.error(f"Ошибка process_successful_payment: {e}")
        await message.answer("❌ Ошибка при активации.")

@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.message.answer("📭 <b>Нет активной подписки</b>", reply_markup=await get_main_keyboard(), parse_mode="HTML")
            await callback.answer()
            return
        
        is_active = user.get('is_active', 0)
        wg_client_id = user.get('wg_client_id')
        if not is_active or not wg_client_id:
            await callback.message.answer("📭 <b>Нет активной подписки</b>", reply_markup=await get_main_keyboard(), parse_mode="HTML")
            await callback.answer()
            return
        
        end_date = datetime.strptime(user['subscription_end'], "%Y-%m-%d %H:%M:%S")
        remaining = end_date - datetime.now()
        if remaining.total_seconds() <= 0:
            await callback.message.answer("⚠️ <b>Подписка истекла!</b>", reply_markup=await get_main_keyboard(), parse_mode="HTML")
            await callback.answer()
            return
        
        config_text = await wg_api.get_config(wg_client_id)
        if not config_text:
            await callback.message.answer(" Не удалось получить конфигурацию.")
            await callback.answer()
            return
        
        file_name = f"wg_{user['tg_id']}.conf"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(config_text)
        
        days = remaining.days
        hours = remaining.seconds // 3600
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Перенести ключи", callback_data=f"share_config_{wg_client_id}")], [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]])
        await callback.message.answer(f"📱 <b>Ваша подписка</b>\n\n✅ Статус: Активна\n📅 Осталось: {days} дн. {hours} ч.\n🕐 Истекает: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n📥 Ваша конфигурация:", parse_mode="HTML", reply_markup=keyboard)
        await callback.message.answer_document(FSInputFile(file_name, filename=file_name))
        os.remove(file_name)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_my_subscription: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("share_config_"))
async def cb_share_config(callback: CallbackQuery):
    try:
        client_id = callback.data.replace("share_config_", "")
        if not client_id or client_id == "None":
            await callback.message.answer("❌ Не найден ID клиента.")
            await callback.answer()
            return
        
        config_text = await wg_api.get_config(client_id)
        if not config_text:
            await callback.message.answer("❌ Не удалось получить конфигурацию.")
            await callback.answer()
            return
        
        file_name = f"wg_{callback.from_user.id}.conf"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(config_text)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="my_subscription")]])
        await callback.message.answer_document(FSInputFile(file_name, filename=file_name), caption="📤 Отправьте в приложение WireGuard", reply_markup=keyboard)
        os.remove(file_name)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_share_config: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    try:
        if not await require_subscription(callback, callback.bot, callback.from_user.id):
            return
        help_text = await get_setting('help_text', DEFAULT_CONFIG['help_text'])
        await callback.message.answer(help_text, parse_mode="HTML", reply_markup=await get_main_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_help: {e}")

# ================= АДМИН ПАНЕЛЬ =================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Панель администратора:", reply_markup=get_admin_keyboard())

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        
        users = await get_all_users()
        text = f"<b>Всего пользователей: {len(users)}</b>\n\n"
        
        for user in users:
            status = "✅" if user.get('is_active') else "❌"
            end = (user.get('subscription_end') or "Нет")[:10]
            name = user.get('wg_client_name') or "Нет"
            referrals = user.get('referrals_count', 0)
            balance = int(user.get('balance', 0))
            
            try:
                user_chat = await callback.bot.get_chat(user['tg_id'])
                username = f"@{user_chat.username}" if user_chat.username else "❌ Нет"
                full_name = user_chat.first_name or "Нет"
            except Exception:
                username = "❌ Нет"
                full_name = "Нет"
            
            text += f"{status} <b>{full_name}</b> {username}\n   ID: <code>{user['tg_id']}</code>\n   WG: {name} | До: {end}\n   Рефералы: {referrals} | Баланс: {balance} дней\n\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]])
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_users: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("📢 <b>Рассылка</b>\n\nОтправьте сообщение:\n\n/cancel для отмены", parse_mode="HTML")
    await state.set_state(BroadcastStates.waiting_message)
    await callback.answer()

@router.message(BroadcastStates.waiting_message, F.text)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    success = 0
    for user in users:
        try:
            await message.bot.send_message(user['tg_id'], message.text)
            success += 1
        except:
            pass
    await message.answer(f"✅ Рассылка завершена!\n\n📤 Отправлено: {success}/{len(users)}")
    await state.clear()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
    else:
        await message.answer("❌ Отменено", reply_markup=await get_main_keyboard())

# ================= ЗАПУСК =================
async def main():
    logging.info("Запуск бота...")
    logging.info(f"Текущая директория: {os.getcwd()}")
    logging.info(f"Права на запись bot.db: {os.access('bot.db', os.W_OK)}")
    
    await init_db()
    login_success = await wg_api.login()
    if login_success:
        logging.info("✅ Подключение к WireGuard успешно")
    
    # ✅ ИСПРАВЛЕНО: Используем SQLiteStorage вместо MemoryStorage
    storage = SqliteStorage("fsm_states.db")
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    
    logging.info("🚀 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
