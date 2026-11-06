import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.database.connection import (
    connect_database,
    close_database,
)
from bot.web import RuntimeState, start_health_server

from bot.handlers.start import router as start_router
from bot.handlers.menu import router as menu_router
from bot.handlers.dashboard import router as dashboard_router
from bot.handlers.kingdom import router as kingdom_router
from bot.handlers.buildings import router as buildings_router
from bot.handlers.army import router as army_router
from bot.handlers.economy import router as economy_router
from bot.handlers.territory import router as territory_router
from bot.handlers.world import router as world_router
from bot.handlers.ranking import router as ranking_router
from bot.handlers.research import router as research_router
from bot.handlers.battle import router as battle_router
from bot.handlers.diplomacy import router as diplomacy_router
from bot.handlers.treaties import router as treaties_router

from bot.workers.production import production_worker
from bot.workers.construction import construction_worker
from bot.workers.military import military_worker
from bot.workers.research import research_worker
from bot.workers.missions import missions_worker
from bot.workers.attack_warning import attack_warning_worker


WORKER_RESTART_DELAY = 5


async def supervise_worker(worker_factory, worker_name):
    """
    Mantiene un trabajador activo y lo reinicia si termina
    inesperadamente o produce una excepción no controlada.
    """
    while True:
        try:
            logging.info(
                "Iniciando trabajador: %s",
                worker_name,
            )

            await worker_factory()

            logging.warning(
                "El trabajador %s terminó inesperadamente.",
                worker_name,
            )

        except asyncio.CancelledError:
            logging.info(
                "Cancelación recibida por el trabajador: %s",
                worker_name,
            )
            raise

        except Exception:
            logging.exception(
                "Fallo crítico en el trabajador %s.",
                worker_name,
            )

        logging.warning(
            "Reiniciando trabajador %s en %s segundos.",
            worker_name,
            WORKER_RESTART_DELAY,
        )

        await asyncio.sleep(WORKER_RESTART_DELAY)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dp = Dispatcher()

    workers = []
    http_server = None
    http_task = None
    polling_task = None

    state = RuntimeState()

    try:
        http_server = await start_health_server(state)

        http_task = asyncio.create_task(
            http_server.serve_forever(),
            name="kingdram-http",
        )

        await connect_database()

        dp.include_router(start_router)
        dp.include_router(menu_router)
        dp.include_router(diplomacy_router)
        dp.include_router(treaties_router)
        dp.include_router(dashboard_router)
        dp.include_router(kingdom_router)
        dp.include_router(buildings_router)
        dp.include_router(army_router)
        dp.include_router(economy_router)
        dp.include_router(territory_router)
        dp.include_router(world_router)
        dp.include_router(ranking_router)
        dp.include_router(research_router)
        dp.include_router(battle_router)

        workers.extend([
            asyncio.create_task(
                supervise_worker(
                    production_worker,
                    "kingdram-production",
                ),
                name="kingdram-production-supervisor",
            ),
            asyncio.create_task(
                supervise_worker(
                    lambda: construction_worker(bot),
                    "kingdram-construction",
                ),
                name="kingdram-construction-supervisor",
            ),
            asyncio.create_task(
                supervise_worker(
                    lambda: military_worker(bot),
                    "kingdram-military",
                ),
                name="kingdram-military-supervisor",
            ),
            asyncio.create_task(
                supervise_worker(
                    lambda: research_worker(bot),
                    "kingdram-research",
                ),
                name="kingdram-research-supervisor",
            ),
            asyncio.create_task(
                supervise_worker(
                    lambda: missions_worker(bot),
                    "kingdram-missions",
                ),
                name="kingdram-missions-supervisor",
            ),
            asyncio.create_task(
                supervise_worker(
                    lambda: attack_warning_worker(bot),
                    "kingdram-attack-warning",
                ),
                name="kingdram-attack-warning-supervisor",
            ),
        ])

        await bot.delete_webhook(
            drop_pending_updates=False,
        )

        state.ready = True

        print("================================")
        print("KINGDRAM")
        print("Base de datos Neon conectada.")
        print("Producción automática iniciada.")
        print("Sistema de construcción iniciado.")
        print("Sistema militar iniciado.")
        print("Sistema de investigación iniciado.")
        print("Sistema de misiones militares iniciado.")
        print("Sistema de alertas de ataques iniciado.")
        print("Sistema de guerra registrado.")
        print("Sistema territorial registrado.")
        print("Explorador del mundo registrado.")
        print("Panel dinámico registrado.")
        print("Notificaciones de finalización activadas.")
        print("Menú persistente conectado.")
        print("Handlers registrados.")
        print("Servidor HTTP listo.")
        print("Polling de Telegram iniciándose.")
        print("================================")

        polling_task = asyncio.create_task(
            dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
            ),
            name="kingdram-telegram-polling",
        )

        done, pending = await asyncio.wait(
            {polling_task, http_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

        for task in done:
            task.result()

    finally:
        state.ready = False

        for task in (polling_task, http_task):
            if task is not None and not task.done():
                task.cancel()

        active_tasks = [
            task
            for task in (polling_task, http_task)
            if task is not None
        ]

        if active_tasks:
            await asyncio.gather(
                *active_tasks,
                return_exceptions=True,
            )

        for worker in workers:
            worker.cancel()

        if workers:
            await asyncio.gather(
                *workers,
                return_exceptions=True,
            )

        if http_server is not None:
            http_server.close()
            await http_server.wait_closed()

        await close_database()
        await bot.session.close()

        print("Kingdram detenido correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
