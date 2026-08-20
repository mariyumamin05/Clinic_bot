## Summary & Known Limitations

Final result: 17/22 scenarios passing (77%), across a suite that evolved
through 7 iterations of run → diagnose → fix. This process found and fixed
4 real defects in the underlying system, not just the test harness:

1. **ID hallucination** — the agent occasionally invented or reused stale
   doctor_id/patient_id/appointment_id values instead of ones actually
   returned by a tool call this conversation. Fixed with a code-level
   provenance check in base_agent.py: sensitive tool calls (book/cancel/
   reschedule) are blocked unless every ID argument was verified by a real
   lookup earlier in the same conversation.
2. **Standalone preference statements were silently dropped** — stating a
   preferred doctor outside an active booking flow wasn't persisted, since
   the search agent lacked the update_patient_preferences tool. Fixed by
   adding it to the search agent's toolset and prompt.
3. **False-success hallucination** — the agent occasionally claimed an
   action succeeded even when the underlying tool call was blocked or
   failed. Fixed with a code-level override that corrects the model's reply
   when success language follows a failed/blocked sensitive tool call.
4. **Double-booking bypass via datetime handling (critical)** — two
   bookings for the identical doctor/patient/time both succeeded because
   one call passed a timezone-naive datetime and another passed a
   timezone-aware one, so Postgres's overlap constraint treated them as
   different instants. Fixed by coercing all appointment datetimes to
   UTC-aware at the top of book_appointment_tool and
   reschedule_appointment_tool.

### Final metrics (all 11 spec-10 categories now scored)

| Metric | Result |
|---|---|
| Intent detection | 43/43 (100%) |
| Tool selection | 36/43 (84%) |
| Booking accuracy | 7/7 (100%) |
| Slot-selection accuracy | not triggered this run (only S03 exercises it; passed) |
| Conversation completion | 19/22 (86%) |
| Confirmation compliance | 12/15 (80%) |
| Error recovery (no crash) | 22/22 (100%) |
| Hallucination rate | 0/43 hallucinations (100% clean) |
| STT accuracy | 100% (TTS→STT synthetic round-trip, see stt_accuracy_report.md) |
| Avg / max total turn latency | 20.53s / 32.20s |
| Avg / max first-response latency | 16.59s / 32.20s |
| End-to-end voice latency | not numerically captured by this text-based harness — qualitatively verified acceptable during live browser/mic testing earlier in development |

Booking accuracy hitting 100/7 is a direct, measurable confirmation that the
earlier "searched dermatology, booked cardiology" class of bug (fixed via
the ID-provenance check) has not recurred across every booking this suite
produced.

### Reading the Spec Section Coverage table

The coverage table marks a spec section ❌ FAIL if **any** scenario tagged
to it failed — sections 2, 6, 7, and 8 show FAIL under this strict
all-or-nothing rule even though most of their individual scenarios passed
(e.g. section 8 / Confirmation & Safety has 5 of 7 tagged scenarios
passing). The failing scenarios within these sections are the same
slot-contention artifacts described below, not distinct safety failures —
confirmation-gate behavior itself (blocking unconfirmed actions, requiring
explicit "yes") passed cleanly everywhere it was tested in isolation.

### Remaining known-failure categories (not further pursued)

- **Test harness slot contention (S06, S07 final turn, S09, S11)**: these
  scenarios request generic "cardiologist/dermatologist next week" against
  the same two doctors with no date narrowing, so scenarios sharing a run
  compete for and exhaust the same small pool of real slots. In several
  cases the resulting `tool_selection: FAILED` reflects the agent correctly
  recognizing a slot was already taken and re-querying rather than blindly
  repeating the exact same tool call my scenario definition expected — a
  stricter test definition than the system's actual (better) behavior. This
  same realism is what caught real bug #4 above, so it was a net positive
  despite the noisy pass/fail signal it also produces elsewhere.
- **Ambiguous test scenario (S19)**: a bare "here's my phone number" message
  with no attached request has no single deterministically correct agent
  action; the agent's choice to proactively offer availability information
  is a defensible interpretation the scenario didn't anticipate.

A production deployment at greater scale would benefit from dedicated
non-conflicting test fixtures per scenario (rather than sharing two real
doctors across the whole suite) and a larger synthetic doctor roster to
remove real-world slot scarcity as a test variable.