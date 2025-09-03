from aiogram import Dispatcher, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from datetime import timedelta, datetime
from aiogram.filters import Command
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from bot.keyboards import kb_builder2
from bot.scheduler import get_calendar_data_async, get_schedule_text
from bot.states import DialogState
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging
import asyncio
import tempfile
import shutil

logger = logging.getLogger(__name__)


async def get_calendar_data_async(group_name):
    try:
        logger.info(f"Запрос расписания для группы: {group_name}")
        result = await asyncio.to_thread(get_calendar_data, group_name)
        logger.info(f"Получено {len(result)} дней расписания для группы {group_name}")
        return result
    except Exception as e:
        logger.error(f"Ошибка в get_calendar_data_async для группы {group_name}: {e}")
        return []


def get_calendar_data(group_name):
    user_data_dir = tempfile.mkdtemp()
    chrome_options = Options()

    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--remote-debugging-port=9222")

    driver = None
    try:
        logger.info(f"Запуск Chrome для группы {group_name}")
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)

        url = f"https://ssau.ru/rasp?groupId={group_name}"
        logger.info(f"Переход по URL: {url}")
        driver.get(url)

        try:
            # Ждем загрузки календаря
            logger.info("Ожидание загрузки элементов расписания...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "schedule__item"))
            )
            logger.info("Элементы расписания найдены")

            # Получаем данные календаря
            calendar_data = driver.find_elements(By.CLASS_NAME, "schedule__item")
            result = []

            logger.info(f"Найдено {len(calendar_data)} элементов расписания")

            for i, item in enumerate(calendar_data):
                try:
                    date_element = item.find_element(By.CLASS_NAME, "schedule__item-date")
                    date = date_element.text
                    logger.debug(f"Обработка даты: {date}")

                    lessons = item.find_elements(By.CLASS_NAME, "schedule__lesson")
                    day_lessons = []

                    for j, lesson in enumerate(lessons):
                        try:
                            time = lesson.find_element(By.CLASS_NAME, "schedule__lesson-time").text
                            subject = lesson.find_element(By.CLASS_NAME, "schedule__lesson-subject").text
                            teacher = lesson.find_element(By.CLASS_NAME, "schedule__lesson-teacher").text
                            auditorium = lesson.find_element(By.CLASS_NAME, "schedule__lesson-auditorium").text

                            day_lessons.append({
                                "time": time,
                                "subject": subject,
                                "teacher": teacher,
                                "auditorium": auditorium
                            })
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга урока {j + 1}: {e}")
                            continue

                    result.append({
                        "date": date,
                        "lessons": day_lessons
                    })

                except Exception as e:
                    logger.warning(f"Ошибка парсинга дня {i + 1}: {e}")
                    continue

            logger.info(f"Успешно обработано {len(result)} дней")
            return result

        except TimeoutException:
            logger.error("Таймаут ожидания элементов расписания")
            # Попробуем сделать скриншот для диагностики
            try:
                screenshot_path = f"/tmp/error_{group_name}.png"
                driver.save_screenshot(screenshot_path)
                logger.info(f"Скриншот сохранен: {screenshot_path}")
            except:
                pass
            return []

    except WebDriverException as e:
        logger.error(f"Ошибка WebDriver: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Chrome драйвер закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии драйвера: {e}")
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except:
            pass


def register_all_handlers(dp: Dispatcher, bot: Bot):
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
    async def schedule_today_handler(message: Message, state: FSMContext):
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
        except Exception as e:
            print(f"Ошибка при получении расписания: {e}")
            await message.answer(f"❌Произошла ошибка. Попробуйте ввести другую группу через /start")

    @dp.message(F.text == '🗓Расписание на завтра')
    async def schedule_tomorrow_handler(message: Message, state: FSMContext):
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
            await message.answer(f"❌Произошла ошибка. Попробуйте ввести другую группу через /start")

    @dp.message(F.text == "🗓Расписание по дате")
    async def date_handler(message: Message, state: FSMContext):
        await state.set_state(DialogState.add_time)
        await message.answer("📅 Выберите дату", reply_markup=await SimpleCalendar(
            locale="ru_RU.utf8").start_calendar()
                             )

    @dp.callback_query(SimpleCalendarCallback.filter(), DialogState.add_time)
    async def process_simple_calendar(
            callback_query: CallbackQuery,
            callback_data: CallbackData,
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
