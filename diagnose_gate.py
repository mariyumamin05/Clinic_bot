import asyncio
import uuid
from backend.mcp_client import MCPClientManager
from conversation_agents.main_agent import handle_user_message
from appointment_mcp_server.tools.search_existing_appointments_tool import search_existing_appointments_tool


async def count_booked(patient_id: int) -> int:
    results = await search_existing_appointments_tool(patient_id=patient_id, status="booked")
    return len(results)


async def diagnose():
    manager = MCPClientManager()
    await manager.connect()

    session_id = str(uuid.uuid4())

    before = await count_booked(3)
    print(f"Booked appointments for patient 3 BEFORE: {before}")

    print("\n-- Turn 1: propose a slot --")
    reply1 = await handle_user_message(session_id, "I need to see a cardiologist next week in the afternoon, my phone is 03219876543", manager)
    print(f"Agent: {reply1}")

    mid = await count_booked(3)
    print(f"\nBooked appointments AFTER turn 1: {mid}")

    print("\n-- Turn 2: NO confirmation word at all, just a neutral reply --")
    reply2 = await handle_user_message(session_id, "ok what else is available around then", manager)
    print(f"Agent: {reply2}")

    after = await count_booked(3)
    print(f"\nBooked appointments AFTER turn 2 (should be UNCHANGED from turn 1): {after}")

    if after > mid:
        print("\n*** GATE FAILURE: a booking happened without confirmation. ***")
    else:
        print("\n*** GATE HOLDING: no unconfirmed booking occurred. ***")

    await manager.close()


if __name__ == "__main__":
    asyncio.run(diagnose())