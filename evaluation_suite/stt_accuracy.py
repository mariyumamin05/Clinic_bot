# evaluation_suite/stt_accuracy.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from voice_pipeline.tts import synthesize_speech
from voice_pipeline.stt import transcribe_audio

# Synthetic round-trip test: generate real audio via TTS, then transcribe it
# back via STT. Not a substitute for testing against genuine human speech
# (accents, background noise, disfluencies aren't exercised this way), but
# gives a real, automated, repeatable baseline number without requiring
# manual audio recording each run.
TEST_PHRASES = [
    "I need to book a cardiologist appointment next week",
    "Can you cancel my appointment for tomorrow afternoon",
    "What is your cancellation policy",
    "I would like to reschedule to Friday at three PM",
    "Is Doctor Ahmed Khan available in the morning",
]


def word_accuracy(expected: str, actual: str) -> float:
    exp_words = expected.lower().split()
    act_words = (actual or "").lower().split()
    if not exp_words:
        return 0.0
    matches = sum(1 for a, b in zip(exp_words, act_words) if a == b)
    return matches / len(exp_words)


async def run():
    total_acc = 0.0
    results = []
    for phrase in TEST_PHRASES:
        audio = await synthesize_speech(phrase)
        if not audio:
            print(f"TTS failed for: {phrase!r} — skipping")
            continue
        transcript = await transcribe_audio(audio)
        acc = word_accuracy(phrase, transcript)
        total_acc += acc
        results.append((phrase, transcript, acc))
        print(f"Expected: {phrase!r}")
        print(f"Got:      {transcript!r}")
        print(f"Word accuracy: {acc*100:.0f}%\n")

    if results:
        overall = total_acc / len(results)
        print(f"Overall STT word accuracy (TTS round-trip): {overall*100:.0f}%")

        report_path = Path(__file__).resolve().parent / "stt_accuracy_report.md"
        lines = ["# STT Accuracy Report (TTS round-trip)", "",
                 f"Overall word accuracy: {overall*100:.0f}%", ""]
        for phrase, transcript, acc in results:
            lines.append(f"- Expected: `{phrase}`")
            lines.append(f"  - Got: `{transcript}`")
            lines.append(f"  - Accuracy: {acc*100:.0f}%")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Report written to {report_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())