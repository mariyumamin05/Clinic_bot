# appointment_mcp_server/tools/cancel_appointment_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import Appointment, AppointmentStatus


async def cancel_appointment_tool(appointment_id: int, cancellation_reason: str | None = None) -> dict:
    """
    Cancel a booked appointment (soft delete — status flips to 'cancelled', row is kept).

    Args:
        appointment_id: The appointment to cancel
        cancellation_reason: Optional reason for cancellation

    Returns:
        On success: {"success": True, "appointment_id": ..., "status": "cancelled"}
        On failure: {"success": False, "reason": "not_found" | "already_cancelled"}
    """
    async with get_db_session() as session:
        query = select(Appointment).where(Appointment.id == appointment_id)
        result = await session.execute(query)
        appointment = result.scalar_one_or_none()

        if not appointment:
            return {"success": False, "reason": "not_found"}

        if appointment.status == AppointmentStatus.cancelled:
            return {"success": False, "reason": "already_cancelled"}

        appointment.status = AppointmentStatus.cancelled
        appointment.cancellation_reason = cancellation_reason
        await session.flush()

        return {
            "success": True,
            "appointment_id": appointment.id,
            "status": "cancelled",
            "cancellation_reason": cancellation_reason,
        }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Cancelling appointment ID 1 --")
        result = await cancel_appointment_tool(appointment_id=1, cancellation_reason="Patient requested cancellation")
        print(result)

        print("\n-- Trying to cancel the SAME appointment again (should fail) --")
        result2 = await cancel_appointment_tool(appointment_id=1)
        print(result2)

        print("\n-- Trying to cancel a non-existent appointment ID 999 --")
        result3 = await cancel_appointment_tool(appointment_id=999)
        print(result3)

    asyncio.run(test())