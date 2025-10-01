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

# Часовые пояса
TZ_LOCAL = ZoneInfo("Europe/Riga")  # Пользовательский TZ с учетом DST
SERVER_TZ = datetime.now().astimezone().tzinfo  # TZ сервера

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

os.makedirs(materials_folder, exist_ok=True)
os.makedirs(pending_folder, exist_ok=True)

is_test_mode = False
original_material_pairs = []

# ─────────────────────────────────────────────────────────────
# Время и утилиты
# ─────────────────────────────────────────────────────────────
def get_current_time() -> datetime:
    return datetime.now(tz=TZ_LOCAL)

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
            [types.KeyboardButton(text="🔄 Перезагрузить"), types.KeyboardButton(text="⏹ Остановить")],
            [types.KeyboardButton(text="⏸ Пауза"), types.KeyboardButton(text="▶️ Продолжить")],
            [types.KeyboardButton(text="🧹 Полная очистка"), types.KeyboardButton(text="⚙️ Настройки")],
            [types.KeyboardButton(text="🧪 Тест (5 сек)")],
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
            logging.warning(f"Удалена пара: {image_path}, {text_path}")
            removed_count += 1
    material_pairs = valid_pairs
    if removed_count > 0:
        logging.info(f"Очередь обновлена: удалено {removed_count}, осталось: {len(material_pairs)}")

def load_and_move_materials():
    global material_pairs
    logging.info("=== ЗАГРУЗКА МАТЕРИАЛОВ ===")
    material_pairs = []
    
    # Проверяем папку wait (файлы, которые уже в очереди)
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
                        logging.info(f"Перемещено: {image} + {text_file}")
                except Exception as e:
                    logging.error(f"Ошибка перемещения {image}: {e}")

    random.shuffle(material_pairs)
    logging.info(f"Загружено {len(material_pairs)} публикаций.")

def remove_sent_files(image_path, text_path):
    """Удаляет опубликованные файлы из папки wait"""
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
            logging.info(f"Удален: {os.path.basename(image_path)}")
        if os.path.exists(text_path):
            os.remove(text_path)
            logging.info(f"Удален: {os.path.basename(text_path)}")

        global material_pairs
        material_pairs = [(img, txt) for img, txt in material_pairs if img != image_path and txt != text_path]

    except Exception as e:
        logging.error(f"Ошибка удаления: {e}", exc_info=True)

# ─────────────────────────────────────────────────────────────
# Отправка
# ─────────────────────────────────────────────────────────────
async def send_material_pair(image_path, text_path):
    try:
        if not os.path.exists(image_path):
            logging.error(f"Файл не найден: {image_path}")
            return
        if not os.path.exists(text_path):
            logging.error(f"Файл не найден: {text_path}")
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
        remove_sent_files(image_path, text_path)

    except Exception as e:
        logging.error(f"Ошибка отправки {image_path}: {e}", exc_info=True)

# ─────────────────────────────────────────────────────────────
# Планирование
# ─────────────────────────────────────────────────────────────
def schedule_posts():
    global scheduled_tasks
    logging.info("=== ПЛАНИРОВАНИЕ ===")
    
    # Очищаем старые задачи
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.warning(f"Ошибка очистки: {e}")

    scheduled_tasks.clear()

    if not material_pairs:
        logging.info("Нет публикаций")
        return

    # Диагностика часовых поясов
    logging.info("Server TZ: %s, now=%s", SERVER_TZ, datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"))
    logging.info("User   TZ: %s, now=%s", TZ_LOCAL, datetime.now(TZ_LOCAL).strftime("%Y-%m-%d %H:%M:%S %Z"))

    now_local = get_current_time()
    anchor_date = now_local.date()

    def day_windows(freq: int):
        if freq <= 1:
            return [(9, 11, "утро")]  # 9-11 утра
        if freq == 2:
            return [(8, 11, "утро"), (18, 21, "вечер")]  # Утро и вечер
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
                run_local = datetime(date.year, date.month, date.day, hh, mm, tzinfo=TZ_LOCAL)
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
            # Преобразуем в локальное время сервера (schedule ждёт наивное "локальное")
            run_server = run_local.astimezone(SERVER_TZ)
            
            # Готовим задачу как одноразовую
            image_path, text_path = material_pairs[idx]
            
            def create_job(img_path, txt_path, task_idx):
                def job_func():
                    asyncio.create_task(send_material_pair(img_path, txt_path))
                    # Помечаем задачу как опубликованную
                    for task in scheduled_tasks:
                        if task["material_index"] == task_idx:
                            task["published"] = True
                            logging.info(f"Помечена как опубликованная задача {task_idx}")
                            break
                    return schedule.CancelJob
                return job_func

            job = schedule.every().day.do(
                create_job(image_path, text_path, idx)
            ).tag('post', f'idx-{idx}')

            # Абсолютный момент старта в локальном времени сервера (наивный)
            job.next_run = run_server.replace(tzinfo=None)

            # Для UI и логов сохраняем UTC
            run_utc = run_server.astimezone(timezone.utc)
            scheduled_tasks.append({
                "run_dt_utc": run_utc,
                "note": describe_part_of_day(run_local),
                "material_index": idx,
                "published": False
            })

            logging.info(
                "План: local=%s | server=%s | utc=%s",
                run_local.strftime("%Y-%m-%d %H:%M %Z"),
                run_server.strftime("%Y-%m-%d %H:%M %Z"),
                run_utc.strftime("%Y-%m-%d %H:%M %Z"),
            )
            planned_count += 1

        except Exception as e:
            logging.exception(f"Ошибка {idx+1}: {e}")

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
        run_local = item["run_dt_utc"].astimezone(TZ_LOCAL)
        
        # Пропускаем уже прошедшие даты
        if run_local <= now_local:
            continue
            
        note = item.get("note") or describe_part_of_day(run_local)
        
        # Проверяем, опубликован ли пост
        if item.get("published", False):
            line = f"• {run_local.strftime('%d.%m.%Y %H:%M')} ({note}) [опубликовано]"
        else:
            line = f"• {run_local.strftime('%d.%m.%Y %H:%M')} ({note})"
            
        lines.append(line)
        shown_count += 1
        if shown_count >= limit:
            break

    return lines

# ─────────────────────────────────────────────────────────────
# Планировщик
# ─────────────────────────────────────────────────────────────
async def run_scheduler_loop():
    logging.info("=== ПЛАНИРОВЩИК ===")
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
        "Используй кнопки для управления:\n"
        "• <b>📊 Статистика</b> - общая информация\n"
        "• <b>📅 Расписание</b> - планирование публикаций\n"
        "• <b>🔄 Перезагрузить</b> - обновить материалы\n"
        "• <b>⏹ Остановить</b> - отменить все публикации\n"
        "• <b>⏸ Пауза</b> - приостановить публикации\n"
        "• <b>▶️ Продолжить</b> - возобновить публикации\n"
        "• <b>🧹 Полная очистка</b> - удалить ВСЕ файлы\n"
        "• <b>⚙️ Настройки</b> - частота публикаций\n"
        "• <b>🧪 Тест (5 сек)</b> - тестовая публикация"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

    load_and_move_materials()
    if material_pairs:
        schedule_posts()

@dp.message(lambda message: message.text == "📊 Статистика")
async def button_stats(message: types.Message):
    try:
        refresh_material_queue()
        materials_files = len([f for f in os.listdir(materials_folder) if os.path.isfile(os.path.join(materials_folder, f))]) if os.path.exists(materials_folder) else 0
        materials_pairs = materials_files // 2
        wait_files = len([f for f in os.listdir(pending_folder) if os.path.isfile(os.path.join(pending_folder, f))]) if os.path.exists(pending_folder) else 0
        wait_pairs = wait_files // 2

        response = "📊 <b>Статистика:</b>\n\n"
        response += f"📥 materials: {materials_pairs} ({materials_files} файлов)\n"
        response += f"⏳ wait: {wait_pairs} ({wait_files} файлов)\n"
        response += f"📋 очередь: {len(material_pairs)} публикаций\n"
        response += f"📅 запланировано: {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} задач\n"
        response += f"⚙️ частота: {PUBLICATIONS_PER_DAY} постов/день\n"

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
    response += "⏳ <b>В очереди:</b>\n"
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
    else:
        response += "\n⏰ Нет запланированных публикаций\n"

    await message.answer(response, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🔄 Перезагрузить")
async def button_reload(message: types.Message):
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.warning(f"Ошибка очистки: {e}")
    global material_pairs
    material_pairs = []

    load_and_move_materials()
    if material_pairs:
        schedule_posts()
        await message.answer(
            f"✅ Загружено {len(material_pairs)} публикаций. "
            f"Запланировано {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} постов.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ Нет публикаций.", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "⏹ Остановить")
async def button_stop(message: types.Message):
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.warning(f"Ошибка очистки: {e}")
    global material_pairs
    cleared_count = len(material_pairs)
    material_pairs = []
    await message.answer(
        f"⏹ Остановлено!\nОчередь очищена: {cleared_count} публикаций",
        reply_markup=get_main_keyboard()
    )

@dp.message(lambda message: message.text == "⏸ Пауза")
async def button_pause(message: types.Message):
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.warning(f"Ошибка очистки: {e}")
    await message.answer("⏸ Пауза", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "▶️ Продолжить")
async def button_resume(message: types.Message):
    if material_pairs:
        schedule_posts()
        await message.answer(
            f"▶️ Возобновлено. "
            f"Запланировано {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} постов.",
            reply_markup=get_main_keyboard()
        )
    else:
        load_and_move_materials()
        if material_pairs:
            schedule_posts()
            await message.answer(
                f"▶️ Возобновлено. "
                f"Запланировано {len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])} постов.",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("📭 Нет публикаций.", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🧹 Полная очистка")
async def button_full_clear(message: types.Message):
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.warning(f"Ошибка очистки: {e}")

    global material_pairs
    cleared_memory = len(material_pairs)
    material_pairs = []

    deleted_materials = 0
    if os.path.exists(materials_folder):
        try:
            for filename in os.listdir(materials_folder):
                file_path = os.path.join(materials_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_materials += 1
                except Exception as e:
                    logging.error(f"Ошибка {filename}: {e}")
        except Exception as e:
            logging.error(f"Ошибка materials: {e}")

    deleted_wait = 0
    if os.path.exists(pending_folder):
        try:
            for filename in os.listdir(pending_folder):
                file_path = os.path.join(pending_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_wait += 1
                except Exception as e:
                    logging.error(f"Ошибка wait {filename}: {e}")
        except Exception as e:
            logging.error(f"Ошибка wait: {e}")

    response = (
        f"🧹 Очистка завершена!\n\n"
        f"📥 materials: {deleted_materials} файлов\n"
        f"⏳ wait: {deleted_wait} файлов\n"
        f"📋 очередь: {cleared_memory} публикаций\n"
    )
    await message.answer(response, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "⚙️ Настройки")
async def button_settings(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="1 пост/день", callback_data="freq_1")],
        [types.InlineKeyboardButton(text="2 поста/день", callback_data="freq_2")],
        [types.InlineKeyboardButton(text="3 поста/день", callback_data="freq_3")],
        [types.InlineKeyboardButton(text="4 поста/день", callback_data="freq_4")]
    ])

    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"Частота: {PUBLICATIONS_PER_DAY} постов/день\n\n"
        f"Выберите новую частоту:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(lambda message: message.text == "🧪 Тест (5 сек)")
async def button_test_fast(message: types.Message):
    if not material_pairs:
        load_and_move_materials()

    if len(material_pairs) >= 1:
        first_pair = material_pairs[0]
        
        def test_publish():
            asyncio.create_task(send_material_pair(first_pair[0], first_pair[1]))
            return schedule.CancelJob
        
        schedule.every(5).seconds.do(test_publish).tag('test')
        
        await message.answer("🚀 Тест через 5 секунд", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Нужен 1 файл (jpg + txt)", reply_markup=get_main_keyboard())

@dp.callback_query(F.data.startswith("freq_"))
async def handle_frequency_change(query: CallbackQuery):
    await query.answer()

    global PUBLICATIONS_PER_DAY

    async with _freq_lock:
        try:
            new_freq = int(query.data.split("_", 1)[1])
            old_freq = PUBLICATIONS_PER_DAY
            PUBLICATIONS_PER_DAY = new_freq

            try:
                schedule.clear('post')
                schedule.clear('test')  # Также очищаем тестовые задачи
            except Exception as e:
                logging.warning(f"Ошибка очистки: {e}")

            material_pairs.clear()
            load_and_move_materials()

            if material_pairs:
                schedule_posts()
                scheduled_count = len([j for j in schedule.jobs if 'post' in getattr(j, 'tags', [])])
                message_text = (
                    f"✅ Частота изменена!\n"
                    f"{old_freq} → {PUBLICATIONS_PER_DAY} постов/день\n"
                    f"Загружено: {len(material_pairs)} публикаций\n"
                    f"Запланировано: {scheduled_count} постов"
                )
            else:
                message_text = f"✅ Частота: {PUBLICATIONS_PER_DAY} постов/день\nНет материалов"

            try:
                await query.message.edit_text(message_text, parse_mode="HTML")
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    pass
                else:
                    await query.message.answer(message_text, parse_mode="HTML")
            except Exception as e:
                await query.message.answer(message_text, parse_mode="HTML")

        except Exception as e:
            logging.error("Ошибка частоты", exc_info=True)
            await query.answer("Ошибка!")
            try:
                await query.message.answer("❌ Ошибка частоты", parse_mode="HTML")
            except Exception as send_error:
                logging.error(f"Ошибка: {send_error}")

# ─────────────────────────────────────────────────────────────
# Webhook handlers
# ─────────────────────────────────────────────────────────────
async def on_startup(bot: Bot):
    logging.info("=== СТАРТ НА RENDER ===")
    
    try:
        schedule.clear('post')
        schedule.clear('test')  # Также очищаем тестовые задачи
    except Exception as e:
        logging.error(f"Ошибка: {e}", exc_info=True)

    WEBHOOK_URL = f"{APP_BASE_URL}/webhook"
    await bot.set_webhook(
        WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )
    logging.info(f"Webhook: {WEBHOOK_URL}")

    asyncio.create_task(run_scheduler_loop())
    
    # При запуске на Render загружаем материалы из текущей среды
    load_and_move_materials()
    if material_pairs:
        schedule_posts()

async def on_shutdown(bot: Bot):
    logging.info("=== СТОП ===")
    await bot.session.close()

async def health(request: web.Request):
    return web.Response(text="OK")

async def tick(request: web.Request):
    if request.query.get("token") != TICK_TOKEN:
        return web.Response(status=403, text="forbidden")
    schedule.run_pending()
    return web.Response(text="tick")

def main():
    logging.info("=== СТАРТ НА RENDER ===")
    
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