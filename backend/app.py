# backend/app.py

import os
import re
import json
import asyncio
import uuid
import sys
from pathlib import Path
from contextlib import asynccontextmanager

import websockets
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from backend.mcp_client import mcp_manager
from conversation_agents.main_agent import handle_user_message
from voice_pipeline.tts import synthesize_speech

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise ValueError(
        "DEEPGRAM_API_KEY not found in .env — the voice pipeline cannot start without it."
    )

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?punctuate=true&interim_results=true&endpointing=800"
    "&vad_events=true&utterance_end_ms=1500&model=nova-3&numerals=true"
)

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_manager.connect()
    yield
    await mcp_manager.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_homepage():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    """Text-only endpoint — useful for testing the agent logic without voice."""
    reply = await handle_user_message(req.session_id, req.message, mcp_manager)
    return {"reply": reply}


def clean_text_for_speech(text):
    text = re.sub(r'^#{1,6}\s?', '', text, flags=re.MULTILINE)
    text = text.replace('**', '')
    text = text.replace('*', '')
    text = re.sub(r'^-\s+', '', text, flags=re.MULTILINE)
    return text.strip()


@app.websocket("/ws")
async def websocket_endpoint(browser_ws: WebSocket):
    await browser_ws.accept()
    print("Browser connected")

    connection_active = {"value": True}
    session_id = str(uuid.uuid4())  # scopes conversation memory to this call

    # Tracks the currently-running response task so a NEW utterance can
    # actually cancel the OLD one (not just silence its audio output).
    # Without this, an abandoned response keeps calling OpenAI/MCP tools
    # and can write its assistant message to DB history out of order
    # relative to the newer exchange — corrupting future context.
    current_llm_task = {"task": None}

    async def safe_send_text(payload):
        if not connection_active["value"]:
            return
        try:
            await browser_ws.send_text(payload)
        except Exception:
            connection_active["value"] = False

    async def safe_send_bytes(payload):
        if not connection_active["value"]:
            return
        try:
            await browser_ws.send_bytes(payload)
        except Exception:
            connection_active["value"] = False

    try:
        try:
            deepgram_ws = await websockets.connect(
                DEEPGRAM_URL,
                additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
            )
        except TypeError:
            deepgram_ws = await websockets.connect(
                DEEPGRAM_URL,
                extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
            )
        print("Connected to Deepgram")
    except Exception as e:
        print(f"Failed to connect to Deepgram: {type(e).__name__}: {repr(e)}")
        await browser_ws.send_text(json.dumps({
            "status": "error",
            "error": "Could not connect to the speech service. Please check your internet connection and try again."
        }))
        await browser_ws.close()
        return

    session_transcript = {"text": ""}
    latest_interim = {"text": ""}
    current_stream_id = {"id": 0}

    def extract_and_reset_transcript():
        full_text = (session_transcript["text"] + " " + latest_interim["text"]).strip()
        session_transcript["text"] = ""
        latest_interim["text"] = ""
        return full_text

    async def stream_llm_response(user_text, my_id):
        try:
            await safe_send_text(json.dumps({"status": "thinking"}))

            sentence_buffer = {"text": ""}
            first_chunk = {"value": True}
            streamed_anything = {"value": False}

            async def on_chunk(delta: str):
                if current_stream_id["id"] != my_id:
                    return
                streamed_anything["value"] = True
                if first_chunk["value"]:
                    await safe_send_text(json.dumps({"status": "speaking"}))
                    first_chunk["value"] = False

                await safe_send_text(json.dumps({"llm_chunk": delta, "stream_id": my_id}))

                sentence_buffer["text"] += delta
                if any(sentence_buffer["text"].rstrip().endswith(p) for p in [".", "?", "!"]):
                    text_to_speak = sentence_buffer["text"].strip()
                    sentence_buffer["text"] = ""
                    if text_to_speak:
                        audio_bytes = await synthesize_speech(clean_text_for_speech(text_to_speak))
                        if audio_bytes and current_stream_id["id"] == my_id:
                            await safe_send_bytes(audio_bytes)

            full_reply = await handle_user_message(session_id, user_text, mcp_manager, on_chunk=on_chunk)

            if not streamed_anything["value"] and current_stream_id["id"] == my_id:
                await safe_send_text(json.dumps({"llm_chunk": full_reply, "stream_id": my_id}))
                audio_bytes = await synthesize_speech(clean_text_for_speech(full_reply))
                if audio_bytes and current_stream_id["id"] == my_id:
                    await safe_send_bytes(audio_bytes)
            elif sentence_buffer["text"].strip() and current_stream_id["id"] == my_id:
                audio_bytes = await synthesize_speech(clean_text_for_speech(sentence_buffer["text"].strip()))
                if audio_bytes and current_stream_id["id"] == my_id:
                    await safe_send_bytes(audio_bytes)

            if current_stream_id["id"] == my_id:
                await safe_send_text(json.dumps({"llm_done": True, "status": "listening"}))

        except asyncio.CancelledError:
            # Expected when a newer utterance interrupts this one — not an error.
            print(f"stream_llm_response (stream_id={my_id}) cancelled by a newer utterance")
            raise
        except Exception as e:
            print("stream_llm_response error:", e)

    async def browser_to_deepgram():
        try:
            while True:
                message = await browser_ws.receive()
                if message.get("bytes") is not None:
                    await deepgram_ws.send(message["bytes"])
                elif message.get("text") is not None:
                    try:
                        control = json.loads(message["text"])
                    except json.JSONDecodeError:
                        control = {}
                    if control.get("type") == "end_session":
                        print("End session requested by browser")
                        await deepgram_ws.close()
                        return
        except Exception as e:
            print("browser_to_deepgram stopped:", e)

    async def deepgram_to_browser():
        try:
            async for message in deepgram_ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    print("Non-JSON message from Deepgram:", message)
                    continue

                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type")

                if msg_type == "UtteranceEnd":
                    full_text = extract_and_reset_transcript()
                    print(f"UtteranceEnd -> sending to LLM: {full_text}")
                    if full_text:
                        current_stream_id["id"] += 1
                        my_id = current_stream_id["id"]

                        # Cancel any still-running response for the PREVIOUS
                        # utterance — it's been superseded, don't let it keep
                        # burning API calls or write history out of order.
                        old_task = current_llm_task["task"]
                        if old_task and not old_task.done():
                            old_task.cancel()

                        current_llm_task["task"] = asyncio.create_task(
                            stream_llm_response(full_text, my_id)
                        )
                    continue

                channel = data.get("channel")
                if not isinstance(channel, dict):
                    continue

                alternatives = channel.get("alternatives", [])
                if not alternatives or not isinstance(alternatives, list):
                    continue

                transcript = alternatives[0].get("transcript", "")
                is_final = data.get("is_final", False)

                if transcript:
                    print(f"Deepgram transcript: {transcript} (is_final: {is_final})")
                    await safe_send_text(json.dumps({"transcript": transcript, "is_final": is_final}))

                    if is_final:
                        session_transcript["text"] += transcript + " "
                        latest_interim["text"] = ""
                    else:
                        latest_interim["text"] = transcript

        except Exception as e:
            print("deepgram_to_browser stopped:", e)

    try:
        await asyncio.gather(browser_to_deepgram(), deepgram_to_browser())
    finally:
        final_task = current_llm_task["task"]
        if final_task and not final_task.done():
            final_task.cancel()
        try:
            await deepgram_ws.close()
        except Exception:
            pass