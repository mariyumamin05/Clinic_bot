# Architecture

## Diagram

Browser client → WebSocket + Deepgram (STT/TTS) → Main agent → Specialized
agents → MCP appointment server (+ RAG knowledge base) → PostgreSQL.

## Layers

### 1. Browser client
Captures microphone audio via `MediaRecorder` (WebM/Opus, 250ms chunks),
streams it over a WebSocket, and plays back TTS audio chunks through a
sequential queue to avoid overlap. See `frontend/index.html`.

### 2. WebSocket + Deepgram STT/TTS
`backend/app.py`'s `/ws` endpoint proxies browser audio to Deepgram's
streaming transcription API, and calls Deepgram's TTS API
(`voice_pipeline/tts.py`) to synthesize each completed sentence of the
agent's reply as it streams out.

### 3. Main agent
`conversation_agents/main_agent.py` loads DB-persisted conversation
history, classifies the message's intent(s) — using a deterministic
"sticky routing" shortcut for short confirmations ("yes", "yeah") that
routes back to whichever agent handled the previous turn, falling back to
LLM classification otherwise — and dispatches to the matching specialized
agent(s), supporting compound requests in a single message.

### 4. Specialized agents
Five agents (`booking_agent.py`, `search_agent.py`, `reschedule_agent.py`,
`cancel_agent.py`, plus the main router) each get a scoped subset of MCP
tools and a focused system prompt. All route through
`conversation_agents/base_agent.py`'s shared tool-calling loop, which
enforces two code-level safety nets on top of prompting:
- **Confirmation gate**: book/cancel/reschedule tool calls are blocked
  unless the patient's last message contains an affirmative.
- **ID provenance check**: any doctor_id/patient_id/appointment_id used in
  a sensitive tool call must have been returned by a real lookup earlier in
  the same conversation — blocks invented or stale IDs.

### 5. MCP appointment server
`appointment_mcp_server/appointment_mcp_server_main.py` exposes 12 tools
over the real MCP protocol (stdio transport), each backed by an async
SQLAlchemy tool function under `appointment_mcp_server/tools/`.

### 6. RAG knowledge base
`rag_knowledge_base/` embeds markdown policy documents (clinic policies,
services, FAQs) with OpenAI embeddings, retrieves by cosine similarity, and
exposes results through the `search_policy_knowledge` MCP tool — used by
the search agent to ground policy answers instead of guessing.

### 7. PostgreSQL
Schema in `appointment_mcp_server/database/appointment_db_schema.sql`.
Double-booking is prevented at the database level with a GiST exclusion
constraint on `(doctor_id, tstzrange(appointment_time, end_time))` for
booked appointments — not just application logic.