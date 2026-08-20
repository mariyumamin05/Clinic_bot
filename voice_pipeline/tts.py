# voice_pipeline/tts.py

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import os
from deepgram import AsyncDeepgramClient

client = AsyncDeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])


async def synthesize_speech(text: str, voice: str = "aura-2-thalia-en") -> bytes | None:
    """Convert text to spoken audio (mp3 bytes) using Deepgram's Aura-2 TTS model.
    Returns None on failure — callers (backend/app.py) already check
    `if audio_bytes and ...` before sending, so a None here is safely skipped
    rather than crashing the WebSocket turn.
    """
    if not text or not text.strip():
        return None
    try:
        audio_chunks = bytearray()
        stream = client.speak.v1.audio.generate(
            text=text,
            model=voice,
            encoding="mp3",
        )
        async for chunk in stream:
            if isinstance(chunk, (bytes, bytearray)):
                audio_chunks.extend(chunk)
            elif hasattr(chunk, "data"):
                audio_chunks.extend(chunk.data)
            else:
                # Unknown chunk shape — print it once so we can see exactly
                # what the SDK is actually handing us, then fix precisely.
                print(f"Unexpected TTS chunk type: {type(chunk)} -> {chunk!r}")
        return bytes(audio_chunks) if audio_chunks else None
    except Exception as e:
        print(f"synthesize_speech error: {type(e).__name__}: {e}")
        return None

if __name__ == "__main__":
    import asyncio

    async def test():
        print("-- Synthesizing test phrase --")
        audio = await synthesize_speech("Hello, this is a test of the text to speech system.")
        if audio:
            out_path = Path("tts_test_output.mp3")
            out_path.write_bytes(audio)
            print(f"Success — wrote {len(audio)} bytes to {out_path.resolve()}")
            print("Play that file to confirm it actually sounds right.")
        else:
            print("FAILED — synthesize_speech returned None, check the error printed above.")

    asyncio.run(test())