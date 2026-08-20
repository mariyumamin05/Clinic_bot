# conversation_agents/base_agent.py

import json
import os
import re
import datetime
from typing import Callable, Awaitable, Optional
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

SENSITIVE_TOOLS = {"book_appointment", "cancel_appointment", "reschedule_appointment"}

ID_ARG_KEYS = {"patient_id", "doctor_id", "appointment_id"}

CONFIRMATION_PATTERNS = [
    re.compile(r"\byes\b"), re.compile(r"\byeah\b"), re.compile(r"\byep\b"),
    re.compile(r"\byup\b"), re.compile(r"\bconfirm(ed)?\b"), re.compile(r"\bsure\b"),
    re.compile(r"\bcorrect\b"), re.compile(r"\bbook it\b"), re.compile(r"\bdo it\b"),
    re.compile(r"\bgo ahead\b"), re.compile(r"\bplease book\b"), re.compile(r"\bthat works\b"),
    re.compile(r"\bsounds good\b"), re.compile(r"\baffirmative\b"), re.compile(r"\bokay\b"),
    re.compile(r"\bplease cancel\b"), re.compile(r"\bplease proceed\b"), re.compile(r"\bproceed\b"),
]

FALSE_SUCCESS_PHRASES = (
    "successfully booked", "has been booked", "is booked", "appointment is confirmed",
    "successfully cancelled", "has been cancelled", "successfully rescheduled",
    "has been rescheduled", "is now cancelled",
)


def _has_recent_confirmation(messages: list[dict]) -> bool:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = (msg.get("content") or "").lower()
            return any(p.search(text) for p in CONFIRMATION_PATTERNS)
    return False


def _claims_success_language(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in FALSE_SUCCESS_PHRASES)


def _extract_ids(result) -> set[int]:
    """Pull any patient_id/doctor_id/appointment_id values out of a tool
    RESULT (dict, or list of dicts) so we know which IDs are 'earned' —
    actually returned by a real lookup this turn — versus guessed."""
    found = set()
    items = result if isinstance(result, list) else [result]
    for item in items:
        if isinstance(item, dict):
            for key in ID_ARG_KEYS:
                val = item.get(key)
                if isinstance(val, int):
                    found.add(val)
    return found


async def run_agent_turn(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    mcp_manager,
    model: str = "gpt-4o-mini",
    max_tool_rounds: int = 5,
    on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
) -> tuple[str, list[dict]]:
    """Runs one user turn through OpenAI's tool-calling loop.

    Two code-level safety nets, in addition to prompt instructions:
    1. Confirmation gate — sensitive tools (book/cancel/reschedule) are
       blocked unless the patient's last message contains an affirmative.
    2. ID provenance check — any patient_id/doctor_id/appointment_id argument
       must match a value actually RETURNED by a tool call earlier THIS turn.
       Prevents the model from guessing/reusing a stale or fabricated ID,
       which can otherwise silently act on — or leak — a different patient's
       real data.
    """
    today_str = datetime.date.today().strftime("%A, %B %d, %Y")
    full_system_prompt = (
        f"{system_prompt}\n\nToday's real date is {today_str}. "
        "Always use this as the actual current date for relative references "
        "like 'tomorrow', 'today', or 'next week' — never assume any other date.\n\n"
        "If a tool result has \"reason\": \"confirmation_required\", it means you "
        "tried to act before the patient explicitly confirmed. Do NOT retry the "
        "tool call, and do NOT tell the patient the action succeeded — instead, "
        "clearly restate what you're about to do and ask the patient to confirm.\n\n"
        "Never say you are 'processing', 'confirming', or 'working on' the request "
        "unless you have just called a tool THIS turn to actually do it. If you're "
        "unsure what to do next, ask a clarifying question instead of claiming "
        "you're handling something in the background.\n\n"
        "NEVER invent or guess an ID (doctor_id, patient_id, appointment_id). Only ever "
        "use an ID that was actually returned by a tool call earlier in THIS conversation "
        "— never reuse an ID from memory, assume a default, or make one up. If you don't "
        "have the ID you need, call the appropriate search/lookup tool again first."
    )
    convo = [{"role": "system", "content": full_system_prompt}, *messages]

    blocked_this_turn = False
    known_ids: set[int] = set()

    for _ in range(max_tool_rounds):
        stream = await client.chat.completions.create(
            model=model,
            messages=convo,
            tools=tools if tools else None,
            stream=True,
        )

        full_text = ""
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.content:
                full_text += delta.content
                if on_chunk:
                    await on_chunk(delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": None, "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

        if not tool_calls_acc:
            if blocked_this_turn and _claims_success_language(full_text):
                corrected = (
                    "I need to stop you there — I haven't actually completed that "
                    "action yet, I need you to explicitly confirm first. Should I "
                    "go ahead?"
                )
                convo.append({"role": "assistant", "content": corrected})
                return corrected, convo[1:]

            convo.append({"role": "assistant", "content": full_text})
            return full_text, convo[1:]

        ordered_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]
        convo.append({
            "role": "assistant",
            "content": full_text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in ordered_calls
            ],
        })

        for tc in ordered_calls:
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                convo.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"success": False, "reason": "invalid_tool_arguments"}),
                })
                continue

            # ID provenance check — block if any ID argument wasn't actually
            # returned by an earlier tool call this turn.
            is_sensitive = tc["name"] in SENSITIVE_TOOLS
            unverified = [
                (k, v) for k, v in args.items()
                if k in ID_ARG_KEYS and isinstance(v, int) and v not in known_ids
                and (is_sensitive or known_ids)
            ]
            if unverified:
                bad_key, bad_val = unverified[0]
                convo.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({
                        "success": False,
                        "reason": "unverified_id",
                        "detail": f"{bad_key}={bad_val} was not confirmed by a lookup "
                                  f"this conversation — call the relevant search/lookup "
                                  f"tool first before using this ID.",
                    }),
                })
                continue

            if tc["name"] in SENSITIVE_TOOLS and not _has_recent_confirmation(messages):
                blocked_this_turn = True
                convo.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({
                        "success": False,
                        "reason": "confirmation_required",
                        "detail": "The patient has not explicitly confirmed this action yet.",
                    }),
                })
                continue

            try:
                result = await mcp_manager.call_tool(tc["name"], args)
            except Exception as e:
                result = {"success": False, "reason": "tool_error", "detail": str(e)}

            known_ids |= _extract_ids(result)

            if tc["name"] in SENSITIVE_TOOLS and result.get("success") is False:
                blocked_this_turn = True

            convo.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result),
            })

    return "I'm having trouble completing that — could you rephrase?", convo[1:]