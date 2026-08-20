# backend/mcp_client.py

import sys
import json
from pathlib import Path
from contextlib import AsyncExitStack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientManager:
    """Owns a single long-lived MCP session connected to the appointment
    server subprocess. Connected once at FastAPI startup, closed at shutdown."""

    def __init__(self):
        self.session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self.openai_tools: list[dict] = []

    async def connect(self):
        self._exit_stack = AsyncExitStack()
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(PROJECT_ROOT / "appointment_mcp_server" / "appointment_mcp_server_main.py")],
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

        list_result = await self.session.list_tools()
        self.openai_tools = [self._mcp_tool_to_openai_schema(t) for t in list_result.tools]

    async def close(self):
        if self._exit_stack:
            await self._exit_stack.aclose()

    @staticmethod
    def _mcp_tool_to_openai_schema(tool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }

    def tools_subset(self, names: list[str]) -> list[dict]:
        """OpenAI tool schemas for only the given names — scopes each specialized
        agent to just the MCP tools it's allowed to call."""
        return [t for t in self.openai_tools if t["function"]["name"] in names]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        print(f"\n[MCP CALL] {name}({arguments})")
        result = await self.session.call_tool(name, arguments=arguments)

        # MCP's own error signal — a server-side exception in the tool. Return
        # an explicit failure shape so the agent has a real "reason" to react
        # to, instead of guessing at an empty/ambiguous result.
        if getattr(result, "isError", False):
            detail = ""
            if result.content:
                block = result.content[0]
                if hasattr(block, "text"):
                    detail = block.text
            output = {"success": False, "reason": "mcp_tool_error", "detail": detail}
            print(f"[MCP RESULT] {name} -> {output}")    
            return output

        if result.content:
            block = result.content[0]
            if hasattr(block, "text"):
                try:
                    output = json.loads(block.text)
                    print(f"[MCP RESULT] {name} -> {output}")
                    return output
                except json.JSONDecodeError:
                    output = {"success": False, "reason": "invalid_tool_response", "detail": block.text}
                    print(f"[MCP RESULT] {name} -> {output}")
                    return output

        return {"success": False, "reason": "empty_tool_response"}


mcp_manager = MCPClientManager()


if __name__ == "__main__":
    import asyncio

    async def test():
        manager = MCPClientManager()
        await manager.connect()
        print(f"Connected. {len(manager.openai_tools)} tools available:\n")
        for tool in manager.openai_tools:
            print(f"- {tool['function']['name']}: {tool['function']['description']}")

        print("\n-- Calling search_doctors tool via MCP protocol --")
        result = await manager.call_tool("search_doctors", {"specialty_name": "cardio"})
        print(result)

        print("\n-- Calling a NON-EXISTENT tool (should surface as a clean error, not empty {}) --")
        result2 = await manager.call_tool("this_tool_does_not_exist", {})
        print(result2)

        await manager.close()

    asyncio.run(test())