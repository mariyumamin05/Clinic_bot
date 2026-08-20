# appointment_mcp_server/tools/search_doctors_tool.py

import sys
import difflib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Doctor, Specialty


async def search_doctors_tool(doctor_name: str | None = None, specialty_name: str | None = None) -> list[dict]:
    """
    Search for active doctors by name and/or specialty.
    At least one of doctor_name or specialty_name should be provided;
    if both are None, returns all active doctors.
    """
    async with get_db_session() as session:
        query = select(Doctor).options(selectinload(Doctor.specialty)).where(Doctor.is_active == True)
        conditions = []

        if doctor_name:
            conditions.append(Doctor.full_name.ilike(f"%{doctor_name}%"))

        if specialty_name:
            # Specialty names won't always share an exact substring with how a patient
            # (or the LLM echoing them) phrases it — "cardiologist" vs "Cardiology",
            # "skin doctor" vs "Dermatology". Fuzzy-match against the known specialty
            # list instead of relying on strict ILIKE substring containment.
            specialty_result = await session.execute(select(Specialty))
            all_specialties = specialty_result.scalars().all()

            query_lower = specialty_name.lower().strip()
            matched_ids = [
                s.id for s in all_specialties
                if query_lower in s.name.lower()
                or s.name.lower() in query_lower
                or difflib.SequenceMatcher(None, query_lower, s.name.lower()).ratio() > 0.6
            ]
            # If nothing plausibly matches, force zero results rather than silently
            # dropping the filter and returning unrelated doctors.
            conditions.append(Doctor.specialty_id.in_(matched_ids or [-1]))

        if conditions:
            query = query.where(or_(*conditions))

        result = await session.execute(query)
        doctors = result.scalars().all()

        return [
            {
                "doctor_id": doc.id,
                "full_name": doc.full_name,
                "specialty": doc.specialty.name if doc.specialty else None,
                "bio": doc.bio,
            }
            for doc in doctors
        ]


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Search by specialty 'cardio' --")
        for r in await search_doctors_tool(specialty_name="cardio"):
            print(r)

        print("\n-- Search by specialty 'cardiologist' (the actual bug case) --")
        for r in await search_doctors_tool(specialty_name="cardiologist"):
            print(r)

        print("\n-- Search by name 'Ahmed' --")
        for r in await search_doctors_tool(doctor_name="Ahmed"):
            print(r)

        print("\n-- No filters (all active doctors) --")
        for r in await search_doctors_tool():
            print(r)

    asyncio.run(test())