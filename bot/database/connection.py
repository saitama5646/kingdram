
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
        ssl="require"
    )

    schema_files = [
        BASE_DIR / "bot" / "database" / "schema.sql",
        BASE_DIR / "bot" / "database" / "systems.sql",
    ]

    try:
        async with pool.acquire() as connection:
            for schema_path in schema_files:
                if not schema_path.exists():
                    raise FileNotFoundError(
                        f"No se encontró el esquema: {schema_path}"
                    )

                schema = schema_path.read_text(encoding="utf-8")

                async with connection.transaction():
                    await connection.execute(schema)

        print("Base de datos Kingdram inicializada correctamente.")
        print("Sistemas económicos, diplomáticos y tecnológicos preparados.")

    except Exception:
        await pool.close()
        pool = None
        raise

    return pool


async def get_pool():
    if pool is None:
        raise RuntimeError("La base de datos no está conectada.")

    return pool


async def close_database():
    global pool

    if pool is not None:
        await pool.close()
        pool = None
        print("Conexión con Neon cerrada.")
