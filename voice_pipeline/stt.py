# voice_pipeline/stt.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import os
from deepgram import AsyncDeepgramClient

client = AsyncDeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])


async def transcribe_audio(audio_bytes: bytes) -> str | None:
    """Transcribe a complete audio clip to text using Deepgram's Nova-3 model.
    Used by the evaluation suite (batch STT accuracy testing), NOT the live
    voice pipeline — the live pipeline streams directly to Deepgram from
    backend/app.py instead.

    Returns the transcript, or None if transcription failed.
    """
    try:
        response = await client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-3",
        )
        return response.results.channels[0].alternatives[0].transcript
    except TypeError as e:
        print(f"transcribe_audio TypeError (likely wrong await pattern, same as TTS): {e}")
        return None
    except Exception as e:
        print(f"transcribe_audio error: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    import asyncio

    async def test():
        test_file = sys.argv[1] if len(sys.argv) > 1 else None
        if not test_file or not Path(test_file).exists():
            print("Usage: python -m voice_pipeline.stt <path_to_audio_file>")
            print("(no file given/found — skipping live API test)")
            return

        audio_bytes = Path(test_file).read_bytes()
        print(f"-- Transcribing {test_file} ({len(audio_bytes)} bytes) --")
        result = await transcribe_audio(audio_bytes)
        print("Transcript:", result)

    asyncio.run(test())