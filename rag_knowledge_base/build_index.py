# rag_knowledge_base/build_index.py

import sys
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import os
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from openai import AsyncOpenAI

DOCS_DIR = Path(__file__).resolve().parent / "documents"
INDEX_DIR = Path(__file__).resolve().parent / "index"
INDEX_PATH = INDEX_DIR / "index.json"
EMBEDDING_MODEL = "text-embedding-3-small"

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def chunk_markdown(text: str, source_file: str) -> list[dict]:
    """Split a markdown file into chunks by '## ' section headers.
    Each chunk carries the document's top-level '# ' title (if present)
    for context, plus its own '## ' heading and body text."""
    title_match = re.match(r"^#\s+(.+)$", text.strip(), re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else source_file

    sections = re.split(r"(?m)^##\s+", text)
    chunks = []
    for section in sections[1:]:  # sections[0] is anything before the first '## '
        lines = section.strip().split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if not body:
            continue
        chunks.append({
            "source": source_file,
            "doc_title": doc_title,
            "heading": heading,
            "text": f"{heading}\n{body}",
        })
    return chunks


async def build_index():
    if not DOCS_DIR.exists():
        print(f"No documents folder found at {DOCS_DIR}")
        return

    all_chunks = []
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, md_file.name))

    if not all_chunks:
        print("No chunks found — check that .md files exist under rag_knowledge_base/documents/")
        return

    print(f"-- Embedding {len(all_chunks)} chunks from {DOCS_DIR} --")
    texts = [c["text"] for c in all_chunks]
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=texts)

    for chunk, embedding_obj in zip(all_chunks, response.data):
        chunk["embedding"] = embedding_obj.embedding

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps({
        "model": EMBEDDING_MODEL,
        "chunks": all_chunks,
    }), encoding="utf-8")

    print(f"Index built: {len(all_chunks)} chunks -> {INDEX_PATH}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(build_index())