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
