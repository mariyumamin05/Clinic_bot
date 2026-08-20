# tests/test_tools.py

import sys
from pathlib import Path
import pytest
from datetime import date, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from appointment_mcp_server.tools.search_doctors_tool import search_doctors_tool
from appointment_mcp_server.tools.search_specialties_tool import search_specialties_tool
from appointment_mcp_server.tools.check_doctor_availability_tool import check_doctor_availability_tool
from appointment_mcp_server.tools.create_patient_profile_tool import create_patient_profile_tool
from appointment_mcp_server.tools.book_appointment_tool import book_appointment_tool
from appointment_mcp_server.tools.cancel_appointment_tool import cancel_appointment_tool


@pytest.mark.asyncio
async def test_search_specialties_returns_results():
    results = await search_specialties_tool()
    assert isinstance(results, list)
    assert len(results) > 0
    assert "name" in results[0]


@pytest.mark.asyncio
async def test_search_doctors_by_specialty():
    results = await search_doctors_tool(specialty_name="cardio")
    assert any(r["specialty"] == "Cardiology" for r in results)


@pytest.mark.asyncio
async def test_create_patient_dedups_by_phone():
    first = await create_patient_profile_tool(
        full_name="Pytest Patient", phone="09999900001"
    )
    second = await create_patient_profile_tool(
        full_name="Pytest Patient", phone="09999900001"
    )
    assert first["patient_id"] == second["patient_id"]
    assert second["newly_created"] is False


@pytest.mark.asyncio
async def test_double_booking_is_rejected():
    today = date.today()
    next_month = today + timedelta(days=30)
    slots = await check_doctor_availability_tool(1, today, next_month)
    if not slots:
        pytest.skip("no available slots to test against")

    from datetime import datetime
    target_dt = datetime.fromisoformat(slots[0]["datetime_iso"])

    patient = await create_patient_profile_tool(
        full_name="Pytest Double Book", phone="09999900002"
    )

    first = await book_appointment_tool(
        doctor_id=1, patient_id=patient["patient_id"], appointment_datetime=target_dt
    )
    assert first["success"] is True

    second = await book_appointment_tool(
        doctor_id=1, patient_id=patient["patient_id"], appointment_datetime=target_dt
    )
    assert second["success"] is False
    assert second["reason"] == "slot_unavailable"

    await cancel_appointment_tool(first["appointment_id"])


@pytest.mark.asyncio
async def test_cancel_nonexistent_appointment():
    result = await cancel_appointment_tool(appointment_id=999999)
    assert result["success"] is False
    assert result["reason"] == "not_found"