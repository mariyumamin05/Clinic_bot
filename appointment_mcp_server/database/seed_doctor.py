# appointment_mcp_server/database/seed_doctor.py

import sys
from pathlib import Path
from datetime import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Specialty, Doctor, DoctorAvailability


async def add_doctor(
    full_name: str,
    specialty_name: str,
    bio: str,
    weekly_hours: list[tuple[int, str, str]],
    # weekly_hours: list of (day_of_week, "HH:MM", "HH:MM")
    # day_of_week: 0=Sunday, 1=Monday, ... 6=Saturday
    slot_duration_min: int = 30,
) -> dict:
    async with get_db_session() as session:
        # 1. Find or create the specialty
        specialty = (await session.execute(
            select(Specialty).where(Specialty.name == specialty_name)
        )).scalar_one_or_none()

        if not specialty:
            specialty = Specialty(name=specialty_name)
            session.add(specialty)
            await session.flush()
            print(f"Created new specialty: {specialty_name}")

        # 2. Create the doctor (skip if one with this exact name already exists)
        existing_doctor = (await session.execute(
            select(Doctor).where(Doctor.full_name == full_name)
        )).scalar_one_or_none()

        if existing_doctor:
            print(f"Doctor '{full_name}' already exists (ID {existing_doctor.id}) — skipping creation.")
            doctor = existing_doctor
        else:
            doctor = Doctor(
                full_name=full_name,
                specialty_id=specialty.id,
                bio=bio,
                is_active=True,
            )
            session.add(doctor)
            await session.flush()
            print(f"Created doctor: {full_name} (ID {doctor.id}), specialty: {specialty_name}")

        # 3. Add weekly availability slots
        for day_of_week, start_str, end_str in weekly_hours:
            h1, m1 = map(int, start_str.split(":"))
            h2, m2 = map(int, end_str.split(":"))
            slot = DoctorAvailability(
                doctor_id=doctor.id,
                day_of_week=day_of_week,
                start_time=time(h1, m1),
                end_time=time(h2, m2),
                slot_duration_min=slot_duration_min,
                is_active=True,
            )
            session.add(slot)

        await session.flush()
        print(f"Added {len(weekly_hours)} weekly availability block(s) for {full_name}")

        return {"doctor_id": doctor.id, "full_name": full_name, "specialty": specialty_name}


if __name__ == "__main__":
    import asyncio

    async def seed():
        # Example: add a General Physician, Mon/Wed/Fri 9am-1pm
        result = await add_doctor(
            full_name="Dr. Bilal Hassan",
            specialty_name="General Physician",
            bio="General physician with a focus on everyday health concerns and preventive care.",
            weekly_hours=[
                (1, "09:00", "13:00"),  # Monday
                (3, "09:00", "13:00"),  # Wednesday
                (5, "09:00", "13:00"),  # Friday
            ],
        )
        print(result)

    asyncio.run(seed())