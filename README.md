# AI Voice Appointment & Scheduling Agent

A production-style voice AI agent for a medical clinic. Patients speak
naturally to find doctors, check availability, and book, reschedule, or
cancel appointments — handled by a multi-agent system backed by a real
PostgreSQL appointment database, an MCP tool server, and a RAG-grounded
knowledge base for policy questions.

## Features

- Real-time voice interface: browser mic → WebSocket → Deepgram STT →
  streaming LLM agent → Deepgram TTS → browser speaker
- 5 specialized agents (main router, search, booking, rescheduling,
  cancellation) coordinated through a shared tool-calling loop
- MCP appointment server exposing 12 tools over the real MCP protocol
  (doctors, patients, appointments, specialties, preferences, policy search)
- PostgreSQL schema with a database-level exclusion constraint preventing
  double-booking, plus application-level conflict handling (inactive
  doctors, clinic closures, outside-hours requests, invalid references)
- Explicit confirmation gating before any booking, cancellation, or
  reschedule — enforced in code, not just prompted
- Cross-session conversation memory (preferred doctor, preferred time)
- RAG knowledge base (cancellation policy, insurance, clinic hours, FAQs)
  grounding policy answers instead of letting the model guess
- Automated evaluation suite: 22 scenarios scoring intent detection, tool
  selection, booking accuracy, confirmation compliance, hallucination rate,
  latency, and STT accuracy

## Architecture

See `docs/architecture.md` for the full diagram and layer-by-layer
explanation. In short:
Browser (mic/speaker)
→ WebSocket → Deepgram STT
→ Main agent (intent routing)
→ Specialized agent (search / booking / reschedule / cancel)
→ MCP appointment server (tools) ←→ RAG knowledge base
→ PostgreSQL
→ Deepgram TTS → WebSocket → Browser (speaker)


## Tech stack

- **Backend**: FastAPI, WebSockets, SQLAlchemy (async), PostgreSQL
- **Agents**: OpenAI (gpt-4o-mini), custom multi-agent orchestration
- **Voice**: Deepgram (streaming STT, Aura TTS)
- **Tools**: MCP (Model Context Protocol) over stdio
- **RAG**: OpenAI embeddings, cosine-similarity retrieval over markdown docs
- **Frontend**: React (CDN, no build step), single-file `index.html`

## Project structure

appointment_mcp_server/ MCP server + tools + database layer
backend/ FastAPI app, WebSocket handler, MCP client
conversation_agents/ Main agent + 4 specialized agents
rag_knowledge_base/ Policy documents, embedding index, retriever
voice_pipeline/ STT/TTS wrappers (Deepgram)
frontend/ Single-page React voice interface
evaluation_suite/ Automated scenario runner + reports
docs/ Architecture and API documentation


## Setup

1. **Clone and create a virtual environment**
```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   cd YOUR_REPO_NAME
   python -m venv venv
   venv\Scripts\activate        # Windows
   pip install -r requirements.txt
```

2. **Environment variables** — create a `.env` file in the project root:

DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname
OPENAI_API_KEY=your_openai_key
DEEPGRAM_API_KEY=your_deepgram_key


3. **Set up the database**
```bash
   psql -f appointment_mcp_server/database/appointment_db_schema.sql
```
   Then seed at least one doctor, specialty, and availability row (see
   `docs/api.md` for the schema).

4. **Build the RAG index**
```bash
   python -m rag_knowledge_base.build_index
```

5. **Run the server**
```bash
   python -m uvicorn backend.app:app --reload
```
   Open `http://localhost:8000/`.

## Running the evaluation suite

```bash
python -m evaluation_suite.cleanup
python -m evaluation_suite.run_evaluation
python -m evaluation_suite.stt_accuracy
```

Results are written to `evaluation_suite/report.md` and
`evaluation_suite/stt_accuracy_report.md`.

## Running the test suite

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system diagram and
  layer-by-layer explanation
- [`docs/api.md`](docs/api.md) — REST/WebSocket endpoints and MCP tool
  reference

## Known limitations

- The evaluation suite's remaining failures are documented in
  `evaluation_suite/report.md` under "Known Limitations" — primarily test
  fixture slot contention between scenarios sharing the same two seeded
  doctors, not product defects.
- The frontend is a single-file React app loaded via CDN (no bundler) —
  functional and fully React, but not a conventional `npm`-managed project.
- Intent classification and preference-memory resolution are LLM-driven and
  therefore probabilistic, not deterministically guaranteed on every turn;
  a code-level confirmation gate and ID-provenance check backstop the
  highest-risk actions (booking, cancelling, rescheduling).
