
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
        max_size=5,
        ssl="require"
    )

    schema_path = BASE_DIR / "bot" / "database" / "schema.sql"

    async with pool.acquire() as connection:
        schema = schema_path.read_text(encoding="utf-8")
        await connection.execute(schema)

    print("Base de datos Kingdram inicializada correctamente.")

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
