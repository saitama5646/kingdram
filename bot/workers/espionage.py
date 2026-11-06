
import asyncio
import logging
import random

from aiogram import Bot

from bot.database.connection import get_pool
from bot.services.espionage import (
    MISSION_TYPES,
    calculate_spy_success,
)
from bot.services.research import get_research_effects


async def resolve_espionage_mission(bot: Bot, mission_id):
    pool = await get_pool()
    notification = None

    async with pool.acquire() as connection:
        async with connection.transaction():
            mission = await connection.fetchrow(
                """
                SELECT
                    em.*,
                    attacker.owner_id AS attacker_owner_id,
                    attacker.name AS attacker_name,
                    target.name AS target_name
                FROM espionage_missions em
                JOIN realms attacker
                  ON attacker.id = em.attacker_realm_id
                JOIN realms target
                  ON target.id = em.target_realm_id
                WHERE em.id = $1
                  AND em.status = 'travelling'
                  AND em.arrival_at <= NOW()
                FOR UPDATE OF em SKIP LOCKED
                """,
                mission_id,
            )

            if not mission:
                return

            attacker_id = mission["attacker_realm_id"]
            target_id = mission["target_realm_id"]

            await connection.fetchrow(
                """
                SELECT id
                FROM realms
                WHERE id = $1
                FOR UPDATE
                """,
                attacker_id,
            )

            await connection.fetchrow(
                """
                SELECT id
                FROM realms
                WHERE id = $1
                FOR UPDATE
                """,
                target_id,
            )

            attacker_research_rows = await connection.fetch(
                """
                SELECT research_type, level
                FROM realm_research
                WHERE realm_id = $1
                """,
                attacker_id,
            )

            target_research_rows = await connection.fetch(
                """
                SELECT research_type, level
                FROM realm_research
                WHERE realm_id = $1
                """,
                target_id,
            )

            attacker_levels = {
                row["research_type"]: row["level"]
                for row in attacker_research_rows
            }

            target_levels = {
                row["research_type"]: row["level"]
                for row in target_research_rows
            }

            attacker_effects = get_research_effects(
                attacker_levels,
            )

            target_effects = get_research_effects(
                target_levels,
            )

            infiltration = max(
                0.0,
                float(
                    attacker_effects.get(
                        "spy_success_bonus",
                        0,
                    )
                ),
            )

            counter_bonus = max(
                0.0,
                float(
                    target_effects.get(
                        "counterespionage_bonus",
                        0,
                    )
                ),
            )

            chance = calculate_spy_success(
                mission["spies_sent"],
                infiltration,
                counter_bonus,
            )

            success = random.random() < chance
            spies_lost = 0
            intelligence = {}

            if success:
                mission_type = mission["mission_type"]

                if mission_type == "resources":
                    row = await connection.fetchrow(
                        """
                        SELECT wood, stone, gold, food
                        FROM resources
                        WHERE realm_id = $1
                        """,
                        target_id,
                    )

                    intelligence = dict(row) if row else {}

                elif mission_type == "military":
                    rows = await connection.fetch(
                        """
                        SELECT unit_type, quantity
                        FROM army
                        WHERE realm_id = $1
                        ORDER BY unit_type
                        """,
                        target_id,
                    )

                    intelligence = {
                        "army": [
                            {
                                "unit_type": row["unit_type"],
                                "quantity": int(row["quantity"]),
                            }
                            for row in rows
                        ]
                    }

                elif mission_type == "buildings":
                    rows = await connection.fetch(
                        """
                        SELECT building_type, level, damaged_levels
                        FROM buildings
                        WHERE realm_id = $1
                        ORDER BY building_type
                        """,
                        target_id,
                    )

                    intelligence = {
                        "buildings": [
                            {
                                "building_type": row["building_type"],
                                "level": int(row["level"]),
                                "damaged_levels": int(
                                    row["damaged_levels"] or 0
                                ),
                            }
                            for row in rows
                        ]
                    }

                elif mission_type == "research":
                    rows = await connection.fetch(
                        """
                        SELECT research_type, level
                        FROM realm_research
                        WHERE realm_id = $1
                        ORDER BY research_type
                        """,
                        target_id,
                    )

                    intelligence = {
                        "research": [
                            {
                                "research_type": row["research_type"],
                                "level": int(row["level"]),
                            }
                            for row in rows
                        ]
                    }

            else:
                spies_lost = 1

                await connection.execute(
                    """
                    INSERT INTO realm_spies (
                        realm_id,
                        quantity,
                        updated_at
                    )
                    VALUES ($1, 0, NOW())
                    ON CONFLICT (realm_id) DO NOTHING
                    """,
                    attacker_id,
                )

                await connection.execute(
                    """
                    UPDATE realm_spies
                    SET quantity = quantity + $1,
                        updated_at = NOW()
                    WHERE realm_id = $2
                    """,
                    mission["spies_sent"] - spies_lost,
                    attacker_id,
                )

            await connection.execute(
                """
                INSERT INTO espionage_reports (
                    mission_id,
                    attacker_realm_id,
                    target_realm_id,
                    mission_type,
                    success,
                    spies_sent,
                    spies_lost,
                    intelligence
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::JSONB)
                """,
                mission_id,
                attacker_id,
                target_id,
                mission["mission_type"],
                success,
                mission["spies_sent"],
                spies_lost,
                __import__("json").dumps(intelligence),
            )

            await connection.execute(
                """
                UPDATE espionage_missions
                SET status = $1
                WHERE id = $2
                  AND status = 'travelling'
                """,
                "completed" if success else "failed",
                mission_id,
            )

            notification = {
                "owner_id": mission["attacker_owner_id"],
                "attacker_name": mission["attacker_name"],
                "target_name": mission["target_name"],
                "mission_type": mission["mission_type"],
                "success": success,
                "spies_lost": spies_lost,
                "intelligence": intelligence,
            }

    if notification:
        try:
            result = (
                "Éxito"
                if notification["success"]
                else "Misión descubierta o fallida"
            )

            message = (
                "🕵 <b>INFORME DE ESPIONAJE</b>\n\n"
                f"🏰 Reino objetivo: "
                f"<b>{notification['target_name']}</b>\n"
                f"📋 Misión: "
                f"<b>{MISSION_TYPES[notification['mission_type']]}</b>\n"
                f"Resultado: <b>{result}</b>\n"
                f"Espías perdidos: "
                f"<b>{notification['spies_lost']}</b>\n"
            )

            if notification["success"]:
                message += "\n<b>INFORMACIÓN OBTENIDA</b>\n"

                for key, value in notification["intelligence"].items():
                    message += f"• {key}: {value}\n"

            await bot.send_message(
                notification["owner_id"],
                message,
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "No se pudo enviar el informe de espionaje %s.",
                mission_id,
            )


async def espionage_worker(bot: Bot):
    print("Sistema de espionaje iniciado.")

    while True:
        try:
            pool = await get_pool()

            async with pool.acquire() as connection:
                due = await connection.fetch(
                    """
                    SELECT id
                    FROM espionage_missions
                    WHERE status = 'travelling'
                      AND arrival_at <= NOW()
                    ORDER BY arrival_at, id
                    LIMIT 20
                    """
                )

            for item in due:
                try:
                    await resolve_espionage_mission(
                        bot,
                        item["id"],
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logging.exception(
                        "Error procesando misión de espionaje %s.",
                        item["id"],
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error general en el worker de espionaje."
            )

        await asyncio.sleep(5)
