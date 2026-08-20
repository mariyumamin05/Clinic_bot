# evaluation_suite/mcp_recorder.py

import time


class RecordingMCPManager:
    """Wraps a real MCPClientManager transparently, logging every tool call
    (name, args, result, latency) without touching production code. All
    other calls (tools_subset, connect, close) pass straight through."""

    def __init__(self, real_manager):
        self._real = real_manager
        self.calls = []  # list of {name, args, result, latency_s, timestamp}

    async def connect(self):
        await self._real.connect()

    async def close(self):
        await self._real.close()

    def tools_subset(self, names):
        return self._real.tools_subset(names)

    @property
    def openai_tools(self):
        return self._real.openai_tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        start = time.perf_counter()
        result = await self._real.call_tool(name, arguments)
        latency = time.perf_counter() - start
        self.calls.append({
            "name": name,
            "args": arguments,
            "result": result,
            "latency_s": latency,
            "timestamp": time.time(),
        })
        return result

    def calls_since(self, index: int) -> list[dict]:
        return self.calls[index:]