import asyncio
import logging

from aiogram import Bot

from bot.database.connection import get_pool
from bot.services.research import RESEARCH


async def finish_research(bot: Bot):
    pool = await get_pool()
    notifications = []

    async with pool.acquire() as connection:
        async with connection.transaction():
            completed = await connection.fetch(
                """
                SELECT
                    rq.id,
                    rq.realm_id,
                    rq.research_type,
                    rq.target_level,
                    r.owner_id,
                    r.name AS realm_name
                FROM research_queue rq
                JOIN realms r ON r.id = rq.realm_id
                WHERE rq.finishes_at <= NOW()
                ORDER BY rq.finishes_at, rq.id
                FOR UPDATE OF rq SKIP LOCKED
                """
            )

            for item in completed:
                research_type = item["research_type"]
                realm_id = item["realm_id"]
                target_level = item["target_level"]

                if research_type not in RESEARCH:
                    logging.error(
                        "Investigación desconocida en cola: %s",
                        research_type,
                    )

                    await connection.execute(
                        """
                        DELETE FROM research_queue
                        WHERE id = $1
                        """,
                        item["id"],
                    )
                    continue

                research_name = RESEARCH[research_type]["name"]

                await connection.execute(
                    """
                    INSERT INTO realm_research (
                        realm_id,
                        research_type,
                        level,
                        updated_at
                    )
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (realm_id, research_type)
                    DO UPDATE SET
                        level = GREATEST(
                            realm_research.level,
                            EXCLUDED.level
                        ),
                        updated_at = NOW()
                    """,
                    realm_id,
                    research_type,
                    target_level,
                )

                await connection.execute(
                    """
                    INSERT INTO realm_event_log (
                        realm_id,
                        event_type,
                        description
                    )
                    VALUES ($1, 'research_completed', $2)
                    """,
                    realm_id,
                    (
                        f"Investigación completada: "
                        f"{research_name} nivel {target_level}."
                    ),
                )

                await connection.execute(
                    """
                    DELETE FROM research_queue
                    WHERE id = $1
                    """,
                    item["id"],
                )

                notifications.append({
                    "owner_id": item["owner_id"],
                    "realm_name": item["realm_name"],
                    "research_name": research_name,
                    "research_type": research_type,
                    "target_level": target_level,
                })

    for item in notifications:
        try:
            await bot.send_message(
                item["owner_id"],
                "🔬 <b>¡Investigación completada!</b>\n\n"
                f"Tu reino <b>{item['realm_name']}</b> "
                f"ha desarrollado <b>{item['research_name']}</b> "
                f"hasta el nivel <b>{item['target_level']}</b>.\n\n"
                + (
                    "Ya puedes acudir a Territorios y elegir "
                    "un territorio completamente vacío para fundar "
                    "tu única provincia."
                    if item["research_type"] == "provincial_administration"
                    else "Los efectos de esta tecnología ya están activos."
                )
            )
        except Exception:
            logging.exception(
                "No se pudo enviar la notificación "
                "de investigación completada."
            )


async def research_worker(bot: Bot):
    print("Sistema de investigación iniciado.")

    while True:
        try:
            await finish_research(bot)

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error finalizando investigaciones."
            )

        await asyncio.sleep(10)
