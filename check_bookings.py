import asyncio
from appointment_mcp_server.tools.search_existing_appointments_tool import search_existing_appointments_tool

async def check():
    print("-- ALL appointments for patient 3 (Zara), any status --")
    results = await search_existing_appointments_tool(patient_id=3, status=None)
    for r in results:
        print(r)

if __name__ == "__main__":
    asyncio.run(check())