# appointment_mcp_server/tools/reschedule_appointment_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment, AppointmentStatus
from appointment_mcp_server.tools.check_doctor_availability_tool import validate_appointment_slot

FK_VIOLATION = "23503"


async def reschedule_appointment_tool(
    appointment_id: int,
    new_appointment_datetime: datetime,
) -> dict:
    # Same coercion as book_appointment_tool — a naive and a UTC-aware
    # datetime for "the same clock time" are NOT the same instant unless
    # forced to one consistent interpretation. Without this, a reschedule
    # could land on a timestamp that doesn't actually match an already-
    # booked slot, silently bypassing the double-booking constraint.
    if new_appointment_datetime.tzinfo is None:
        new_appointment_datetime = new_appointment_datetime.replace(tzinfo=timezone.utc)
    else:
        new_appointment_datetime = new_appointment_datetime.astimezone(timezone.utc)

    async with get_db_session() as session:
        query = select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.status == AppointmentStatus.booked,
        )
        appointment = (await session.execute(query)).scalar_one_or_none()

        if not appointment:
            return {"success": False, "reason": "not_found", "suggested_slot": None}

        validation = await validate_appointment_slot(
            appointment.doctor_id,
            new_appointment_datetime,
            appointment.duration_minutes,
            exclude_appointment_id=appointment_id,
        )
        if not validation["valid"]:
            return {
                "success": False,
                "reason": validation["reason"],
                "suggested_slot": validation.get("suggested_slot"),
            }

        try:
            old_time = appointment.appointment_time.isoformat()
            appointment.appointment_time = new_appointment_datetime
            await session.flush()

            return {
                "success": True,
                "appointment_id": appointment.id,
                "old_time": old_time,
                "new_time": new_appointment_datetime.isoformat(),
                "status": "booked",
            }

        except IntegrityError as e:
            await session.rollback()
            sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
            if sqlstate == FK_VIOLATION:
                return {"success": False, "reason": "invalid_reference", "detail": "doctor_id does not exist"}
            return {"success": False, "reason": "slot_unavailable", "suggested_slot": None}


if __name__ == "__main__":
    import asyncio
    from datetime import date, timedelta
    from appointment_mcp_server.tools.check_doctor_availability_tool import check_doctor_availability_tool
    from appointment_mcp_server.tools.book_appointment_tool import book_appointment_tool

    async def test():
        today = date.today()
        next_week = today + timedelta(days=7)
        slots = await check_doctor_availability_tool(1, today, next_week)

        if len(slots) < 2:
            print("Not enough available slots to test rescheduling.")
            return

        occupied_dt = datetime.fromisoformat(slots[0]["datetime_iso"])
        target_dt = datetime.fromisoformat(slots[1]["datetime_iso"])

        print(f"-- Booking a DIFFERENT appointment at {occupied_dt} to occupy that slot --")
        occupying = await book_appointment_tool(doctor_id=1, patient_id=3, appointment_datetime=occupied_dt)
        print(occupying)
        if not occupying.get("success"):
            print("Could not set up occupied slot, aborting test.")
            return

        print(f"\n-- Rescheduling appointment ID 2 to {occupied_dt} (should FAIL — occupied by a different appointment) --")
        print(await reschedule_appointment_tool(appointment_id=2, new_appointment_datetime=occupied_dt))

        print(f"\n-- Same attempt as a NAIVE datetime (strips tzinfo — should STILL fail) --")
        naive_occupied_dt = occupied_dt.replace(tzinfo=None)
        print(await reschedule_appointment_tool(appointment_id=2, new_appointment_datetime=naive_occupied_dt))

        print("\n-- Rescheduling a non-existent appointment ID 999 --")
        print(await reschedule_appointment_tool(appointment_id=999, new_appointment_datetime=target_dt))

    asyncio.run(test())