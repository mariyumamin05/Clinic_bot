# appointment_mcp_server/database/appointment_db_connection.py

import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found. Check your .env file.")

# Async engine — talks to Supabase via asyncpg driver
engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True temporarily if you want to see raw SQL for debugging
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # checks connection is alive before using it — avoids stale connection errors
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_db_session():
    """
    Use this in every MCP tool and FastAPI route to get a DB session.
    Automatically commits on success, rolls back on error, and closes after.

    Example usage:
        async with get_db_session() as session:
            result = await session.execute(some_query)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_connection():
    """Quick sanity check — run this file directly to confirm DB connectivity."""
    from sqlalchemy import text
    async with get_db_session() as session:
        result = await session.execute(text("SELECT 1"))
        print("Connection successful:", result.scalar())


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_connection())