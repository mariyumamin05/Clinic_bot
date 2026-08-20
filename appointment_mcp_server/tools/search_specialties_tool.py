# appointment_mcp_server/tools/search_specialties_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Specialty


async def search_specialties_tool(name: str | None = None) -> list[dict]:
    async with get_db_session() as session:
        query = select(Specialty)
        if name:
            query = query.where(Specialty.name.ilike(f"%{name}%"))
        result = await session.execute(query)
        return [{"specialty_id": s.id, "name": s.name} for s in result.scalars().all()]


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- All specialties --")
        for r in await search_specialties_tool():
            print(r)

    asyncio.run(test())