
import asyncio
import logging

from aiogram import Bot

from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS


def calculate_construction_power_gain(
    previous_level,
    target_level,
):
    """
    Calcula el poder ganado por niveles realmente construidos.

    Cada nivel nuevo aporta 25 puntos.
    Una construcción que no aumenta el nivel no aporta poder.
    """
    previous_level = max(0, int(previous_level))
    target_level = max(0, int(target_level))

    return max(0, target_level - previous_level) * 25


async def finish_constructions(bot: Bot):
    pool = await get_pool()
    notifications = []

    # Las reparaciones se procesan de forma independiente
    # para evitar afectar las construcciones pendientes.

    async with pool.acquire() as connection:
        async with connection.transaction():
            completed = await connection.fetch(
                """
                SELECT
                    cq.id,
                    cq.realm_id,
                    cq.building_type,
                    cq.target_level,
                    r.owner_id,
                    r.name AS realm_name
                FROM construction_queue cq
                JOIN realms r ON r.id = cq.realm_id
                WHERE cq.finishes_at <= NOW()
                ORDER BY cq.finishes_at, cq.id
                FOR UPDATE OF cq SKIP LOCKED
                """
            )

            for item in completed:
                building_type = item["building_type"]
                target_level = item["target_level"]
                realm_id = item["realm_id"]

                # Serializar las finalizaciones del mismo reino.
                await connection.fetchrow(
                    """
                    SELECT id
                    FROM realms
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    realm_id,
                )

                previous_level = await connection.fetchval(
                    """
                    SELECT level
                    FROM buildings
                    WHERE realm_id = $1
                      AND building_type = $2
                    FOR UPDATE
                    """,
                    realm_id,
                    building_type,
                )

                previous_level = int(previous_level or 0)

                await connection.execute(
                    """
                    INSERT INTO buildings (
                        realm_id,
                        building_type,
                        level
                    )
                    VALUES ($1, $2, $3)
                    ON CONFLICT (realm_id, building_type)
                    DO UPDATE SET
                        level = GREATEST(
                            buildings.level,
                            EXCLUDED.level
                        )
                    """,
                    realm_id,
                    building_type,
                    target_level,
                )

                power_gain = calculate_construction_power_gain(
                    previous_level,
                    target_level,
                )

                if power_gain > 0:
                    await connection.execute(
                        """
                        UPDATE realms
                        SET power = power + $1
                        WHERE id = $2
                        """,
                        power_gain,
                        realm_id,
                    )

                await connection.execute(
                    """
                    INSERT INTO realm_event_log (
                        realm_id,
                        event_type,
                        description
                    )
                    VALUES ($1, 'construction_completed', $2)
                    """,
                    realm_id,
                    (
                        f"Construcción completada: "
                        f"{building_type} "
                        f"nivel {target_level}."
                    ),
                )

                await connection.execute(
                    """
                    DELETE FROM construction_queue
                    WHERE id = $1
                    """,
                    item["id"],
                )

                notifications.append({
                    "owner_id": item["owner_id"],
                    "realm_name": item["realm_name"],
                    "building_type": building_type,
                    "target_level": target_level,
                })

    for item in notifications:
        info = BUILDINGS.get(
            item["building_type"],
            {},
        )

        name = info.get(
            "name",
            item["building_type"],
        )

        icon = info.get("icon", "🏰")

        try:
            await bot.send_message(
                item["owner_id"],
                "🏗 <b>¡Construcción finalizada!</b>\n\n"
                f"Tu reino <b>{item['realm_name']}</b> "
                f"ha completado {icon} <b>{name}</b>, "
                f"nivel {item['target_level']}."
            )

        except Exception:
            logging.exception(
                "No se pudo enviar la notificación "
                "de construcción finalizada."
            )


async def construction_worker(bot: Bot):
    print("Sistema de construcción iniciado.")

    while True:
        try:
            await finish_constructions(bot)

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error finalizando construcciones."
            )

        await asyncio.sleep(3)
