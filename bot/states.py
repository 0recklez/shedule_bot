from aiogram.fsm.state import StatesGroup, State


class DialogState(StatesGroup):
    add_time = State()
    ask_group = State()
    add_group = State()
