# appointment_mcp_server/appointment_mcp_server_main.py

import sys
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

from appointment_mcp_server.tools.search_doctors_tool import search_doctors_tool
from appointment_mcp_server.tools.get_doctor_details_tool import get_doctor_details_tool
from appointment_mcp_server.tools.check_doctor_availability_tool import check_doctor_availability_tool
from appointment_mcp_server.tools.search_existing_appointments_tool import search_existing_appointments_tool
from appointment_mcp_server.tools.create_patient_profile_tool import create_patient_profile_tool
from appointment_mcp_server.tools.get_patient_profile_tool import get_patient_profile_tool
from appointment_mcp_server.tools.book_appointment_tool import book_appointment_tool
from appointment_mcp_server.tools.reschedule_appointment_tool import reschedule_appointment_tool
from appointment_mcp_server.tools.cancel_appointment_tool import cancel_appointment_tool
from appointment_mcp_server.tools.search_specialties_tool import search_specialties_tool
from appointment_mcp_server.tools.update_patient_preferences_tool import update_patient_preferences_tool
from appointment_mcp_server.tools.search_policy_knowledge_tool import search_policy_knowledge_tool
# Create the MCP server instance — this name shows up in MCP clients
mcp = FastMCP("appointment-scheduling-server")


@mcp.tool()
async def search_doctors(doctor_name: str | None = None, specialty_name: str | None = None) -> list[dict]:
    """Search for active doctors by name and/or specialty (e.g. 'cardiologist')."""
    return await search_doctors_tool(doctor_name, specialty_name)


@mcp.tool()
async def get_doctor(doctor_id: int) -> dict | None:
    """Get full profile for one doctor by ID, including their weekly availability schedule."""
    return await get_doctor_details_tool(doctor_id)


@mcp.tool()
async def get_availability(
    doctor_id: int,
    start_date: date,
    end_date: date,
    time_of_day_preference: str | None = None,
) -> list[dict]:
    """Find available appointment slots for a doctor within a date range.
    time_of_day_preference can be 'morning', 'afternoon', 'evening', or None."""
    return await check_doctor_availability_tool(doctor_id, start_date, end_date, time_of_day_preference)


@mcp.tool()
async def search_appointments(
    patient_id: int,
    status: str | None = "booked",
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Search a patient's appointments, optionally filtered by status and date range."""
    return await search_existing_appointments_tool(patient_id, status, start_date, end_date)


@mcp.tool()
async def create_patient(
    full_name: str,
    phone: str,
    email: str | None = None,
    preferred_doctor_id: int | None = None,
) -> dict:
    """Create a new patient profile, or return the existing one if the phone number is already registered."""
    return await create_patient_profile_tool(full_name, phone, email, preferred_doctor_id)


@mcp.tool()
async def get_patient(patient_id: int | None = None, phone: str | None = None) -> dict | None:
    """Look up a patient by ID or phone number."""
    return await get_patient_profile_tool(patient_id, phone)


@mcp.tool()
async def book_appointment(
    doctor_id: int,
    patient_id: int,
    appointment_datetime: datetime,
    duration_minutes: int = 30,
    notes: str | None = None,
) -> dict:
    """Book an appointment for a patient with a doctor at a specific date & time.
    Checks for conflicts and suggests an alternative slot if unavailable."""
    return await book_appointment_tool(doctor_id, patient_id, appointment_datetime, duration_minutes, notes)


@mcp.tool()
async def reschedule_appointment(appointment_id: int, new_appointment_datetime: datetime) -> dict:
    """Reschedule an existing booked appointment to a new date & time."""
    return await reschedule_appointment_tool(appointment_id, new_appointment_datetime)


@mcp.tool()
async def cancel_appointment(appointment_id: int, cancellation_reason: str | None = None) -> dict:
    """Cancel a booked appointment. Sets status to cancelled, keeps the record for history."""
    return await cancel_appointment_tool(appointment_id, cancellation_reason)


@mcp.tool()
async def search_specialties(name: str | None = None) -> list[dict]:
    """List available medical specialties, optionally filtered by partial name."""
    return await search_specialties_tool(name)


@mcp.tool()
async def update_patient_preferences(
    patient_id: int,
    preferred_doctor_id: int | None = None,
    preferred_time_of_day: str | None = None,
) -> dict:
    """Save a patient's preferred doctor and/or preferred time of day for future visits."""
    return await update_patient_preferences_tool(patient_id, preferred_doctor_id, preferred_time_of_day)
@mcp.tool()
async def search_policy_knowledge(query: str, top_k: int = 3) -> list[dict]:
    """Search the clinic's knowledge base for policy, service, or FAQ information —
    cancellation policy, payment/insurance, clinic timings, general FAQs, etc.
    Use this instead of guessing when asked about clinic policies or general info."""
    return await search_policy_knowledge_tool(query, top_k)

if __name__ == "__main__":
    mcp.run()