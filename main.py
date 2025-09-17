import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import timedelta, datetime
from config import Config, load_config

config: Config = load_config()
BOT_TOKEN: str = config.tg_bot.token

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

button_shedule_today = KeyboardButton(text="🗓Расписание на сегодня")
button_shedule_date = KeyboardButton(text="🗓Расписание по дате")
button_shedule_tomorrow = KeyboardButton(text="🗓Расписание на завтра")

kb_builder2 = ReplyKeyboardBuilder()
kb_builder2.row(button_shedule_today, button_shedule_tomorrow, button_shedule_date, width=2)


class DialogState(StatesGroup):
    add_time = State()
    ask_group = State()
    add_group = State()


schedule_cache = {}
cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 1200


def get_calendar_data(group_name):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)
    driver.get("https://ya.mininuniver.ru/shedule")

    group_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "searchGroup"))
    )
    group_input.send_keys(group_name)
    time.sleep(1)
    group_input.send_keys(Keys.ARROW_DOWN)
    group_input.send_keys(Keys.ENTER)

    time.sleep(2)
    calendar_data = driver.execute_script("return window.CalendarData")

    driver.quit()
    return calendar_data


def get_calendar_data_cached(group_name):
    now = time.time()
    cache_key = group_name
    with cache_lock:
        entry = schedule_cache.get(cache_key)
        if entry and now - entry["timestamp"] < CACHE_TTL_SECONDS:
            return entry["data"]
    data = get_calendar_data(group_name)
    with cache_lock:
        schedule_cache[cache_key] = {"timestamp": now, "data": data}
    return data


executor = ThreadPoolExecutor(max_workers=2)


async def get_calendar_data_async(group_name):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, get_calendar_data_cached, group_name)


def get_schedule_text(calendar_data, target_date: str = None) -> str:
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    found = False
    message = f"📅 Расписание на {target_date}:\n"

    couple_type_map = {
        "лек.": "🟩 Лекция",
        "прак.": "🟦 Практика",
        "лаб. р.": "🟧 Лабораторная",
        "зач.": "🟧 Зачет",
        "экз.": "🟥 Экзамен",
        "КСР": "🟦 КСР",
        "кон.": "🟦 Контрольная"
    }

    for day in calendar_data:
        date = day.get("date")
        if date != target_date:
            continue

        found = True
        title = day.get("title")
        if title:
            for pair_number, pair_info in title.items():
                lessons = pair_info.get("lessons", [])

                for lesson in lessons:
                    subgroup_text = "Подгруппа не указана"

                    subgroup = lesson.get("subgroup")
                    if isinstance(subgroup, dict):
                        subgroup_number = subgroup.get("subgroup_numbers")
                        if subgroup_number:
                            subgroup_text = f"Подгруппа: {subgroup_number}"

                    couple = lesson.get("couple", {})
                    time_ = couple.get("time", "время неизвестно")
                    discipline = lesson.get("discipline", "предмет неизвестен")
                    teacher = lesson.get("teacher", {}).get("name", "преподаватель неизвестен")
                    cabinet = lesson.get("place", {}).get("cabinet", "кабинет не указан")
                    address = lesson.get("place", {}).get("housing", {}).get("address", "")
                    couple_type_key = couple.get("couple_type", "не указано")
                    couple_type = couple_type_map.get(couple_type_key, couple_type_key)

                    message += (f"\n🕒 Пара №{pair_number} ({time_})\n"
                                f"📚 {discipline}\n"
                                f"{couple_type}\n"
                                f"👥 {subgroup_text}\n"
                                f"👨‍🏫 {teacher}\n"
                                f"🏫 {cabinet}, {address}\n")
        else:
            message += "\n📭 Занятий нет."

    if not found:
        message = f"📅 На {target_date} занятий не найдено."

    return message


@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    await message.answer("👋 Привет! Напиши название своей группы (например ИСТ-24-1)")
    await state.set_state(DialogState.ask_group)


@dp.message(DialogState.ask_group)
async def process_group_name(message: Message, state: FSMContext):
    if message.text in ["🗓Расписание на сегодня", "🗓Расписание на завтра", "🗓Расписание по дате"]:
        await message.answer("❗️Пожалуйста, введите название группы вручную, например: `ИСТ-24-1`")
        return
    group_name = message.text.upper().strip()
    await state.update_data(group_name=group_name)
    await state.set_state(DialogState.add_group)
    await message.answer(
        f"✅ Группа установлена: {group_name}",
        reply_markup=kb_builder2.as_markup(
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder='Выберите действие'
        )
    )


@dp.message(F.text == '🗓Расписание на сегодня')
async def get_group_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    group_name = data.get("group_name")
    if not group_name:
        await message.answer("❗️Сначала введите группу через /start.")
        return
    await message.answer(f"📡 Получаю расписание на сегодня")
    try:
        calendar_data = await get_calendar_data_async(group_name)
        target_date = datetime.now().strftime("%Y-%m-%d")
        result = get_schedule_text(calendar_data, target_date)
        await message.answer(result)
    except:
        await message.answer(f"❌ Группа не найдена, введите другую через /start ")


@dp.message(F.text == '🗓Расписание на завтра')
async def get_group_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    group_name = data.get("group_name")
    if not group_name:
        await message.answer("❗️Сначала введите группу через /start.")
        return
    await message.answer(f"📡 Получаю расписание на завтра")
    try:
        calendar_data = await get_calendar_data_async(group_name)
        target_date = datetime.now() + timedelta(days=1)
        target_date = target_date.strftime("%Y-%m-%d")
        result = get_schedule_text(calendar_data, target_date)
        await message.answer(result)
    except:
        await message.answer(f"❌ Группа не найдена, введите другую через /start ")


@dp.message(F.text == "🗓Расписание по дате")
async def date_handler(message: Message, state: FSMContext):
    await state.set_state(DialogState.add_time)
    await message.answer("📅 Выберите дату", reply_markup=await SimpleCalendar(
        locale="ru_RU.utf8").start_calendar()
                         )


@dp.callback_query(SimpleCalendarCallback.filter(), DialogState.add_time)
async def process_simple_calendar(
        callback_query: CallbackQuery,
        callback_data: SimpleCalendarCallback,  # Исправлен тип
        state: FSMContext
):

    locale = "ru_RU.utf8"

    calendar = SimpleCalendar(locale=locale, show_alerts=True)
    calendar.set_dates_range(datetime(2022, 1, 1), datetime(2025, 12, 31))

    selected, date = await calendar.process_selection(callback_query, callback_data)

    if selected:
        await state.update_data(task_time=date)
        task_time = date
        data = await state.get_data()
        group_name, date_input = data.get("group_name"), task_time.strftime("%Y-%m-%d")
        if not group_name:
            await callback_query.message.answer("❗️Сначала введите группу через /start.")
            return
        await callback_query.message.answer(f"📡 Загружаю расписание на {date_input}")
        try:
            calendar_data = await get_calendar_data_async(group_name)
            result = get_schedule_text(calendar_data, date_input)
            await callback_query.message.answer(result)
        except:
            await callback_query.message.answer(f"❌ Группа не найдена, введите другую через /start ")


@dp.message()
async def other_message(message: Message):
    welcome_text = "😳 Я вас не понял. Выбери действие из меню, чтобы получить расписание."
    await message.answer(
        text=welcome_text,
        reply_markup=kb_builder2.as_markup(
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder='Выберите действие'
        )
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())