# evaluation_suite/cleanup.py
import sys
import asyncio
from pathlib import Path
from sqlalchemy import select, delete

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment, Patient


async def cleanup():
    async with get_db_session() as session:
        patients = (await session.execute(
            select(Patient).where(Patient.full_name.ilike("Eval Patient%"))
        )).scalars().all()
        patient_ids = [p.id for p in patients]

        if not patient_ids:
            print("No eval patients found — nothing to clean up.")
            return

        await session.execute(delete(Appointment).where(Appointment.patient_id.in_(patient_ids)))
        await session.execute(delete(Patient).where(Patient.id.in_(patient_ids)))
        print(f"Deleted {len(patient_ids)} eval patients and their appointments.")


if __name__ == "__main__":
    asyncio.run(cleanup())