# appointment_mcp_server/tools/search_policy_knowledge_tool.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from rag_knowledge_base.retriever import search_knowledge_base


async def search_policy_knowledge_tool(query: str, top_k: int = 3) -> list[dict]:
    """Search the clinic's policy/FAQ knowledge base for information relevant
    to the patient's question. Returns the most relevant text chunks with
    their source document, so the agent can ground its answer in real content
    instead of guessing."""
    results = await search_knowledge_base(query, top_k=top_k)
    return [
        {"text": r["text"], "source": r["doc_title"], "relevance": round(r["score"], 3)}
        for r in results
    ]


if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Searching for 'cancellation policy' --")
        results = await search_policy_knowledge_tool("cancellation policy")
        for r in results:
            print(r)

        print("\n-- Searching for 'insurance' --")
        results2 = await search_policy_knowledge_tool("do you accept insurance")
        for r in results2:
            print(r)

    asyncio.run(test())