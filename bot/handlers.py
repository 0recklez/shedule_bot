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
