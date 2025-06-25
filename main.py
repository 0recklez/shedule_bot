import asyncio
from aiogram import Bot, Dispatcher
from config import Config, load_config
from bot.handlers import register_all_handlers

config: Config = load_config()
BOT_TOKEN: str = config.tg_bot.token
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
register_all_handlers(dp, bot)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
