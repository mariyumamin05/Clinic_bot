# appointment_mcp_server/tools/book_appointment_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment
from appointment_mcp_server.tools.check_doctor_availability_tool import validate_appointment_slot

FK_VIOLATION = "23503"


async def book_appointment_tool(
    doctor_id: int,
    patient_id: int,
    appointment_datetime: datetime,
    duration_minutes: int = 30,
    notes: str | None = None,
) -> dict:
    # Coerce naive datetimes to UTC explicitly — a naive and an aware
    # datetime representing "the same clock time" are NOT the same instant
    # unless we force one consistent interpretation. Without this, two
    # bookings for what looks like the identical slot can silently bypass
    # the database's double-booking constraint (confirmed happening in
    # evaluation suite S07 — two appointments booked for the same doctor/
    # patient/time because one call passed a naive datetime and the other
    # passed a UTC-aware one).
    if appointment_datetime.tzinfo is None:
        appointment_datetime = appointment_datetime.replace(tzinfo=timezone.utc)
    else:
        appointment_datetime = appointment_datetime.astimezone(timezone.utc)

    validation = await validate_appointment_slot(doctor_id, appointment_datetime, duration_minutes)
    if not validation["valid"]:
        return {
            "success": False,
            "reason": validation["reason"],
            "suggested_slot": validation.get("suggested_slot"),
        }

    async with get_db_session() as session:
        try:
            new_appointment = Appointment(
                doctor_id=doctor_id,
                patient_id=patient_id,
                appointment_time=appointment_datetime,
                duration_minutes=duration_minutes,
                end_time=appointment_datetime,
                notes=notes,
            )
            session.add(new_appointment)
            await session.flush()

            return {
                "success": True,
                "appointment_id": new_appointment.id,
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "appointment_time": appointment_datetime.isoformat(),
                "duration_minutes": duration_minutes,
                "status": "booked",
            }

        except IntegrityError as e:
            await session.rollback()
            sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)

            if sqlstate == FK_VIOLATION:
                return {
                    "success": False,
                    "reason": "invalid_reference",
                    "detail": "doctor_id or patient_id does not exist",
                }

            return {
                "success": False,
                "reason": "slot_unavailable",
                "suggested_slot": None,
            }


if __name__ == "__main__":
    import asyncio
    from datetime import date, timedelta
    from appointment_mcp_server.tools.check_doctor_availability_tool import check_doctor_availability_tool

    async def test():
        today = date.today()
        next_week = today + timedelta(days=7)
        slots = await check_doctor_availability_tool(1, today, next_week)

        if not slots:
            print("No available slots found to test booking with.")
            return

        target_dt = datetime.fromisoformat(slots[0]["datetime_iso"])

        print(f"-- Booking Dr. Ahmed (ID 1) for patient ID 3 at {target_dt} --")
        print(await book_appointment_tool(doctor_id=1, patient_id=3, appointment_datetime=target_dt))

        print("\n-- Trying to double-book the SAME slot, but as a NAIVE datetime "
              "(strips tzinfo — this is the exact bug pattern from S07) --")
        naive_dt = target_dt.replace(tzinfo=None)
        print(await book_appointment_tool(doctor_id=1, patient_id=3, appointment_datetime=naive_dt))

        print("\n-- Trying to double-book the SAME slot (original aware datetime, should fail: slot_unavailable) --")
        print(await book_appointment_tool(doctor_id=1, patient_id=3, appointment_datetime=target_dt))

        print("\n-- Booking with a bogus patient_id=99999 (should fail: invalid_reference) --")
        target_dt2 = datetime.fromisoformat(slots[1]["datetime_iso"]) if len(slots) > 1 else target_dt
        print(await book_appointment_tool(doctor_id=1, patient_id=99999, appointment_datetime=target_dt2))

    asyncio.run(test())