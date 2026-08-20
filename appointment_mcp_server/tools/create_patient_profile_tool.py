# appointment_mcp_server/tools/create_patient_profile_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Patient


async def create_patient_profile_tool(
    full_name: str,
    phone: str,
    email: str | None = None,
    preferred_doctor_id: int | None = None,
) -> dict:
    """
    Create a new patient profile, or return the existing one if the phone number
    is already registered (avoids duplicate patients on repeat calls).

    Args:
        full_name: Patient's full name
        phone: Patient's phone number (used as the uniqueness key)
        email: Optional email
        preferred_doctor_id: Optional preferred doctor's ID

    Returns:
        Dict with the patient's details and a flag indicating if it was newly created.
    """
    async with get_db_session() as session:
        # Check if a patient with this phone already exists
        existing_query = select(Patient).where(Patient.phone == phone)
        existing_result = await session.execute(existing_query)
        existing_patient = existing_result.scalar_one_or_none()

        if existing_patient:
            return {
                "patient_id": existing_patient.id,
                "full_name": existing_patient.full_name,
                "phone": existing_patient.phone,
                "email": existing_patient.email,
                "preferred_doctor_id": existing_patient.preferred_doctor_id,
                "newly_created": False,
            }

        new_patient = Patient(
            full_name=full_name,
            phone=phone,
            email=email,
            preferred_doctor_id=preferred_doctor_id,
        )
        session.add(new_patient)
        await session.flush()  # assigns new_patient.id without ending the transaction

        return {
            "patient_id": new_patient.id,
            "full_name": new_patient.full_name,
            "phone": new_patient.phone,
            "email": new_patient.email,
            "preferred_doctor_id": new_patient.preferred_doctor_id,
            "newly_created": True,
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Create new patient --")
        result = await create_patient_profile_tool(
            full_name="Zara Iqbal",
            phone="03219876543",
            email="zara@example.com",
        )
        print(result)

        print("\n-- Try creating same patient again (same phone) --")
        result = await create_patient_profile_tool(
            full_name="Zara Iqbal",
            phone="03219876543",
        )
        print(result)
        print("(should show newly_created: False, same patient_id as above)")

    asyncio.run(test())