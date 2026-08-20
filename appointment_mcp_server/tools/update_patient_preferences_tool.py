# appointment_mcp_server/tools/update_patient_preferences_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Patient


async def update_patient_preferences_tool(
    patient_id: int,
    preferred_doctor_id: int | None = None,
    preferred_time_of_day: str | None = None,
) -> dict:
    """Persist a patient's stated preferences so future sessions/calls can
    resolve phrases like 'book my usual doctor'. Only overwrites fields
    explicitly passed (non-None)."""
    async with get_db_session() as session:
        patient = (await session.execute(
            select(Patient).where(Patient.id == patient_id)
        )).scalar_one_or_none()

        if not patient:
            return {"success": False, "reason": "not_found"}

        if preferred_doctor_id is not None:
            patient.preferred_doctor_id = preferred_doctor_id
        if preferred_time_of_day is not None:
            patient.preferred_time_of_day = preferred_time_of_day

        await session.flush()

        return {
            "success": True,
            "patient_id": patient.id,
            "preferred_doctor_id": patient.preferred_doctor_id,
            "preferred_time_of_day": patient.preferred_time_of_day,
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Setting patient 3's preferred doctor to ID 1 --")
        print(await update_patient_preferences_tool(patient_id=3, preferred_doctor_id=1))

        print("\n-- Updating a non-existent patient (should fail) --")
        print(await update_patient_preferences_tool(patient_id=99999, preferred_doctor_id=1))

    asyncio.run(test())