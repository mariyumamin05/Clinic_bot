# API Reference

## REST endpoints

### `POST /chat`
Text-only endpoint for testing agent logic without voice.

Request:
```json
{ "session_id": "uuid-string", "message": "I need a cardiologist next week" }
```

Response:
```json
{ "reply": "I found Dr. Ahmed Khan available Tuesday at 2:30 PM..." }
```

### `GET /`
Serves the frontend (`frontend/index.html`).

## WebSocket

### `WS /ws`
Real-time voice session. One connection = one call.

**Client → server**: binary audio chunks (WebM/Opus), or a JSON control
message `{"type": "end_session"}` to close cleanly.

**Server → client** (JSON):
| Field | Meaning |
|---|---|
| `status` | `listening` \| `thinking` \| `speaking` \| `error` |
| `transcript`, `is_final` | Live STT transcript |
| `llm_chunk`, `stream_id` | Streamed reply text |
| `llm_done` | Turn complete |

**Server → client** (binary): MP3 audio bytes for the current reply.

## MCP tools

All exposed by `appointment_mcp_server_main.py`, callable by any agent
scoped to include them.

| Tool | Purpose |
|---|---|
| `search_doctors(doctor_name?, specialty_name?)` | Find doctors by name/specialty |
| `get_doctor(doctor_id)` | Full doctor profile + weekly availability |
| `search_specialties(name?)` | List specialties |
| `get_availability(doctor_id, start_date, end_date, time_of_day_preference?)` | Open slots in a range |
| `create_patient(full_name, phone, email?, preferred_doctor_id?)` | Create or return existing patient (dedup by phone) |
| `get_patient(patient_id?, phone?)` | Look up a patient |
| `update_patient_preferences(patient_id, preferred_doctor_id?, preferred_time_of_day?)` | Persist a stated preference |
| `book_appointment(doctor_id, patient_id, appointment_datetime, duration_minutes?, notes?)` | Book, with conflict checking |
| `reschedule_appointment(appointment_id, new_appointment_datetime)` | Move an existing appointment |
| `cancel_appointment(appointment_id, cancellation_reason?)` | Cancel (soft delete) |
| `search_appointments(patient_id, status?, start_date?, end_date?)` | List a patient's appointments |
| `search_policy_knowledge(query, top_k?)` | RAG lookup over clinic policy docs |

### Failure reasons

Sensitive tools return `{"success": false, "reason": "...", ...}` on
failure. Reasons in use: `slot_unavailable`, `doctor_unavailable`,
`clinic_closed`, `outside_availability`, `invalid_reference`,
`not_found`, `already_cancelled`, `confirmation_required`,
`unverified_id`, `mcp_tool_error`, `tool_error`.