# evaluation_suite/run_evaluation.py

import sys
import time
import uuid
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp_client import MCPClientManager
from conversation_agents.main_agent import handle_user_message, get_last_resolved_intents
from conversation_agents.base_agent import SENSITIVE_TOOLS, _claims_success_language
from evaluation_suite.mcp_recorder import RecordingMCPManager
from evaluation_suite.scenarios import SCENARIOS

TIME_WINDOWS = {
    "morning": (6, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
}


def _check_time_window(turn_calls: list[dict], window: str) -> bool | None:
    lo, hi = TIME_WINDOWS.get(window, (0, 24))
    iso = None
    for call in turn_calls:
        result = call["result"]
        if isinstance(result, dict) and "appointment_time" in result:
            iso = result["appointment_time"]
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and "datetime_iso" in item:
                    iso = item["datetime_iso"]
                    break
        if iso:
            hour = int(iso.split("T")[1][:2])
            return lo <= hour < hi
    return None


def _check_booking_accuracy(turn_calls: list[dict], expected_specialty: str | None) -> bool | None:
    """Verifies a successful booking/reschedule used the doctor_id that was
    actually returned by a search_doctors/get_doctor call THIS turn with the
    matching specialty — catches the 'booked with the wrong doctor' regression
    class found earlier (e.g. dermatology search, cardiology booking)."""
    if not expected_specialty:
        return None

    matched_doctor_ids = set()
    for call in turn_calls:
        if call["name"] in ("search_doctors", "get_doctor"):
            result = call["result"]
            items = result if isinstance(result, list) else [result]
            for item in items:
                if isinstance(item, dict) and item.get("specialty") == expected_specialty:
                    if "doctor_id" in item:
                        matched_doctor_ids.add(item["doctor_id"])

    for call in turn_calls:
        if call["name"] in ("book_appointment", "reschedule_appointment") and call["result"].get("success"):
            booked_doctor_id = call["result"].get("doctor_id")
            if booked_doctor_id is None:
                continue
            if not matched_doctor_ids:
                return None  # can't verify — no matching specialty lookup seen this turn
            return booked_doctor_id in matched_doctor_ids
    return None


async def run_scenario(scenario: dict, mcp_manager: RecordingMCPManager) -> dict:
    session_id = str(uuid.uuid4())
    turn_results = []
    scenario_error = None

    for turn in scenario["turns"]:
        start_index = len(mcp_manager.calls)

        first_chunk_time = {"t": None}

        async def on_chunk(delta: str):
            if first_chunk_time["t"] is None:
                first_chunk_time["t"] = time.perf_counter()

        t0 = time.perf_counter()
        try:
            reply = await handle_user_message(session_id, turn["user"], mcp_manager, on_chunk=on_chunk)
        except Exception as e:
            scenario_error = f"{type(e).__name__}: {e}"
            turn_results.append({
                "user": turn["user"], "reply": None, "total_latency_s": None,
                "first_response_latency_s": None, "crashed": True, "checks": {},
            })
            continue
        t1 = time.perf_counter()
        total_latency = t1 - t0
        first_response_latency = (first_chunk_time["t"] - t0) if first_chunk_time["t"] is not None else total_latency

        turn_calls = mcp_manager.calls_since(start_index)
        called_names = {c["name"] for c in turn_calls}
        actual_intents = get_last_resolved_intents()

        checks = {}

        expect_any = turn.get("expect_tools_any")
        if expect_any is not None:
            checks["tool_selection"] = True if len(expect_any) == 0 else bool(called_names & set(expect_any))

        expect_intent = turn.get("expect_intent")
        if expect_intent is not None:
            checks["intent_detection"] = any(i in expect_intent for i in actual_intents)

        expect_sensitive = turn.get("expect_sensitive_success")
        if expect_sensitive is not None:
            sensitive_calls = [c for c in turn_calls if c["name"] in SENSITIVE_TOOLS]
            any_success = any(c["result"].get("success") is True for c in sensitive_calls)
            checks["confirmation_compliance"] = (any_success == expect_sensitive)

        sensitive_calls = [c for c in turn_calls if c["name"] in SENSITIVE_TOOLS]
        any_sensitive_success = any(c["result"].get("success") is True for c in sensitive_calls)
        claims_success = _claims_success_language(reply or "")
        checks["no_hallucination"] = not (claims_success and not any_sensitive_success)

        window = turn.get("expect_time_window")
        if window:
            result = _check_time_window(turn_calls, window)
            if result is not None:
                checks["slot_selection_accuracy"] = result

        expected_specialty = turn.get("expected_specialty")
        if expected_specialty:
            result = _check_booking_accuracy(turn_calls, expected_specialty)
            if result is not None:
                checks["booking_accuracy"] = result

        turn_results.append({
            "user": turn["user"], "reply": reply,
            "total_latency_s": total_latency,
            "first_response_latency_s": first_response_latency,
            "crashed": False, "checks": checks,
            "tools_called": [c["name"] for c in turn_calls],
            "intents": actual_intents,
        })

    all_checks_passed = all(
        v for t in turn_results for v in t["checks"].values()
    ) and scenario_error is None

    # Conversation completion: every sensitive action this scenario expected
    # to succeed actually did, by the end, with no crash — a looser but real
    # check that the conversation reached its intended outcome, not just that
    # individual turns didn't error.
    expected_successes = [t for t in scenario["turns"] if t.get("expect_sensitive_success") is True]
    completion_ok = scenario_error is None
    if expected_successes:
        completion_ok = completion_ok and all(
            tr["checks"].get("confirmation_compliance", False)
            for tr, t in zip(turn_results, scenario["turns"])
            if t.get("expect_sensitive_success") is True
        )

    return {
        "id": scenario["id"], "category": scenario["category"],
        "spec_sections": scenario.get("spec_sections", []),
        "description": scenario["description"],
        "passed": all_checks_passed,
        "conversation_completion": completion_ok,
        "error": scenario_error,
        "turns": turn_results,
    }


def build_report(results: list[dict]) -> str:
    lines = ["# Evaluation Report", ""]
    lines.append(f"Scenarios run: {len(results)}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"Scenarios passed: {passed}/{len(results)}")
    lines.append("")

    metric_totals = {}
    all_total_latencies = []
    all_first_latencies = []
    for r in results:
        for t in r["turns"]:
            if t["total_latency_s"] is not None:
                all_total_latencies.append(t["total_latency_s"])
            if t["first_response_latency_s"] is not None:
                all_first_latencies.append(t["first_response_latency_s"])
            for metric, val in t["checks"].items():
                metric_totals.setdefault(metric, [0, 0])
                metric_totals[metric][1] += 1
                if val:
                    metric_totals[metric][0] += 1

    error_recovery_pass = sum(1 for r in results if r["error"] is None)
    completion_pass = sum(1 for r in results if r["conversation_completion"])

    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append("| Metric | Pass Rate |")
    lines.append("|---|---|")
    for metric, (passed_count, total) in sorted(metric_totals.items()):
        rate = passed_count / total * 100 if total else 0
        lines.append(f"| {metric} | {passed_count}/{total} ({rate:.0f}%) |")
    lines.append(f"| error_recovery (no crash) | {error_recovery_pass}/{len(results)} "
                  f"({error_recovery_pass/len(results)*100:.0f}%) |")
    lines.append(f"| conversation_completion | {completion_pass}/{len(results)} "
                  f"({completion_pass/len(results)*100:.0f}%) |")
    if all_total_latencies:
        lines.append(f"| avg total turn latency | {sum(all_total_latencies)/len(all_total_latencies):.2f}s |")
        lines.append(f"| max total turn latency | {max(all_total_latencies):.2f}s |")
    if all_first_latencies:
        lines.append(f"| avg first-response latency | {sum(all_first_latencies)/len(all_first_latencies):.2f}s |")
        lines.append(f"| max first-response latency | {max(all_first_latencies):.2f}s |")
    lines.append("")
    lines.append("*Note: first-response latency only differs from total latency on single-intent "
                  "turns, where streaming is active. Multi-intent (compound) turns run their "
                  "sub-handlers sequentially without direct streaming, so the two figures are "
                  "equal for those turns — this is a known harness limitation, not a 0ms response.*")
    lines.append("")

    SPEC_LABELS = {
        1: "Real-Time Voice Pipeline", 2: "Appointment Management",
        3: "Intelligent Scheduling", 4: "MCP Appointment Server",
        5: "Agent Architecture (compound requests)", 6: "Conflict Handling",
        7: "Conversation Memory", 8: "Confirmation & Safety",
        9: "RAG Knowledge Base",
    }
    lines.append("## Spec Section Coverage")
    lines.append("")
    lines.append("| # | Spec Requirement | Covered By | Result |")
    lines.append("|---|---|---|---|")
    for section_num, label in SPEC_LABELS.items():
        if section_num == 1:
            lines.append(f"| 1 | {label} | *(verified separately via live browser testing)* | — |")
            continue
        if section_num == 4:
            lines.append(f"| 4 | {label} | Exercised in every scenario (all tool calls go "
                          f"through the real MCP server) | — |")
            continue
        covering = [r for r in results if section_num in r["spec_sections"]]
        if not covering:
            lines.append(f"| {section_num} | {label} | *no scenario tagged* | ⚠️ GAP |")
            continue
        ids = ", ".join(r["id"] for r in covering)
        result = "✅ PASS" if all(r["passed"] for r in covering) else "❌ FAIL"
        lines.append(f"| {section_num} | {label} | {ids} | {result} |")
    lines.append("")

    lines.append("## Per-Scenario Results")
    lines.append("")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"### [{status}] {r['id']} — {r['category']}")
        lines.append(f"{r['description']}")
        if r["error"]:
            lines.append(f"- **Crashed:** {r['error']}")
        for t in r["turns"]:
            lines.append(f"- User: \"{t['user']}\"")
            if t["crashed"]:
                lines.append("  - CRASHED")
                continue
            lines.append(f"  - Intents: {t['intents']}")
            lines.append(f"  - Tools called: {t['tools_called']}")
            lines.append(f"  - Total latency: {t['total_latency_s']:.2f}s | "
                          f"First-response: {t['first_response_latency_s']:.2f}s")
            for metric, val in t["checks"].items():
                lines.append(f"  - {metric}: {'OK' if val else 'FAILED'}")
        lines.append("")

    return "\n".join(lines)


async def main():
    real_manager = MCPClientManager()
    await real_manager.connect()
    recorder = RecordingMCPManager(real_manager)

    results = []
    for scenario in SCENARIOS:
        print(f"Running {scenario['id']} — {scenario['description']}")
        result = await run_scenario(scenario, recorder)
        results.append(result)
        print(f"  -> {'PASS' if result['passed'] else 'FAIL'}")

    await real_manager.close()

    report = build_report(results)
    report_path = Path(__file__).resolve().parent / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {report_path}")
    print(f"\n{sum(1 for r in results if r['passed'])}/{len(results)} scenarios passed")


if __name__ == "__main__":
    asyncio.run(main())