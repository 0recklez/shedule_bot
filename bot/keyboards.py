from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

button_shedule_today = KeyboardButton(text="🗓Расписание на сегодня")
button_shedule_date = KeyboardButton(text="🗓Расписание по дате")
button_shedule_tomorrow = KeyboardButton(text="🗓Расписание на завтра")
kb_builder2 = ReplyKeyboardBuilder()
kb_builder2.row(button_shedule_today, button_shedule_tomorrow, button_shedule_date, width=2)
