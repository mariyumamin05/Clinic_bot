# appointment_mcp_server/tools/search_existing_appointments_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import date, datetime, time, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment, AppointmentStatus,Doctor


async def search_existing_appointments_tool(
    patient_id: int,
    status: str | None = "booked",  # "booked" | "cancelled" | "completed" | "no_show" | None (=all)
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """
    Search a patient's appointments, optionally filtered by status and date range.

    Args:
        patient_id: The patient's ID
        status: Filter by status, or None for all statuses. Defaults to "booked".
        start_date: Optional earliest date (inclusive)
        end_date: Optional latest date (inclusive)

    Returns:
        List of dicts with appointment + doctor details, sorted by appointment_time.
    """
    async with get_db_session() as session:
        query = (
            select(Appointment)
            .options(
                selectinload(Appointment.doctor).selectinload(Doctor.specialty),
            )
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.appointment_time)
        )

        if status:
            query = query.where(Appointment.status == AppointmentStatus(status))

        if start_date:
            query = query.where(
                Appointment.appointment_time >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            )
        if end_date:
            query = query.where(
                Appointment.appointment_time <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)
            )

        result = await session.execute(query)
        appointments = result.scalars().all()

        return [
            {
                "appointment_id": appt.id,
                "doctor_name": appt.doctor.full_name,
                "specialty": appt.doctor.specialty.name if appt.doctor.specialty else None,
                "appointment_time": appt.appointment_time.isoformat(),
                "duration_minutes": appt.duration_minutes,
                "status": appt.status.value,
                "notes": appt.notes,
            }
            for appt in appointments
        ]


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Patient ID 1, booked appointments (should be empty, none booked yet) --")
        results = await search_existing_appointments_tool(1)
        for r in results:
            print(r)
        if not results:
            print("(no results — expected, since we haven't booked anything yet)")

        print("\n-- Patient ID 1, ALL statuses --")
        results = await search_existing_appointments_tool(1, status=None)
        for r in results:
            print(r)
        if not results:
            print("(no results — expected)")

    asyncio.run(test())