# rag_knowledge_base/retriever.py

import sys
import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import os
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from openai import AsyncOpenAI

INDEX_PATH = Path(__file__).resolve().parent / "index" / "index.json"
EMBEDDING_MODEL = "text-embedding-3-small"

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_index_cache: dict | None = None


def _load_index() -> dict:
    global _index_cache
    if _index_cache is None:
        if not INDEX_PATH.exists():
            raise FileNotFoundError(
                f"No index found at {INDEX_PATH}. Run 'python -m rag_knowledge_base.build_index' first."
            )
        _index_cache = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return _index_cache


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
    """Embed the query, compare against all indexed chunks via cosine
    similarity, return the top_k most relevant chunks with their source."""
    index = _load_index()
    chunks = index["chunks"]

    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    query_embedding = response.data[0].embedding

    scored = [
        {
            "text": c["text"],
            "source": c["source"],
            "doc_title": c["doc_title"],
            "score": _cosine_similarity(query_embedding, c["embedding"]),
        }
        for c in chunks
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


if __name__ == "__main__":
    import asyncio

    async def test():
        queries = [
            "What is your cancellation policy?",
            "Do you take insurance?",
            "Can I book for my mom?",
        ]
        for q in queries:
            print(f"\n-- Query: {q} --")
            results = await search_knowledge_base(q, top_k=2)
            for r in results:
                print(f"[{r['score']:.3f}] ({r['source']}) {r['text'][:100]}...")

    asyncio.run(test())