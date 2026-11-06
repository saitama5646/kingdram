
from bot.database.connection import get_pool


MINIMUM_DESTRUCTION = 0.50


async def would_create_vassalage_cycle(
    connection,
    lord_realm_id: int,
    vassal_realm_id: int,
):
    return await connection.fetchval(
        """
        WITH RECURSIVE descendants(realm_id) AS (
            SELECT $2::BIGINT

            UNION

            SELECT rel.vassal_realm_id
            FROM vassalage_relations rel
            JOIN descendants d
              ON rel.lord_realm_id = d.realm_id
            WHERE rel.status = 'active'
        )
        SELECT EXISTS (
            SELECT 1
            FROM descendants
            WHERE realm_id = $1
        )
        """,
        lord_realm_id,
        vassal_realm_id,
    )



async def create_vassalage_request(
    lord_realm_id: int,
    vassal_realm_id: int,
    destruction_ratio: float
):
    if lord_realm_id == vassal_realm_id:
        return False, "No puedes someter tu propio reino."

    if not MINIMUM_DESTRUCTION <= destruction_ratio <= 1:
        return False, (
            "No se ha alcanzado el 50 % "
            "de destrucción de infraestructura."
        )

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            realms = await connection.fetch(
                """
                SELECT id
                FROM realms
                WHERE id = ANY($1::BIGINT[])
                ORDER BY id
                FOR UPDATE
                """,
                [lord_realm_id, vassal_realm_id]
            )

            if len(realms) != 2:
                return False, "Uno de los reinos no existe."

            if await would_create_vassalage_cycle(
                connection,
                lord_realm_id,
                vassal_realm_id,
            ):
                return False, (
                    "Solicitud imposible: crearía un ciclo de vasallaje. "
                    "Un reino no puede ser señor de su propio señor."
                )

            relation = await connection.fetchrow(
                """
                SELECT id
                FROM vassalage_relations
                WHERE vassal_realm_id = $1
                  AND status = 'active'
                """,
                vassal_realm_id
            )

            if relation:
                return False, (
                    "Ese reino ya tiene un señor feudal."
                )

            pending = await connection.fetchrow(
                """
                SELECT id
                FROM vassalage_requests
                WHERE vassal_realm_id = $1
                  AND status = 'pending'
                """,
                vassal_realm_id
            )

            if pending:
                return False, (
                    "Ya existe una solicitud pendiente."
                )

            await connection.execute(
                """
                INSERT INTO vassalage_requests (
                    lord_realm_id,
                    vassal_realm_id,
                    destruction_ratio
                )
                VALUES ($1, $2, $3)
                """,
                lord_realm_id,
                vassal_realm_id,
                destruction_ratio
            )

    return True, "Solicitud de vasallaje enviada."


async def decide_vassalage_request(
    request_id: int,
    owner_id: int,
    accept: bool
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            request = await connection.fetchrow(
                """
                SELECT req.*
                FROM vassalage_requests req
                JOIN realms vassal
                  ON vassal.id = req.vassal_realm_id
                WHERE req.id = $1
                  AND vassal.owner_id = $2
                  AND req.status = 'pending'
                FOR UPDATE OF req
                """,
                request_id,
                owner_id
            )

            if not request:
                return False, (
                    "Solicitud inexistente o ya resuelta."
                )

            # Bloquear ambos reinos por ID ascendente antes de validar
            # o aceptar la relación.
            locked_realms = await connection.fetch(
                """
                SELECT id
                FROM realms
                WHERE id = ANY($1::BIGINT[])
                ORDER BY id
                FOR UPDATE
                """,
                [
                    request["lord_realm_id"],
                    request["vassal_realm_id"],
                ],
            )

            if len(locked_realms) != 2:
                return False, "Uno de los reinos ya no existe."

            if accept:
                if await would_create_vassalage_cycle(
                    connection,
                    request["lord_realm_id"],
                    request["vassal_realm_id"],
                ):
                    return False, (
                        "Solicitud rechazada: produciría un ciclo "
                        "de vasallaje."
                    )

                # Revalidar que el reino vasallo no haya
                # adquirido otro señor mientras esperaba.
                active_relation = await connection.fetchrow(
                    """
                    SELECT id
                    FROM vassalage_relations
                    WHERE vassal_realm_id = $1
                      AND status = 'active'
                    FOR UPDATE
                    """,
                    request["vassal_realm_id"],
                )

                if active_relation:
                    return False, (
                        "Este reino ya tiene un señor feudal."
                    )

                # Cancelar una petición inversa pendiente.
                await connection.execute(
                    """
                    UPDATE vassalage_requests
                    SET status = 'cancelled',
                        decided_at = NOW()
                    WHERE lord_realm_id = $1
                      AND vassal_realm_id = $2
                      AND status = 'pending'
                    """,
                    request["vassal_realm_id"],
                    request["lord_realm_id"],
                )

                await connection.execute(
                    """
                    INSERT INTO vassalage_relations (
                        lord_realm_id,
                        vassal_realm_id
                    )
                    VALUES ($1, $2)
                    """,
                    request["lord_realm_id"],
                    request["vassal_realm_id"]
                )

                status = "accepted"
                message = "Has aceptado el vasallaje."

            else:
                status = "rejected"
                message = "Has rechazado la solicitud."

            await connection.execute(
                """
                UPDATE vassalage_requests
                SET status = $1,
                    decided_at = NOW()
                WHERE id = $2
                """,
                status,
                request_id
            )

    return True, message


async def grant_independence(
    lord_realm_id: int,
    vassal_realm_id: int,
    owner_id: int
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            relation = await connection.fetchrow(
                """
                SELECT rel.id
                FROM vassalage_relations rel
                JOIN realms lord
                  ON lord.id = rel.lord_realm_id
                WHERE rel.lord_realm_id = $1
                  AND rel.vassal_realm_id = $2
                  AND rel.status = 'active'
                  AND lord.owner_id = $3
                FOR UPDATE OF rel
                """,
                lord_realm_id,
                vassal_realm_id,
                owner_id
            )

            if not relation:
                return False, (
                    "Solo el señor feudal puede "
                    "conceder la independencia."
                )

            await connection.execute(
                """
                UPDATE vassalage_relations
                SET status = 'ended',
                    ended_at = NOW(),
                    ended_by_owner_id = $1
                WHERE id = $2
                """,
                owner_id,
                relation["id"]
            )

    return True, (
        "Has concedido la independencia al reino."
    )


async def get_vassalage_data(owner_id: int):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            owner_id
        )

        if not realm:
            return None

        lord = await connection.fetchrow(
            """
            SELECT lord.name
            FROM vassalage_relations rel
            JOIN realms lord
              ON lord.id = rel.lord_realm_id
            WHERE rel.vassal_realm_id = $1
              AND rel.status = 'active'
            """,
            realm["id"]
        )

        vassals = await connection.fetch(
            """
            SELECT
                rel.vassal_realm_id,
                vassal.name,
                rel.started_at
            FROM vassalage_relations rel
            JOIN realms vassal
              ON vassal.id = rel.vassal_realm_id
            WHERE rel.lord_realm_id = $1
              AND rel.status = 'active'
            ORDER BY rel.started_at
            """,
            realm["id"]
        )

        incoming = await connection.fetch(
            """
            SELECT
                req.id,
                req.destruction_ratio,
                req.created_at,
                lord.name AS lord_name
            FROM vassalage_requests req
            JOIN realms lord
              ON lord.id = req.lord_realm_id
            WHERE req.vassal_realm_id = $1
              AND req.status = 'pending'
            ORDER BY req.created_at DESC
            """,
            realm["id"]
        )

        outgoing = await connection.fetch(
            """
            SELECT
                req.id,
                req.status,
                vassal.name AS vassal_name,
                req.created_at
            FROM vassalage_requests req
            JOIN realms vassal
              ON vassal.id = req.vassal_realm_id
            WHERE req.lord_realm_id = $1
            ORDER BY req.created_at DESC
            LIMIT 20
            """,
            realm["id"]
        )

    return {
        "realm": realm,
        "lord": lord,
        "vassals": vassals,
        "incoming": incoming,
        "outgoing": outgoing
    }
