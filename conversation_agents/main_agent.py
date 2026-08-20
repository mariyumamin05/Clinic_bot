# conversation_agents/main_agent.py

import sys
import re
import json
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import os
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from openai import AsyncOpenAI
from sqlalchemy import select
from appointment_mcp_server.database.appointment_db_connection import get_db_session
from appointment_mcp_server.database.appointment_db_models import (
    ConversationSession, ConversationMessage, MessageRole,
)

from conversation_agents.booking_agent import handle_booking
from conversation_agents.search_agent import handle_search
from conversation_agents.reschedule_agent import handle_reschedule
from conversation_agents.cancel_agent import handle_cancel

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INTENT_PROMPT = """Classify the user's LATEST message for a medical clinic voice assistant,
using the conversation history for context. A short reply like "yes", "sure", "cancel it",
or "book that one" has NO meaning on its own — you MUST look at what the assistant just
said/asked to determine what the user is actually confirming or responding to.

Only return MULTIPLE intents when the user is asking for genuinely SEPARATE actions in
one message — e.g. "cancel my appointment tomorrow AND book a new one next week" is two
real actions (cancel + book).

Do NOT split into multiple intents just because a message contains supporting details
alongside a single request. Example: "I need to see a cardiologist next week, my phone
number is 03219876543, my name is Zara" is ONE intent ("search" or "book", depending on
whether they're asking to find options or explicitly asking to book) — the phone number
and name are supporting details for that one request, not a second request.

Respond ONLY with JSON in this exact shape, no other text:
{"intents": ["search" | "book" | "reschedule" | "cancel" | "other", ...]}
List each distinct intent once, in the order the patient mentioned them.
If there's only one request, return a list with one item — this is the common case.
"""

ACTION_KEYWORD_PATTERN = re.compile(
    r"\b(book|cancel|reschedul\w*|search|specialt\w*|doctor|appointment|available|availab\w*)\b",
    re.IGNORECASE,
)

# Exposes the intent(s) actually used to route the most recent
# handle_user_message call — used by the evaluation suite to score intent
# detection as its own metric, separate from tool selection.
_last_resolved_intents: list[str] = []


def get_last_resolved_intents() -> list[str]:
    return list(_last_resolved_intents)


def _looks_like_sticky_reply(text: str) -> bool:
    """A short reply with no new-topic keywords is very likely responding to
    whatever the assistant just asked, not starting a new request. This is a
    deterministic backstop for cases like a bare "yes"/"no"/"that's correct"
    after a proposed booking, cancellation, or reschedule — where per-turn LLM
    intent classification has proven unreliable even with history context,
    since nothing forces the model to recognize "stay with the same agent"."""
    words = text.strip().split()
    if len(words) > 6:
        return False
    if ACTION_KEYWORD_PATTERN.search(text):
        return False
    return True


async def _get_or_create_session(session_id: str) -> uuid.UUID:
    session_uuid = uuid.UUID(session_id)
    async with get_db_session() as session:
        result = await session.execute(
            select(ConversationSession).where(ConversationSession.id == session_uuid)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            session.add(ConversationSession(id=session_uuid))
            await session.flush()
    return session_uuid


async def _get_session_last_intent(session_uuid: uuid.UUID) -> str | None:
    async with get_db_session() as session:
        result = await session.execute(
            select(ConversationSession.last_intent).where(ConversationSession.id == session_uuid)
        )
        row = result.first()
        return row[0] if row else None


async def _set_session_last_intent(session_uuid: uuid.UUID, intent: str):
    async with get_db_session() as session:
        result = await session.execute(
            select(ConversationSession).where(ConversationSession.id == session_uuid)
        )
        record = result.scalar_one_or_none()
        if record:
            record.last_intent = intent


async def _load_history(session_uuid: uuid.UUID) -> list[dict]:
    async with get_db_session() as session:
        result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_uuid)
            .order_by(ConversationMessage.created_at)
        )
        rows = result.scalars().all()

    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in rows
        if msg.role in (MessageRole.user, MessageRole.assistant)
    ]


async def _save_message(session_uuid: uuid.UUID, role: MessageRole, content: str):
    async with get_db_session() as session:
        session.add(ConversationMessage(session_id=session_uuid, role=role, content=content))


async def _classify_intent(user_message: str, recent_history: list[dict]) -> list[str]:
    try:
        context_messages = recent_history[-6:] + [{"role": "user", "content": user_message}]

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                *context_messages,
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        intents = data.get("intents")
        if not isinstance(intents, list) or not intents:
            return ["search"]
        valid = {"search", "book", "reschedule", "cancel", "other"}
        seen = []
        for i in intents:
            if i in valid and i not in seen:
                seen.append(i)
        return seen or ["search"]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return ["search"]


async def handle_user_message(session_id: str, user_text: str, mcp_manager, on_chunk=None) -> str:
    """Main entry point. Loads this session's DB-persisted history, determines
    intent(s) — via deterministic sticky routing for short replies with no
    new-topic keywords, or LLM classification otherwise — resolves each to its
    handler and dedupes, routes in order, persists the new turn and the last
    handled intent (for the next turn's sticky check), and returns the reply."""
    global _last_resolved_intents

    session_uuid = await _get_or_create_session(session_id)
    history = await _load_history(session_uuid)

    await _save_message(session_uuid, MessageRole.user, user_text)

    messages = history + [{"role": "user", "content": user_text}]

    last_intent = await _get_session_last_intent(session_uuid)
    if last_intent and _looks_like_sticky_reply(user_text):
        intents = [last_intent]
    else:
        intents = await _classify_intent(user_text, history)

    handlers = {
        "search": handle_search,
        "book": handle_booking,
        "reschedule": handle_reschedule,
        "cancel": handle_cancel,
        "other": handle_search,
    }

    resolved = []  # list of (intent_label, handler), deduped by handler
    seen_handlers = set()
    for intent in intents:
        handler = handlers.get(intent, handle_search)
        if handler not in seen_handlers:
            seen_handlers.add(handler)
            resolved.append((intent, handler))

    _last_resolved_intents = [intent for intent, _ in resolved]

    stream_directly = on_chunk if len(resolved) == 1 else None

    reply_parts = []
    last_processed_intent = None
    for intent, handler in resolved:
        reply_text, _ = await handler(messages, mcp_manager, on_chunk=stream_directly)
        reply_parts.append(reply_text)
        messages = messages + [{"role": "assistant", "content": reply_text}]
        last_processed_intent = intent

    full_reply = "\n\n".join(reply_parts)
    await _save_message(session_uuid, MessageRole.assistant, full_reply)
    if last_processed_intent:
        await _set_session_last_intent(session_uuid, last_processed_intent)
    return full_reply


if __name__ == "__main__":
    import asyncio
    from backend.mcp_client import MCPClientManager

    async def test():
        manager = MCPClientManager()
        await manager.connect()

        booking_session_id = str(uuid.uuid4())
        print("-- Turn 1: propose --")
        r1 = await handle_user_message(booking_session_id, "I need to see a cardiologist next week in the afternoon, my phone is 03219876543, name is Zara Iqbal", manager)
        print(f"Agent: {r1}")
        print(f"Resolved intents: {get_last_resolved_intents()}\n")

        print("-- Turn 2: BARE confirmation, no keywords at all --")
        r2 = await handle_user_message(booking_session_id, "Yeah, that's correct.", manager)
        print(f"Agent: {r2}")
        print(f"Resolved intents: {get_last_resolved_intents()}\n")

        await manager.close()

    asyncio.run(test())