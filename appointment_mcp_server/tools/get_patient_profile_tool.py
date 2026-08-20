# appointment_mcp_server/tools/get_patient_profile_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Patient


async def get_patient_profile_tool(patient_id: int | None = None, phone: str | None = None) -> dict | None:
    """
    Look up a patient by ID or phone number. At least one must be provided.

    Args:
        patient_id: The patient's ID
        phone: The patient's phone number

    Returns:
        Dict with patient details, or None if not found.
    """
    if not patient_id and not phone:
        raise ValueError("Must provide either patient_id or phone")

    async with get_db_session() as session:
        query = select(Patient).options(selectinload(Patient.preferred_doctor))

        if patient_id:
            query = query.where(Patient.id == patient_id)
        else:
            query = query.where(Patient.phone == phone)

        result = await session.execute(query)
        patient = result.scalar_one_or_none()

        if not patient:
            return None

        return {
            "patient_id": patient.id,
            "full_name": patient.full_name,
            "phone": patient.phone,
            "email": patient.email,
            "preferred_doctor_id": patient.preferred_doctor_id,
            "preferred_doctor_name": patient.preferred_doctor.full_name if patient.preferred_doctor else None,
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Lookup by patient_id=3 (Zara) --")
        result = await get_patient_profile_tool(patient_id=3)
        print(result)

        print("\n-- Lookup by phone='03219876543' --")
        result = await get_patient_profile_tool(phone="03219876543")
        print(result)

        print("\n-- Lookup by patient_id=999 (should not exist) --")
        result = await get_patient_profile_tool(patient_id=999)
        print(result)

    asyncio.run(test())