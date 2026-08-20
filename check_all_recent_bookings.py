import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment, Patient, Doctor

async def check():
    async with get_db_session() as session:
        query = (
            select(Appointment)
            .options(
                selectinload(Appointment.patient),
                selectinload(Appointment.doctor),
            )
            .order_by(Appointment.created_at.desc())
            .limit(5)
        )
        results = (await session.execute(query)).scalars().all()

        print("-- 5 most recently CREATED appointments (any patient) --")
        for a in results:
            print({
                "appointment_id": a.id,
                "patient_name": a.patient.full_name,
                "patient_phone": a.patient.phone,
                "doctor_name": a.doctor.full_name,
                "appointment_time": a.appointment_time.isoformat(),
                "status": a.status.value,
                "created_at": a.created_at.isoformat(),
            })

if __name__ == "__main__":
    asyncio.run(check())