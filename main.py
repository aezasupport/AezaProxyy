import subprocess
import sys

def install_dependencies():
    """Устанавливает зависимости если их нет"""
    try:
        import aiosqlite
        import aiohttp
        import aiogram
        print("✅ Все модули установлены")
    except ImportError:
        print("📦 Устанавливаем зависимости...")
        subprocess.check_call([
            sys.executable, 
            "-m", 
            "pip", 
            "install", 
            "aiogram>=3.0.0",
            "aiosqlite>=0.19.0",
            "aiohttp>=3.8.0"
        ])

# Устанавливаем перед импортами
install_dependencies()

# Теперь импорты
import asyncio
import logging
import aiohttp
import aiosqlite
# ... остальные импорты
import os
import json
import asyncio
import logging
import aiohttp
import aiosqlite
import time
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime, timedelta

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = "8751382520:AAGP0pP2ZgtZImjrjHDXjBmlBfxtC35JWlA"
WG_PANEL_URL = "http://89.208.104.215:51821"
WG_PASSWORD = "admin123"
ADMIN_ID = 6846734926

CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "tariffs": {
        "1_month": {"name": "1 месяц", "stars": 150, "days": 30},
        "3_months": {"name": "3 месяца", "stars": 400, "days": 90},
        "6_months": {"name": "6 месяцев", "stars": 700, "days": 180},
    },
    "welcome_text": "Привет, {name}! 👋\nЯ бот для продажи надежных VPN-конфигураций WireGuard.",
    "purchase_success_text": "✅ <b>Оплата прошла успешно!</b>\n\n🎉 Тариф '{tariff_name}' активирован\n📅 Действует до: {expiry_date}\n\n📥 Скачайте конфигурацию ниже",
    "help_text": "📖 <b>Как пользоваться:</b>\n\n1. Выберите тариф в разделе 'Купить подписку'\n2. Оплатите звездами Telegram\n3. Скачайте файл конфигурации\n4. Установите приложение WireGuard\n5. Импортируйте файл в приложение\n6. Подключайтесь!\n\nВопросы: @nocaponeNGG",
    "referral_text": " <b>Приглашай друзей и получай бонусы!</b>\n\n💰 <b>Ты получаешь:</b> {bonus}⭐ за каждого друга\n🎁 <b>Друг получает:</b> скидку на первую покупку\n\n🔗 <b>Твоя ссылка:</b>\n<code>{referral_link}</code>\n\nНажми «Поделиться» чтобы отправить ссылку другу!",
    "referral_bonus_days": 3,
    "admin_id": ADMIN_ID
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
router = Router()

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

# ================= УПРАВЛЕНИЕ НАСТРОЙКАМИ =================
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {**DEFAULT_CONFIG, **config}
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def get_config():
    return load_config()

def update_tariff(tariff_key, **kwargs):
    config = load_config()
    if tariff_key in config['tariffs']:
        config['tariffs'][tariff_key].update(kwargs)
        save_config(config)
        return True
    return False

def update_setting(key, value):
    config = load_config()
    config[key] = value
    save_config(config)
    return True

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                wg_client_name TEXT,
                wg_client_id TEXT,
                subscription_start TEXT,
                subscription_end TEXT,
                is_active INTEGER DEFAULT 0
            )
        """)
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
            logging.info("✅ Добавлена колонка referral_code")
        except Exception:
            logging.info("ℹ️ Колонка referral_code уже существует")
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            logging.info("✅ Добавлена колонка referred_by")
        except Exception:
            logging.info("ℹ️ Колонка referred_by уже существует")
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0")
            logging.info("✅ Добавлена колонка referrals_count")
        except Exception:
            logging.info("ℹ️ Колонка referrals_count уже существует")
        
        await db.execute("""
            UPDATE users 
            SET referral_code = 'ref' || tg_id || '0000'
            WHERE referral_code IS NULL OR referral_code = ''
        """)
        logging.info("✅ Обновлены старые пользователи (добавлен referral_code)")
        
        await db.commit()
        logging.info("✅ База данных инициализирована")

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
    """Гарантирует наличие referral_code у пользователя"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT referral_code FROM users WHERE tg_id = ?", (tg_id,))
            user = await cursor.fetchone()
            
            if user and user['referral_code']:
                return user['referral_code']
            
            # Генерируем новый referral_code
            referral_code = f"ref{tg_id}0000"
            await db.execute("UPDATE users SET referral_code = ? WHERE tg_id = ?", (referral_code, tg_id))
            await db.commit()
            logging.info(f"✅ Сгенерирован referral_code {referral_code} для пользователя {tg_id}")
            return referral_code
    except Exception as e:
        logging.error(f"Ошибка ensure_referral_code: {e}")
        return f"ref{tg_id}0000"

async def create_user(tg_id: int, referred_by: int = None):
    """Создает пользователя или возвращает существующего"""
    try:
        async with aiosqlite.connect("bot.db") as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
            existing = await cursor.fetchone()
            
            if existing:
                logging.info(f"ℹ️ Пользователь {tg_id} уже существует")
                return {'new_user': False, 'existing_user': True}
            
            referral_code = f"ref{tg_id}{int(time.time()) % 10000}"
            
            await db.execute(
                "INSERT INTO users (tg_id, referral_code, referred_by, referrals_count, balance) VALUES (?, ?, ?, 0, 0)",
                (tg_id, referral_code, referred_by)
            )
            
            logging.info(f"✅ Создан новый пользователь {tg_id} с referral_code: {referral_code}")
            
            if referred_by:
                await db.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = ?", (referred_by,))
                
                config = get_config()
                bonus = config.get('referral_bonus_days', 3)
                await db.execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (bonus, referred_by))
                
                cursor = await db.execute("SELECT balance FROM users WHERE tg_id = ?", (referred_by,))
                result = await cursor.fetchone()
                new_balance = result['balance'] if result else bonus
                
                logging.info(f"✅ Реферальный бонус: {bonus}⭐ пользователю {referred_by}. Новый баланс: {new_balance}⭐")
                
                await db.commit()
                return {
                    'new_user': True,
                    'referred_by': referred_by,
                    'bonus': bonus,
                    'new_balance': new_balance
                }
            
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
            async with session.post(
                f"{self.base_url}/api/wireguard/client", 
                json={"name": name},
                cookies=self.cookies
            ) as resp:
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
            async with session.get(
                f"{self.base_url}/api/wireguard/client/{client_id}/configuration",
                cookies=self.cookies
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None
        except Exception as e:
            logging.error(f"WireGuard get_config error: {e}")
            return None

wg_api = WireGuardAPI(WG_PANEL_URL, WG_PASSWORD)

# ================= КЛАВИАТУРЫ =================
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_wg")],
        [InlineKeyboardButton(text="📱 Моя подписка", callback_data="my_subscription")],
        [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="referral")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text=" Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text=" Назад", callback_data="start")]
    ])

def get_tariff_keyboard():
    config = get_config()
    keyboard = []
    for key, tariff in config['tariffs'].items():
        keyboard.append([InlineKeyboardButton(text=f"{tariff['name']} - {tariff['stars']} ", callback_data=f"tariff_{key}")])
    keyboard.append([InlineKeyboardButton(text=" Назад", callback_data="start")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Редактировать тарифы", callback_data="admin_edit_tariffs_menu")],
        [InlineKeyboardButton(text="📝 Текст приветствия", callback_data="admin_edit_welcome_text")],
        [InlineKeyboardButton(text="📝 Текст покупки", callback_data="admin_edit_purchase_text")],
        [InlineKeyboardButton(text="📝 Текст помощи", callback_data="admin_edit_help_text")],
        [InlineKeyboardButton(text="⭐ Реферальный бонус", callback_data="admin_edit_referral_bonus")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]
    ])

def get_edit_tariffs_keyboard():
    config = get_config()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 месяц: {config['tariffs']['1_month']['stars']}⭐ / {config['tariffs']['1_month']['days']}дн", callback_data="admin_edit_1month")],
        [InlineKeyboardButton(text=f"3 месяца: {config['tariffs']['3_months']['stars']}⭐ / {config['tariffs']['3_months']['days']}дн", callback_data="admin_edit_3months")],
        [InlineKeyboardButton(text=f"6 месяцев: {config['tariffs']['6_months']['stars']}⭐ / {config['tariffs']['6_months']['days']}дн", callback_data="admin_edit_6months")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_settings")]
    ])

def get_edit_tariff_options_keyboard(tariff_key):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"admin_change_price_{tariff_key}")],
        [InlineKeyboardButton(text="📅 Изменить дни", callback_data=f"admin_change_days_{tariff_key}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_edit_tariffs_menu")]
    ])

# ================= ОБРАБОТЧИКИ =================
@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    try:
        logging.info(f"📨 /start от {message.from_user.id}")
        
        args = message.text.split()
        referral_code = args[1] if len(args) > 1 else None
        
        referred_by = None
        if referral_code:
            logging.info(f"🔍 Найден referral_code: {referral_code}")
            referrer = await get_user_by_referral_code(referral_code)
            if referrer and referrer['tg_id'] != message.from_user.id:
                referred_by = referrer['tg_id']
                logging.info(f" Пользователь {message.from_user.id} пришел от реферала {referred_by}")
            else:
                logging.info(f"⚠️ Реферал не найден или это сам пользователь")
        
        existing_user = await get_user(message.from_user.id)
        referral_info = await create_user(message.from_user.id, referred_by=referred_by)
        
        # СНАЧАЛА отправляем уведомления о реферале
        if referral_info and referral_info.get('existing_user'):
            if referred_by:
                referrer_user = await get_user(referred_by)
                referrer_name = referrer_user.get('wg_client_name', f"ID {referred_by}") if referrer_user else "неизвестно"
                
                await message.answer(
                    f"ℹ️ <b>Вы уже зарегистрированы в боте!</b>\n\n"
                    f"Вы перешли по реферальной ссылке пользователя: {referrer_name}\n"
                    f"Но так как вы уже в боте, бонус не начислен.\n\n"
                    f"Приглашайте друзей сами и получайте бонусы!",
                    parse_mode="HTML"
                )
                logging.info(f"ℹ️ Пользователь {message.from_user.id} уже в боте, пришел от {referred_by}")
                return
        
        if referral_info and referral_info.get('new_user') and referral_info.get('referred_by'):
            bonus = referral_info['bonus']
            
            # Получаем баланс пригласившего
            referrer_data = await get_user(referred_by)
            referrer_balance = referrer_data.get('balance', bonus) if referrer_data else bonus
            
            logging.info(f"📨 Отправка уведомлений: новый={message.from_user.id}, пригласивший={referred_by}, бонус={bonus}")
            
            # 1. Уведомление НОВОМУ пользователю (показываем bonus)
            await message.answer(
                f"🎁 <b>Вам начислен бонус!</b>\n\n"
                f"Вы зарегистрировались по реферальной ссылке!\n"
                f"💰 Вам начислено {bonus}⭐\n"
                f"💵 Ваш баланс: {bonus}⭐\n\n"
                f"Приглашайте друзей и получайте больше бонусов!",
                parse_mode="HTML"
            )
            
            # 2. Уведомление ПРИГЛАСИВШЕМУ
            try:
                username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{message.from_user.id}"
                await bot.send_message(
                    referred_by,
                    f"🎉 <b>Новый реферал!</b>\n\n"
                    f"Пользователь {username} зарегистрировался по вашей ссылке!\n\n"
                    f" Вам начислено {bonus}⭐\n"
                    f"💵 Ваш баланс: {referrer_balance}⭐",
                    parse_mode="HTML"
                )
                logging.info(f"✅ Уведомление о реферале отправлено пользователю {referred_by}")
            except Exception as e:
                logging.error(f"❌ Не удалось отправить уведомление о реферале пользователю {referred_by}: {e}")
        
        # ТЕПЕРЬ показываем меню
        config = get_config()
        welcome_text = config['welcome_text'].format(name=message.from_user.first_name)
        
        if message.from_user.id == ADMIN_ID:
            await message.answer(
                "Привет, Админ! 👋\nДобро пожаловать в панель управления WireGuard ботом.",
                reply_markup=get_admin_keyboard()
            )
        else:
            await message.answer(welcome_text, reply_markup=get_main_keyboard())
                    
    except Exception as e:
        logging.error(f"❌ Ошибка cmd_start: {e}", exc_info=True)
        await message.answer("Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data == "start")
async def cb_start(callback: CallbackQuery):
    try:
        config = get_config()
        welcome_text = config['welcome_text'].format(name=callback.from_user.first_name)
        await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_start: {e}")

@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    try:
        user = await get_user(callback.from_user.id)
        if not user:
            await create_user(callback.from_user.id)
            user = await get_user(callback.from_user.id)
        
        # Используем ensure_referral_code для получения постоянного кода
        referral_code = await ensure_referral_code(callback.from_user.id)
        
        user = await get_user(callback.from_user.id)
        balance = user.get('balance', 0) if user else 0
        referrals_count = user.get('referrals_count', 0) if user else 0
        
        config = get_config()
        bonus = config.get('referral_bonus_days', 3)
        
        bot_info = await callback.bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start={referral_code}"
        
        referral_text = config.get('referral_text', DEFAULT_CONFIG['referral_text']).format(
            bonus=bonus,
            referral_link=referral_link
        )
        
        stats_text = (
            f"📊 <b>Ваша статистика:</b>\n"
            f"💵 Баланс: {balance}⭐\n"
            f"👥 Приглашено: {referrals_count}\n"
            f" За друга: {bonus}⭐\n\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" Поделиться!", url=f"https://t.me/share/url?url={referral_link}&text=Приглашаю тебя в VPN бот!")]
        ])
        
        await callback.message.answer(
            stats_text + referral_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"❌ Ошибка cb_referral: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)

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
        await callback.message.answer(
            "⚙️ <b>Настройки бота</b>\n\nВыберите что хотите изменить:",
            reply_markup=get_admin_settings_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_settings: {e}")

@router.callback_query(F.data == "admin_edit_referral_bonus")
async def cb_admin_edit_referral_bonus(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        
        config = get_config()
        current_bonus = config.get('referral_bonus_days', 3)
        
        await callback.message.answer(
            f"⭐ <b>Реферальный бонус</b>\n\n"
            f"Текущий бонус: <b>{current_bonus}⭐</b> за каждого друга\n\n"
            f"Отправьте новое количество звезд:\n\n"
            f"/cancel для отмены",
            parse_mode="HTML"
        )
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
            await message.answer("❌ Бонус не может быть отрицательным!")
            return
        
        update_setting('referral_bonus_days', new_bonus)
        await message.answer(
            f"✅ Реферальный бонус изменен на {new_bonus}⭐\n\n"
            f"Теперь за каждого друга будет начисляться {new_bonus}⭐",
            reply_markup=get_admin_settings_keyboard()
        )
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
        total_balance = sum(u.get('balance', 0) for u in users)
        
        config = get_config()
        
        text = (
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 <b>Пользователи:</b>\n"
            f"   Всего: {total_users}\n"
            f"   Активных: {active_count}\n\n"
            f"👥 <b>Рефералы:</b>\n"
            f"   Всего приглашений: {total_referrals}\n\n"
            f"💰 <b>Балансы:</b>\n"
            f"   Всего выдано: {total_balance}⭐\n\n"
            f"💰 <b>Тарифы:</b>\n"
        )
        
        for key, tariff in config['tariffs'].items():
            text += f"   {tariff['name']}: {tariff['stars']}⭐ / {tariff['days']}дн\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]
        ])
        
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
        await callback.message.answer(
            "💰 <b>Редактирование тарифов</b>\n\nВыберите тариф:",
            reply_markup=get_edit_tariffs_keyboard(),
            parse_mode="HTML"
        )
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
        await callback.message.answer(
            "Выберите что изменить для тарифа:",
            reply_markup=get_edit_tariff_options_keyboard(tariff_key),
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_edit_tariff: {e}")

@router.callback_query(F.data == "admin_edit_welcome_text")
async def cb_admin_edit_welcome(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        
        config = get_config()
        await callback.message.answer(
            f" <b>Текущий текст приветствия:</b>\n\n<code>{config['welcome_text']}</code>\n\n"
            f"Отправьте новый текст (используйте {{name}} для имени):\n\n/cancel для отмены",
            parse_mode="HTML"
        )
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
        
        config = get_config()
        await callback.message.answer(
            f"📝 <b>Текущий текст покупки:</b>\n\n<code>{config['purchase_success_text']}</code>\n\n"
            f"Отправьте новый текст (HTML, используйте {{tariff_name}} и {{expiry_date}})\n\n/cancel для отмены",
            parse_mode="HTML"
        )
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
        
        config = get_config()
        await callback.message.answer(
            f"📝 <b>Текущий текст помощи:</b>\n\n<code>{config['help_text']}</code>\n\n"
            f"Отправьте новый текст (HTML формат)\n\n/cancel для отмены",
            parse_mode="HTML"
        )
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
        await callback.message.answer("📅 Введите количество дней:")
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_admin_change_days: {e}")

@router.message(AdminEditStates.editing_welcome_text, F.text)
async def process_edit_welcome(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    update_setting('welcome_text', message.text)
    await message.answer("✅ Текст приветствия обновлен!", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@router.message(AdminEditStates.editing_purchase_text, F.text)
async def process_edit_purchase(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    update_setting('purchase_success_text', message.text)
    await message.answer("✅ Текст покупки обновлен!", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@router.message(AdminEditStates.editing_help_text, F.text)
async def process_edit_help(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    update_setting('help_text', message.text)
    await message.answer("✅ Текст помощи обновлен!", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@router.message(AdminEditStates.editing_price_1month, F.text)
async def process_edit_price_1month(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        update_tariff('1_month', stars=new_price)
        await message.answer(f"✅ Цена для 1 месяца изменена на {new_price}⭐", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_price_3months, F.text)
async def process_edit_price_3months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        update_tariff('3_months', stars=new_price)
        await message.answer(f"✅ Цена для 3 месяцев изменена на {new_price}⭐", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_price_6months, F.text)
async def process_edit_price_6months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = int(message.text)
        update_tariff('6_months', stars=new_price)
        await message.answer(f"✅ Цена для 6 месяцев изменена на {new_price}⭐", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_1month, F.text)
async def process_edit_days_1month(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        update_tariff('1_month', days=new_days)
        await message.answer(f"✅ Срок для 1 месяца изменен на {new_days} дней", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_3months, F.text)
async def process_edit_days_3months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        update_tariff('3_months', days=new_days)
        await message.answer(f"✅ Срок для 3 месяцев изменен на {new_days} дней", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.message(AdminEditStates.editing_days_6months, F.text)
async def process_edit_days_6months(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_days = int(message.text)
        update_tariff('6_months', days=new_days)
        await message.answer(f"✅ Срок для 6 месяцев изменен на {new_days} дней", reply_markup=get_edit_tariffs_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число!")

@router.callback_query(F.data == "buy_wg")
async def cb_buy(callback: CallbackQuery):
    try:
        text = "💫 Оплата производится звездами Telegram (Telegram Stars)\n\nВыберите тариф:"
        await callback.message.edit_text(text, reply_markup=get_tariff_keyboard())
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка cb_buy: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery, state: FSMContext):
    try:
        tariff_key = callback.data.replace("tariff_", "")
        config = get_config()
        tariff = config['tariffs'][tariff_key]
        
        await state.set_state(PurchaseStates.selecting_tariff)
        await state.update_data(tariff_key=tariff_key, stars=tariff['stars'], days=tariff['days'], name=tariff['name'])
        
        await callback.message.answer(
            f"<b>Покупка тарифа '{tariff['name']}'</b>\n\n"
            f"💰 Стоимость: {tariff['stars']} ⭐\n"
            f"📅 Срок: {tariff['days']} дней\n\n"
            f"Для подтверждения нажмите кнопку ниже",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💳 Оплатить {tariff['stars']} ⭐", callback_data=f"pay_{tariff_key}")],
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="buy_wg")]
            ]),
            parse_mode="HTML"
        )
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
            await callback.answer("Сессия истекла. Начните сначала.", show_alert=True)
            return
            
        config = get_config()
        tariff = config['tariffs'][tariff_key]
        
        await callback.message.answer(
            f"✅ <b>Тестовая оплата прошла!</b>\n\n"
            f"🎉 Тариф '{tariff['name']}' активирован\n"
            f"📅 Действует до: {(datetime.now() + timedelta(days=tariff['days'])).strftime('%d.%m.%Y')}",
            parse_mode="HTML"
        )
        
        # Получаем username для имени клиента
        try:
            user_chat = await callback.bot.get_chat(callback.from_user.id)
            username = user_chat.username
            if username:
                client_name = f"{username}"  # Используем username
            else:
                client_name = f"tg{callback.from_user.id}"  # Если нет username, используем tg_id
        except Exception:
            client_name = f"tg{callback.from_user.id}"
        
        # Добавляем timestamp чтобы имя было уникальным
        client_name = f"{client_name}_{int(time.time())}"
        
        logging.info(f"🔧 Создание клиента {client_name}...")
        
        client_id = await wg_api.create_client(client_name)
        
        if client_id:
            config_text = await wg_api.get_config(client_id)
            if config_text:
                await update_subscription(callback.from_user.id, client_name, client_id, tariff['days'])
                
                file_name = f"wg_{callback.from_user.id}.conf"
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(config_text)
                
                await callback.message.answer_document(FSInputFile(file_name, filename=file_name))
                os.remove(file_name)
        
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Ошибка cb_pay: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(callback: CallbackQuery):
    try:
        user = await get_user(callback.from_user.id)
        
        if not user:
            await callback.message.answer(
                " <b>У вас нет активной подписки</b>\n\n"
                "Приобретите подписку в разделе 'Купить подписку'",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        is_active = user.get('is_active', 0)
        wg_client_id = user.get('wg_client_id')
        
        if not is_active or not wg_client_id:
            await callback.message.answer(
                "📭 <b>У вас нет активной подписки</b>\n\n"
                "Приобретите подписку в разделе 'Купить подписку'",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        end_date = datetime.strptime(user['subscription_end'], "%Y-%m-%d %H:%M:%S")
        remaining = end_date - datetime.now()
        
        if remaining.total_seconds() <= 0:
            await callback.message.answer(
                "⚠️ <b>Ваша подписка истекла!</b>\n\n"
                "Приобретите новую подписку",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        config_text = await wg_api.get_config(wg_client_id)
        if not config_text:
            await callback.message.answer("❌ Не удалось получить конфигурацию.")
            await callback.answer()
            return
        
        file_name = f"wg_{user['tg_id']}.conf"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(config_text)
        
        days = remaining.days
        hours = remaining.seconds // 3600
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Перенести ключи в приложение", callback_data=f"share_config_{wg_client_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
        ])
        
        await callback.message.answer(
            f"📱 <b>Ваша подписка</b>\n\n"
            f"✅ Статус: Активна\n"
            f"📅 Осталось: {days} дн. {hours} ч.\n"
            f"⏰ Истекает: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📥 Ваша конфигурация:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
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
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" Назад", callback_data="my_subscription")]
        ])
        
        await callback.message.answer_document(
            FSInputFile(file_name, filename=file_name),
            caption="📱 Отправьте этот файл в приложение WireGuard",
            reply_markup=keyboard
        )
        os.remove(file_name)
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Ошибка cb_share_config: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    try:
        config = get_config()
        help_text = config.get('help_text', DEFAULT_CONFIG['help_text'])
        await callback.message.answer(help_text, parse_mode="HTML", reply_markup=get_main_keyboard())
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
        text = f"👥 <b>Всего пользователей: {len(users)}</b>\n\n"
        
        for user in users:
            status = "✅" if user.get('is_active') else "❌"
            end = (user.get('subscription_end') or "Нет")[:10]
            name = user.get('wg_client_name') or "Нет"
            referrals = user.get('referrals_count', 0)
            balance = user.get('balance', 0)
            
            # Получаем username
            try:
                user_chat = await callback.bot.get_chat(user['tg_id'])
                username = f"@{user_chat.username}" if user_chat.username else "❌ Нет"
                full_name = user_chat.first_name or "Нет"
            except Exception:
                username = "❌ Нет"
                full_name = "Нет"
            
            text += f"{status} <b>{full_name}</b> {username}\n"
            text += f"   ID: <code>{user['tg_id']}</code>\n"
            text += f"   WG: {name} | До: {end}\n"
            text += f"   Рефералы: {referrals} | Баланс: {balance}⭐\n\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_start")]
        ])
        
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
    
    await callback.message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки:\n\n"
        "/cancel для отмены",
        parse_mode="HTML"
    )
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
    
    await message.answer(f"✅ Рассылка завершена!\n Отправлено: {success}")
    await state.clear()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())

# ================= ЗАПУСК =================
async def main():
    await init_db()
    
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
    
    login_success = await wg_api.login()
    if login_success:
        logging.info("✅ Подключение к WireGuard успешно")
    
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    logging.info("🚀 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
