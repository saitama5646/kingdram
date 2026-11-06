import asyncio
import logging

from aiogram import Bot

from bot.database.connection import get_pool


WARNING_SECONDS = 300
CHECK_INTERVAL = 15


async def attack_warning_worker(bot: Bot):
    print("Sistema de avisos de ataques iniciado.")

    pool = await get_pool()

    async with pool.acquire() as connection:
        await connection.execute(
            """
            ALTER TABLE military_missions
            ADD COLUMN IF NOT EXISTS warning_sent_at TIMESTAMPTZ
            """
        )

    while True:
        try:
            async with pool.acquire() as connection:
                missions = await connection.fetch(
                    """
                    SELECT
                        m.id,
                        m.arrival_at,
                        defender.owner_id AS defender_owner_id,
                        defender.name AS defender_name,
                        attacker.name AS attacker_name
                    FROM military_missions m
                    JOIN realms defender
                      ON defender.id = m.defender_realm_id
                    JOIN realms attacker
                      ON attacker.id = m.attacker_realm_id
                    WHERE m.status = 'travelling'
                      AND m.mission_type = 'attack'
                      AND m.warning_sent_at IS NULL
                      AND m.arrival_at > NOW()
                      AND m.arrival_at <=
                          NOW() + $1 * INTERVAL '1 second'
                    ORDER BY m.arrival_at, m.id
                    LIMIT 50
                    """,
                    WARNING_SECONDS,
                )

                for mission in missions:
                    message = (
                        "⚠️ <b>¡VUESTRO REINO ESTÁ BAJO AMENAZA!</b>\n\n"
                        f"🏰 Reino defensor: "
                        f"<b>{mission['defender_name']}</b>\n"
                        f"🚩 Reino atacante: "
                        f"<b>{mission['attacker_name']}</b>\n"
                        f"🆔 Expedición: "
                        f"<b>#{mission['id']}</b>\n\n"
                        "Un ejército enemigo marcha hacia vuestras "
                        "murallas.\n\n"
                        "⏳ <b>La llegada está prevista en "
                        "5 minutos o menos.</b>\n\n"
                        "¡Preparad las defensas!"
                    )

                    # Reclamar la alerta antes de enviarla para evitar
                    # duplicados si el trabajador se reinicia.
                    claimed = await connection.fetchval(
                        """
                        UPDATE military_missions
                        SET warning_sent_at = NOW()
                        WHERE id = $1
                          AND warning_sent_at IS NULL
                        RETURNING id
                        """,
                        mission["id"],
                    )

                    if not claimed:
                        continue

                    try:
                        await bot.send_message(
                            int(mission["defender_owner_id"]),
                            message,
                            parse_mode="HTML",
                        )

                        logging.info(
                            "Alerta de ataque enviada para misión #%s",
                            mission["id"],
                        )

                    except Exception:
                        # Si Telegram no recibió el mensaje, permitir
                        # que el trabajador vuelva a intentarlo.
                        await connection.execute(
                            """
                            UPDATE military_missions
                            SET warning_sent_at = NULL
                            WHERE id = $1
                            """,
                            mission["id"],
                        )

                        logging.exception(
                            "No se pudo enviar la alerta de misión #%s",
                            mission["id"],
                        )

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error en el trabajador de alertas de ataque."
            )

        await asyncio.sleep(CHECK_INTERVAL)
