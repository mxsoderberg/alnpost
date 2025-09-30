import os
import random
import asyncio
import logging
import shutil
import math
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv
import schedule
from aiohttp import web
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────
# Конфиг/переменные окружения
# ─────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TICK_TOKEN = os.getenv("TICK_TOKEN", "")

APP_BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://alnpost-bot.onrender.com").rstrip("/")

# Логи
logging.basicConfig(level=logging.INFO)

# Бот
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Часовой пояс Риги
TZ_RIGA = ZoneInfo("Europe/Riga")

# ─────────────────────────────────────────────────────────────
# Глобальные структуры
# ─────────────────────────────────────────────────────────────
material_pairs = []
PUBLICATIONS_PER_DAY = 2

scheduled_tasks = []
_freq_lock = asyncio.Lock()

# Пути к папкам
base_path = os.path.dirname(os.path.abspath(__file__))
materials_folder = os.path.join(base_path, "materials")
pending_folder = os.path.join(base_path, "wait")
archive_folder = os.path.join(base_path, "arch")

# Создаем необходимые папки
os.makedirs(materials_folder, exist_ok=True)
os.makedirs(pending_folder, exist_ok=True)
os.makedirs(archive_folder, exist_ok=True)

is_test_mode = False
original_material_pairs = []

# ─────────────────────────────────────────────────────────────
# Время и утилиты
# ─────────────────────────────────────────────────────────────
def get_current_time() -> datetime:
    return datetime.now(tz=TZ_RIGA)

def describe_part_of_day(dt_local: datetime) -> str:
    h = dt_local.hour
    if 6 <= h <= 11:
        return "🌅 Утро"
    elif 12 <= h <= 17:
        return "☀️ День"
    elif 18 <= h <= 23:
        return "🌆 Вечер"
    else:
        return "🌙 Ночь"

def random_time(start_hour, end_hour):
    hour = random.randint(start_hour, end_hour)
    minute = random.randint(0, 59)
    return f"{hour:02d}:{minute:02d}"

# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📊 Статистика"), types.KeyboardButton(text="📅 Расписание")],
            [types.KeyboardButton(text="⏰ Следующие"), types.KeyboardButton(text="📋 Все публикации")],
            [types.KeyboardButton(text="🔄 Перезагрузить"), types.KeyboardButton(text="⏹ Остановить")],
            [types.KeyboardButton(text="⏸ Пауза"), types.KeyboardButton(text="▶️ Продолжить")],
            [types.KeyboardButton(text="🗑 Очистить очередь"), types.KeyboardButton(text="🧹 Полная очистка")],
            [types.KeyboardButton(text="⚙️ Настройки"), types.KeyboardButton(text="🧪 Тест (10 сек/1 мин)")],
        ],
        resize_keyboard=True
    )
    return keyboard

# ─────────────────────────────────────────────────────────────
# Работа с очередью/файлами
# ─────────────────────────────────────────────────────────────
def refresh_material_queue():
    global material_pairs
    valid_pairs = []
    removed_count = 0
    for image_path, text_path in material_pairs:
        if os.path.exists(image_path) and os.path.exists(text_path):
            valid_pairs.append((image_path, text_path))
        else:
            logging.warning(f"Удалена неактуальная пара: {image_path}, {text_path}")
            removed_count += 1
    material_pairs = valid_pairs
    if removed_count > 0:
        logging.info(f"Очередь обновлена: удалено {removed_count}, осталось: {len(material_pairs)}")

def load_and_move_materials():
    global material_pairs
    logging.info("=== ЗАГРУЗКА МАТЕРИАЛОВ ===")
    material_pairs = []
    
    # Сначала wait
    wait_files = os.listdir(pending_folder) if os.path.exists(pending_folder) else []
    wait_images = [f for f in wait_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
    wait_texts = [f for f in wait_files if f.lower().endswith('.txt')]

    for image in wait_images:
        image_name = os.path.splitext(image)[0]
        text_file = next((txt for txt in wait_texts if os.path.splitext(txt)[0] == image_name), None)
        if text_file:
            image_path = os.path.join(pending_folder, image)
            text_path = os.path.join(pending_folder, text_file)
            if os.path.exists(image_path) and os.path.exists(text_path):
                material_pairs.append((image_path, text_path))

    # Если в wait пусто — берём из materials
    if not material_pairs:
        materials_files = os.listdir(materials_folder) if os.path.exists(materials_folder) else []
        images = [f for f in materials_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
        texts = [f for f in materials_files if f.lower().endswith('.txt')]

        for image in images:
            image_name = os.path.splitext(image)[0]
            text_file = next((txt for txt in texts if os.path.splitext(txt)[0] == image_name), None)
            if text_file:
                src_image = os.path.join(materials_folder, image)
                src_text = os.path.join(materials_folder, text_file)
                dst_image = os.path.join(pending_folder, image)
                dst_text = os.path.join(pending_folder, text_file)
                try:
                    if os.path.exists(src_image) and os.path.exists(src_text):
                        shutil.move(src_image, dst_image)
                        shutil.move(src_text, dst_text)
                        material_pairs.append((dst_image, dst_text))
                except Exception as e:
                    logging.error(f"Ошибка перемещения {image}: {e}")

    random.shuffle(material_pairs)
    logging.info(f"Загружено {len(material_pairs)} публикаций.")

def archive_sent_files(image_path, text_path):
    try:
        image_name = os.path.basename(image_path)
        text_name = os.path.basename(text_path)
        image_wait = os.path.join(pending_folder, image_name)
        text_wait = os.path.join(pending_folder, text_name)
        image_archive = os.path.join(archive_folder, image_name)
        text_archive = os.path.join(archive_folder, text_name)

        if os.path.exists(image_wait):
            shutil.move(image_wait, image_archive)
        if os.path.exists(text_wait):
            shutil.move(text_wait, text_archive)

        global material_pairs
        material_pairs = [(img, txt) for img, txt in material_pairs if img != image_path and txt != text_path]

    except Exception as e:
        logging.error(f"Ошибка архивирования: {e}", exc_info=True)

# ─────────────────────────────────────────────────────────────
# Отправка
# ─────────────────────────────────────────────────────────────
async def send_material_pair(image_path, text_path):
    try:
        if not os.path.exists(image_path):
            logging.error(f"Файл изображения не найден: {image_path}")
            return
        if not os.path.exists(text_path):
            logging.error(f"Файл текста не найден: {text_path}")
            return

        with open(text_path, 'r', encoding='utf-8') as f:
            caption = f.read().strip()

        await bot.send_photo(
            chat_id=CHAT_ID,
            photo=types.FSInputFile(image_path),
            caption=caption,
            disable_notification=True
        )
        logging.info(f"Отправлено: {os.path.basename(image_path)}")
        archive_sent_files(image_path, text_path)

    except Exception as e:
        logging.error(f"Ошибка отправки {image_path}: {e}", exc_info=True)

# ─────────────────────────────────────────────────────────────
# Планирование
# ─────────────────────────────────────────────────────────────
def schedule_posts():
    global scheduled_tasks
    logging.info("=== ПЛАНИРОВАНИЕ ПОСТОВ ===")
    
    try:
        schedule.clear('post')
    except Exception as e:
        logging.warning(f"Ошибка очистки расписания: {e}")

    scheduled_tasks.clear()

    if not material_pairs:
        logging.info("Нет публикаций для планирования")
        return

    now_local = get_current_time()
    anchor_date = now_local.date()

    def day_windows(freq: int):
        if freq <= 1:
            return [(9, 11, "утро")]
        if freq == 2:
            return [(8, 11, "утро"), (18, 21, "вечер")]
        if freq == 3:
            return [(8, 11, "утро"), (12, 17, "день"), (18, 21, "вечер")]
        return [(8, 10, "раннее утро"), (11, 13, "полдень"), (14, 17, "день"), (18, 21, "вечер")]

    windows = day_windows(PUBLICATIONS_PER_DAY)

    def build_future_slots(min_count: int):
        slots = []
        days_to_build = max(3, math.ceil(min_count / max(1, PUBLICATIONS_PER_DAY)) + 3)
        d = 0
        while len(slots) < min_count:
            date = anchor_date + timedelta(days=d)
            for (h1, h2, label) in windows[:PUBLICATIONS_PER_DAY]:
                hh, mm = map(int, random_time(h1, h2).split(":"))
                run_local = datetime(date.year, date.month, date.day, hh, mm, tzinfo=TZ_RIGA)
                if run_local > now_local:
                    slots.append((run_local, label))
            d += 1
            if d >= days_to_build and len(slots) < min_count:
                days_to_build += 3
        slots.sort(key=lambda x: x[0])
        return slots

    needed = len(material_pairs)
    future_slots = build_future_slots(needed)

    planned_count = 0
    for idx, (run_local, period_label) in enumerate(future_slots[:needed]):
        try:
            run_utc = run_local.astimezone(timezone.utc)
            note = describe_part_of_day(run_local)

            scheduled_tasks.append({
                "run_dt_utc": run_utc,
                "note": note,
                "material_index": idx
            })

            image_path, text_path = material_pairs[idx]

            def enqueue_once(img=image_path, txt=text_path):
                asyncio.create_task(send_material_pair(img, txt))
                return schedule.CancelJob

            time_str_local = run_local.strftime("%H:%M")
            job = schedule.every().day.at(time_str_local).do(enqueue_once).tag('post', f'idx-{idx}')
            job.next_run = run_utc.replace(tzinfo=None)

            logging.info(f"Публикация {idx+1}: {time_str_local}")
            planned_count += 1

        except Exception as e:
            logging.exception(f"Ошибка планирования {idx+1}: {e}")

    scheduled_tasks.sort(key=lambda x: x["run_dt_utc"])
    logging.info(f"Запланировано {planned_count} публикаций")

# ─────────────────────────────────────────────────────────────
# Отображение запланированных
# ─────────────────────────────────────────────────────────────
def get_scheduled_publications_info(limit: int = 50) -> list[str]:
    now_local = get_current_time()
    lines = []

    shown_count = 0
    for item in sorted(scheduled_tasks, key=lambda x: x["run_dt_utc"]):
        run_local = item["run_dt_utc"].astimezone(TZ_RIGA)
        if run_local <= now_local:
            continue
        note = item.get("note") or describe_part_of_day(run_local)
        line = f"• {run_local.strftime('%d.%m.%Y %H:%M')} ({note})"
        lines.append(line)
        shown_count += 1
        if shown_count >= limit:
            break

    return lines

# ─────────────────────────────────────────────────────────────
# Планировщик-луп
# ─────────────────────────────────────────────────────────────
async def run_scheduler_loop():
    logging.info("=== ЗАПУСК ПЛАНИРОВЩИКА ===")
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

# ─────────────────────────────────────────────────────────────
# Хендлеры команд/кнопок
# ─────────────────────────────────────────────────────────────
@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    welcome_text = (
        "🚀 <b>Бот для автоматических публикаций</b>\n\n"
        "Используй кнопки для управления ботом"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🔄 Перезагрузить")
async def button_reload(message: types.Message):
    logging.info("Перезагрузка материалов")
    try:
        schedule.clear('post')
    except Exception as e:
        logging.warning(f"Ошибка очистки расписания: {e}")
    global material_pairs
    material_pairs = []

    load_and_move_materials()
    pairs_count = len(material_pairs)
    if pairs_count > 0:
        schedule_posts()
        await message.answer(
            f"✅ Загружено {pairs_count} публикаций. "
            f"Запланировано {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} постов.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Нет публикаций.", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "📊 Статистика")
async def button_stats(message: types.Message):
    try:
        refresh_material_queue()
        materials_files = len([f for f in os.listdir(materials_folder) if os.path.isfile(os.path.join(materials_folder, f))]) if os.path.exists(materials_folder) else 0
        materials_pairs = materials_files // 2
        wait_files = len([f for f in os.listdir(pending_folder) if os.path.isfile(os.path.join(pending_folder, f))]) if os.path.exists(pending_folder) else 0
        wait_pairs = wait_files // 2
        arch_files = len([f for f in os.listdir(archive_folder) if os.path.isfile(os.path.join(archive_folder, f))]) if os.path.exists(archive_folder) else 0
        arch_pairs = arch_files // 2

        response = "📊 <b>Статистика:</b>\n\n"
        response += f"📥 materials: {materials_pairs} ({materials_files} файлов)\n"
        response += f"⏳ wait: {wait_pairs} ({wait_files} файлов)\n"
        response += f"📁 arch: {arch_pairs} ({arch_files} файлов)\n"
        response += f"📋 очередь: {len(material_pairs)} публикаций\n"
        response += f"📅 запланировано: {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} задач\n"

        await message.answer(response, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "📅 Расписание")
async def button_schedule(message: types.Message):
    refresh_material_queue()

    if not material_pairs:
        await message.answer("📭 Очередь пуста.", reply_markup=get_main_keyboard())
        return

    response = "📅 <b>Планирование:</b>\n\n"
    response += "📥 <b>В очереди:</b>\n"
    for i, (image_path, text_path) in enumerate(material_pairs[:15], 1):
        filename = os.path.basename(image_path)
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            if filename.lower().endswith(ext):
                filename = filename[:-len(ext)]
                break
        response += f"{i}. {filename}\n"

    response += f"\n📊 Всего: {len(material_pairs)} публикаций\n"

    lines = get_scheduled_publications_info(limit=50)
    if lines:
        response += "\n⏰ <b>Запланировано:</b>\n" + "\n".join(lines) + "\n"

    await message.answer(response, parse_mode="HTML", reply_markup=get_main_keyboard())

# ─────────────────────────────────────────────────────────────
# AIOHTTP endpoints + lifecycle
# ─────────────────────────────────────────────────────────────
async def on_startup(bot: Bot):
    logging.info("=== ЗАПУСК НА RENDER ===")
    
    # Очистка планировщика
    try:
        schedule.clear('post')
    except Exception as e:
        logging.error(f"Ошибка очистки планировщика: {e}", exc_info=True)

    # Установка вебхука
    WEBHOOK_URL = f"{APP_BASE_URL}/webhook"
    await bot.set_webhook(
        WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

    # Запуск планировщика
    asyncio.create_task(run_scheduler_loop())

async def on_shutdown(bot: Bot):
    logging.info("=== ОСТАНОВКА ===")
    await bot.session.close()

async def health(request: web.Request):
    return web.Response(text="OK")

async def tick(request: web.Request):
    if request.query.get("token") != TICK_TOKEN:
        return web.Response(status=403, text="forbidden")
    schedule.run_pending()
    return web.Response(text="tick")

def main():
    logging.info("=== ЗАПУСК НА RENDER ===")
    
    # Только режим вебхуков для Render
    port = int(os.environ.get("PORT", 10000))
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")

    app.router.add_get("/", lambda r: web.Response(text="Bot is running"))
    app.router.add_get("/health", health)
    app.router.add_get("/tick", tick)

    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()