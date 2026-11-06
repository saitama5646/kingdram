import asyncpg

from bot.config import DATABASE_URL, BASE_DIR


pool = None


async def connect_database():
    global pool

    if pool is not None:
        return pool

    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=1,
        max_size=10,
        ssl="require",
    )

    schema_files = [
        BASE_DIR / "bot" / "database" / "schema.sql",
        BASE_DIR / "bot" / "database" / "systems.sql",
        BASE_DIR / "bot" / "database" / "battle.sql",
        BASE_DIR / "bot" / "database" / "world.sql",
        BASE_DIR / "bot" / "database" / "queues.sql",
        BASE_DIR / "bot" / "database" / "world_layout.sql",
        BASE_DIR / "bot" / "database" / "provinces.sql",
        BASE_DIR / "bot" / "database" / "diplomacy.sql",
        BASE_DIR / "bot" / "database" / "treaties.sql",
        BASE_DIR / "bot" / "database" / "vassalage.sql",
        BASE_DIR / "bot" / "database" / "combat_repairs.sql",
    ]

    try:
        async with pool.acquire() as connection:
            for schema_path in schema_files:
                if not schema_path.exists():
                    raise FileNotFoundError(
                        f"No se encontró la migración: {schema_path}"
                    )

                schema = schema_path.read_text(
                    encoding="utf-8"
                )

                async with connection.transaction():
                    await connection.execute(schema)

                print(
                    f"Migración aplicada: {schema_path.name}"
                )

        print(
            "Base de datos Kingdram inicializada correctamente."
        )

    except Exception:
        await pool.close()
        pool = None
        raise

    return pool


async def get_pool():
    if pool is None:
        raise RuntimeError(
            "La base de datos no está conectada."
        )

    return pool


async def close_database():
    global pool

    if pool is not None:
        await pool.close()
        pool = None
