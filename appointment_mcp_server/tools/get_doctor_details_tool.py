# appointment_mcp_server/tools/get_doctor_details_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Doctor

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


async def get_doctor_details_tool(doctor_id: int) -> dict | None:
    """
    Get full profile for one doctor, including specialty and weekly availability.

    Args:
        doctor_id: The doctor's ID

    Returns:
        Dict with doctor details, or None if not found / inactive.
    """
    async with get_db_session() as session:
        query = (
            select(Doctor)
            .options(
                selectinload(Doctor.specialty),
                selectinload(Doctor.availability_slots),
            )
            .where(Doctor.id == doctor_id, Doctor.is_active == True)
        )
        result = await session.execute(query)
        doctor = result.scalar_one_or_none()

        if not doctor:
            return None

        availability = [
            {
                "day": DAY_NAMES[slot.day_of_week],
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
                "slot_duration_min": slot.slot_duration_min,
            }
            for slot in doctor.availability_slots
            if slot.is_active
        ]

        return {
            "doctor_id": doctor.id,
            "full_name": doctor.full_name,
            "specialty": doctor.specialty.name if doctor.specialty else None,
            "bio": doctor.bio,
            "weekly_availability": availability,
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Doctor ID 1 (should exist) --")
        result = await get_doctor_details_tool(1)
        print(result)

        print("\n-- Doctor ID 999 (should not exist) --")
        result = await get_doctor_details_tool(999)
        print(result)

    asyncio.run(test())