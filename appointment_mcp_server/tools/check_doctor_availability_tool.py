# appointment_mcp_server/tools/check_doctor_availability_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import (
    Doctor, DoctorAvailability, Appointment, AppointmentStatus, ClinicClosure,
)


def _time_of_day_matches(slot_time: time, preference: str | None) -> bool:
    if not preference:
        return True
    hour = slot_time.hour
    if preference == "morning":
        return 6 <= hour < 12
    if preference == "afternoon":
        return 12 <= hour < 17
    if preference == "evening":
        return 17 <= hour < 21
    return True


async def check_doctor_availability_tool(
    doctor_id: int,
    start_date: date,
    end_date: date,
    time_of_day_preference: str | None = None,
) -> list[dict]:
    """
    Find available appointment slots for a doctor within a date range.
    Skips inactive doctors and clinic-closed dates entirely.
    """
    async with get_db_session() as session:
        doctor = (await session.execute(
            select(Doctor).where(Doctor.id == doctor_id)
        )).scalar_one_or_none()
        if not doctor or not doctor.is_active:
            return []

        avail_query = select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.is_active == True,
        )
        weekly_template = (await session.execute(avail_query)).scalars().all()
        if not weekly_template:
            return []

        template_by_day = {}
        for slot in weekly_template:
            template_by_day.setdefault(slot.day_of_week, []).append(slot)

        range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        range_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        booked_query = select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.booked,
            Appointment.appointment_time >= range_start,
            Appointment.appointment_time <= range_end,
        )
        booked_appointments = (await session.execute(booked_query)).scalars().all()
        booked_times = {appt.appointment_time for appt in booked_appointments}

        closure_query = select(ClinicClosure.closure_date).where(
            ClinicClosure.closure_date >= start_date,
            ClinicClosure.closure_date <= end_date,
        )
        closed_dates = {row[0] for row in (await session.execute(closure_query)).all()}

        available_slots = []
        current_date = start_date
        while current_date <= end_date:
            if current_date in closed_dates:
                current_date += timedelta(days=1)
                continue

            day_of_week = (current_date.weekday() + 1) % 7

            for template_slot in template_by_day.get(day_of_week, []):
                slot_start = datetime.combine(current_date, template_slot.start_time, tzinfo=timezone.utc)
                slot_end = datetime.combine(current_date, template_slot.end_time, tzinfo=timezone.utc)
                duration = timedelta(minutes=template_slot.slot_duration_min)

                slot_time = slot_start
                while slot_time + duration <= slot_end:
                    if slot_time not in booked_times and _time_of_day_matches(slot_time.time(), time_of_day_preference):
                        available_slots.append({
                            "date": current_date.isoformat(),
                            "time": slot_time.strftime("%H:%M"),
                            "datetime_iso": slot_time.isoformat(),
                        })
                    slot_time += duration

            current_date += timedelta(days=1)

        return available_slots


async def validate_appointment_slot(
    doctor_id: int,
    start_dt: datetime,
    duration_minutes: int,
    exclude_appointment_id: int | None = None,
) -> dict:
    """
    Validate a specific [start_dt, start_dt + duration_minutes) range for booking.
    """
    async with get_db_session() as session:
        doctor = (await session.execute(
            select(Doctor).where(Doctor.id == doctor_id)
        )).scalar_one_or_none()
        if not doctor or not doctor.is_active:
            return {"valid": False, "reason": "doctor_unavailable", "suggested_slot": None}

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        closure = (await session.execute(
            select(ClinicClosure).where(ClinicClosure.closure_date == start_dt.date())
        )).scalar_one_or_none()
        if closure:
            return {"valid": False, "reason": "clinic_closed", "suggested_slot": None}

        day_of_week = (start_dt.weekday() + 1) % 7
        template = (await session.execute(
            select(DoctorAvailability).where(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.day_of_week == day_of_week,
                DoctorAvailability.is_active == True,
            )
        )).scalars().all()

        fits_window = any(
            slot.start_time <= start_dt.time() and end_dt.time() <= slot.end_time
            for slot in template
            if end_dt.date() == start_dt.date()
        )
        if not fits_window:
            return {"valid": False, "reason": "outside_availability", "suggested_slot": None}

        overlap_query = select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.booked,
            Appointment.appointment_time < end_dt,
            Appointment.end_time > start_dt,
        )
        if exclude_appointment_id is not None:
            overlap_query = overlap_query.where(Appointment.id != exclude_appointment_id)

        overlapping = (await session.execute(overlap_query)).scalars().first()
        if overlapping:
            fallback = await check_doctor_availability_tool(doctor_id, start_dt.date(), start_dt.date())
            future = [s for s in fallback if s["datetime_iso"] > start_dt.isoformat()]
            return {
                "valid": False,
                "reason": "slot_unavailable",
                "suggested_slot": future[0] if future else None,
            }

        return {"valid": True}


if __name__ == "__main__":
    import asyncio
    from datetime import date as _date, timedelta as _td

    async def test():
        today = _date.today()
        next_week = today + _td(days=7)

        print(f"-- Dr. Ahmed (ID 1) availability, {today} to {next_week}, afternoon only --")
        for r in await check_doctor_availability_tool(1, today, next_week, time_of_day_preference="afternoon"):
            print(r)

        print(f"\n-- Dr. Ahmed (ID 1) availability, {today} to {next_week}, no filter --")
        for r in await check_doctor_availability_tool(1, today, next_week):
            print(r)

    asyncio.run(test())