import asyncio
import logging

from aiogram import Bot

from bot.database.connection import get_pool
from bot.services.research import RESEARCH


async def finish_research(bot: Bot):
    pool = await get_pool()

    async with pool.acquire() as connection:
        due_ids = await connection.fetch(
            """
            SELECT id
            FROM research_queue
            WHERE finishes_at <= NOW()
            ORDER BY finishes_at, id
            LIMIT 50
            """
        )

        for candidate in due_ids:
            research_id = candidate["id"]
            notification = None

            try:
                async with connection.transaction():
                    item = await connection.fetchrow(
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
                        WHERE rq.id = $1
                          AND rq.finishes_at <= NOW()
                        FOR UPDATE OF rq SKIP LOCKED
                        """,
                        research_id,
                    )

                    if item is None:
                        continue

                    realm_id = item["realm_id"]

                    # Serializar investigaciones del mismo reino.
                    await connection.fetchrow(
                        """
                        SELECT id
                        FROM realms
                        WHERE id = $1
                        FOR UPDATE
                        """,
                        realm_id,
                    )

                    research_type = item["research_type"]
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
                            research_id,
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
                        research_id,
                    )

                    notification = {
                        "owner_id": item["owner_id"],
                        "realm_name": item["realm_name"],
                        "research_name": research_name,
                        "research_type": research_type,
                        "target_level": target_level,
                    }

            except asyncio.CancelledError:
                raise

            except Exception:
                logging.exception(
                    "Error procesando la investigación %s. "
                    "Se continuará con las demás investigaciones.",
                    research_id,
                )
                continue

            # Solo notificar después del commit.
            if notification is None:
                continue

            try:
                await bot.send_message(
                    notification["owner_id"],
                    "🔬 <b>¡Investigación completada!</b>\n\n"
                    f"Tu reino <b>{notification['realm_name']}</b> "
                    f"ha desarrollado "
                    f"<b>{notification['research_name']}</b> "
                    f"hasta el nivel "
                    f"<b>{notification['target_level']}</b>.\n\n"
                    + (
                        "Ya puedes acudir a Territorios y elegir "
                        "un territorio completamente vacío para fundar "
                        "tu única provincia."
                        if notification["research_type"]
                        == "provincial_administration"
                        else "Los efectos de esta tecnología ya están activos."
                    )
                )

            except asyncio.CancelledError:
                raise

            except Exception:
                logging.exception(
                    "No se pudo enviar la notificación "
                    "de investigación %s.",
                    research_id,
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
