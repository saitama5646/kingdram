
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.database.connection import (
    connect_database,
    close_database
)

from bot.handlers.start import router as start_router
from bot.handlers.kingdom import router as kingdom_router
from bot.handlers.buildings import router as buildings_router
from bot.handlers.army import router as army_router
from bot.handlers.menu import router as menu_router

from bot.workers.production import production_worker
from bot.workers.construction import construction_worker
from bot.workers.military import military_worker


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    dp = Dispatcher()
    workers = []

    try:
        await connect_database()

        dp.include_router(start_router)
        dp.include_router(kingdom_router)
        dp.include_router(buildings_router)
        dp.include_router(army_router)
        dp.include_router(menu_router)

        workers.append(
            asyncio.create_task(production_worker())
        )

        workers.append(
            asyncio.create_task(construction_worker())
        )

        workers.append(
            asyncio.create_task(military_worker())
        )

        print("================================")
        print("KINGDRAM")
        print("Base de datos Neon conectada.")
        print("Producción automática iniciada.")
        print("Sistema de construcción iniciado.")
        print("Sistema militar iniciado.")
        print("Handlers registrados.")
        print("Polling iniciado.")
        print("================================")

        await dp.start_polling(bot)

    finally:
        for worker in workers:
            worker.cancel()

        if workers:
            await asyncio.gather(
                *workers,
                return_exceptions=True
            )

        await close_database()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
