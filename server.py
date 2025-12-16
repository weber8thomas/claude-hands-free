#!/usr/bin/env python3
"""
Simple HTTP server for voice interactions with Claude Code CLI
Receives audio → processes with Whisper/Claude/Piper → returns audio
Maintains conversation sessions for continuity
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import time
import subprocess
from pathlib import Path
import tempfile
import uuid
from datetime import datetime
import wave
import json
from typing import Optional, Dict
import os
import secrets
import aiofiles

# Wyoming protocol
from wyoming.client import AsyncClient
from wyoming.audio import wav_to_chunks, AudioStart, AudioStop
from wyoming.asr import Transcribe
from wyoming.tts import Synthesize

app = FastAPI(title="Claude Voice Server")

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Request logging middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_host = request.client.host if request.client else "unknown"

        print(f"→ {request.method} {request.url.path} from {client_host}")

        try:
            response = await call_next(request)
            duration = time.time() - start_time
            print(f"← {request.method} {request.url.path} → {response.status_code} ({duration:.2f}s)")
            return response
        except Exception as e:
            duration = time.time() - start_time
            print(f"← {request.method} {request.url.path} → ERROR: {e} ({duration:.2f}s)")
            raise


app.add_middleware(RequestLoggingMiddleware)

# Configuration
WHISPER_HOST = os.getenv("WHISPER_HOST", "192.168.0.122")  # Use host IP from container
WHISPER_PORT = int(os.getenv("WHISPER_PORT", "10300"))
PIPER_HOST = os.getenv("PIPER_HOST", "192.168.0.122")  # Use host IP from container
PIPER_PORT = int(os.getenv("PIPER_PORT", "10200"))
TEMP_DIR = Path("/tmp/claude-voice")
TEMP_DIR.mkdir(exist_ok=True)

# Conversation sessions storage
SESSIONS_DIR = TEMP_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# Active Claude CLI processes (for interactive mode)
active_processes: Dict[str, subprocess.Popen] = {}

# Whisper transcription lock (only one at a time to avoid protocol conflicts)
whisper_lock = asyncio.Lock()

# Voice request queue (in-memory for MCP integration)
voice_requests = {}  # {request_id: {"status": "pending", "transcript": None, "language": "fr"}}
voice_requests_lock = asyncio.Lock()


async def transcribe_audio(audio_path: Path, language: str = "fr") -> str:
    """Convert audio to text using Whisper"""
    # Read and validate WAV file first
    print(f"Opening WAV file: {audio_path}, exists: {audio_path.exists()}")

    # Use lock to ensure only one transcription at a time (with timeout)
    try:
        async with asyncio.timeout(120):  # 2 minute timeout for getting lock + transcription
            async with whisper_lock:
                print(f"Acquired Whisper lock, connecting...")
                client = AsyncClient.from_uri(f"tcp://{WHISPER_HOST}:{WHISPER_PORT}")

                async with client:
                    # Send transcription request
                    await client.write_event(Transcribe(language=language).event())

                    # Open WAV and send chunks with start/stop events
                    with wave.open(str(audio_path), "rb") as wav_file:
                        rate = wav_file.getframerate()
                        width = wav_file.getsampwidth()
                        channels = wav_file.getnchannels()
                        print(f"WAV params: rate={rate}, width={width}, channels={channels}")

                        # Use wav_to_chunks with start_event and stop_event flags
                        chunk_count = 0
                        for audio_event in wav_to_chunks(wav_file, samples_per_chunk=1024, start_event=True, stop_event=True):
                            await client.write_event(audio_event.event())
                            chunk_count += 1

                        print(f"Sent {chunk_count} audio events (including start/stop)")

                    # Read transcript with timeout
                    transcript = ""
                    print(f"Waiting for transcript from Whisper...")
                    event_count = 0

                    try:
                        # Add timeout to prevent hanging forever
                        async with asyncio.timeout(30):
                            while True:
                                event = await client.read_event()
                                event_count += 1
                                if event is None:
                                    print(f"Got None event after {event_count} events")
                                    break
                                print(f"Event {event_count}: type={event.type}, data keys={list(event.data.keys()) if hasattr(event.data, 'keys') else 'not a dict'}")

                                # Check for transcript event
                                if event.type == "transcript":
                                    transcript = event.data.get("text", "")
                                    print(f"Got transcript: '{transcript}'")
                                    break

                                # Limit events to prevent infinite loop
                                if event_count > 100:
                                    print(f"Too many events ({event_count}), stopping")
                                    break
                    except asyncio.TimeoutError:
                        print(f"Timeout after {event_count} events waiting for transcript")
                    except Exception as e:
                        print(f"Error reading events: {e}")

                    if not transcript:
                        print(f"No transcript received after {event_count} events")

                    return transcript.strip()
    except asyncio.TimeoutError:
        print(f"Overall timeout waiting for lock or transcription")
        return ""
    except Exception as e:
        print(f"Error in transcribe_audio: {e}")
        return ""


async def synthesize_speech(text: str, output_path: Path):
    """Convert text to speech using Piper"""
    client = AsyncClient.from_uri(f"tcp://{PIPER_HOST}:{PIPER_PORT}")

    async with client:
        await client.write_event(Synthesize(text=text).event())

        audio_chunks = []
        while True:
            event = await client.read_event()
            if event is None:
                break
            if event.type == "audio-chunk":
                audio_chunks.append(event.data.get("audio", b""))
            elif event.type == "audio-stop":
                break

        if audio_chunks:
            audio_data = b"".join(audio_chunks)
            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                wav_file.writeframes(audio_data)


class ClaudeSession:
    """Maintains a persistent Claude Code CLI session"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: Optional[subprocess.Popen] = None
        self.history_file = SESSIONS_DIR / f"{session_id}.json"
        self.conversation_history = []
        self._load_history()

    def _load_history(self):
        """Load conversation history from disk"""
        if self.history_file.exists():
            with open(self.history_file) as f:
                self.conversation_history = json.load(f)

    def _save_history(self):
        """Save conversation history to disk"""
        with open(self.history_file, "w") as f:
            json.dump(self.conversation_history, f, indent=2)

    def start_interactive(self):
        """Start an interactive Claude CLI process"""
        if self.process is None or self.process.poll() is not None:
            self.process = subprocess.Popen(
                ["claude", "chat"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

    def send_message(self, prompt: str) -> str:
        """Send a message to Claude and get response"""
        self.start_interactive()

        try:
            # Send prompt
            self.process.stdin.write(prompt + "\n")
            self.process.stdin.flush()

            # Read response (until we get a prompt back)
            response_lines = []
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                # Check for next prompt indicator
                if line.strip().startswith(">"):
                    break
                response_lines.append(line)

            response = "".join(response_lines).strip()

            # Save to history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": response})
            self._save_history()

            return response

        except Exception as e:
            # Fallback to one-shot mode
            return self._fallback_message(prompt)

    def _fallback_message(self, prompt: str) -> str:
        """Fallback: run Claude with conversation context"""
        # Build context from history
        context = "\n\n".join(
            [
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in self.conversation_history[-6:]  # Last 3 exchanges
            ]
        )

        full_prompt = f"{context}\n\nUser: {prompt}" if context else prompt

        try:
            result = subprocess.run(
                ["claude", "chat", "-m", full_prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            response = result.stdout.strip() or result.stderr.strip()

            # Save to history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": response})
            self._save_history()

            return response
        except Exception as e:
            return f"Error: {str(e)}"

    def close(self):
        """Close the Claude process"""
        if self.process and self.process.poll() is None:
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=5)


# Session management
sessions: Dict[str, ClaudeSession] = {}


def get_session(session_id: Optional[str] = None) -> tuple[str, ClaudeSession]:
    """Get or create a Claude session"""
    if session_id and session_id in sessions:
        return session_id, sessions[session_id]

    # Create new session
    new_id = session_id or str(uuid.uuid4())[:8]
    sessions[new_id] = ClaudeSession(new_id)
    return new_id, sessions[new_id]


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web interface"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        content = index_file.read_text()
        return Response(
            content=content,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return "<h1>Claude Voice Server</h1><p>Web interface not found. Please check static/index.html</p>"


@app.post("/voice")
async def voice_interaction(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None)
):
    """
    Main endpoint: receive audio, process with Claude, return audio response
    Maintains conversation continuity via session_id
    """
    # Get or create session
    sid, claude_session = get_session(session_id)
    request_id = str(uuid.uuid4())[:8]
    print(f"[{sid}/{request_id}] Voice request (session: {'existing' if session_id else 'new'})")

    # Save uploaded audio
    input_path = TEMP_DIR / f"{request_id}_input.wav"
    with open(input_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    try:
        # 1. Transcribe audio to text
        print(f"[{sid}/{request_id}] Transcribing...")
        text = await transcribe_audio(input_path)

        if not text:
            raise HTTPException(status_code=400, detail="No speech detected")

        print(f"[{sid}/{request_id}] Transcript: {text}")

        # 2. Send to Claude (maintains conversation context)
        print(f"[{sid}/{request_id}] Asking Claude...")
        response = claude_session.send_message(text)
        print(f"[{sid}/{request_id}] Response: {response[:100]}...")

        # 3. Synthesize speech
        print(f"[{sid}/{request_id}] Synthesizing speech...")
        output_path = TEMP_DIR / f"{request_id}_output.wav"
        await synthesize_speech(response, output_path)

        print(f"[{sid}/{request_id}] ✅ Complete")

        # Return audio file with session ID in header
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="response.wav",
            headers={"X-Session-ID": sid},
            background=None,
        )

    except Exception as e:
        print(f"[{sid}/{request_id}] ❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up input file
        if input_path.exists():
            input_path.unlink()


@app.post("/session/new")
async def new_session():
    """Create a new conversation session"""
    sid, _ = get_session()
    return {"session_id": sid}


@app.post("/session/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear conversation history for a session"""
    if session_id in sessions:
        sessions[session_id].conversation_history = []
        sessions[session_id]._save_history()
        return {"status": "cleared"}
    raise HTTPException(status_code=404, detail="Session not found")


# === MCP Voice Input API Endpoints ===

@app.post("/api/request-voice")
async def request_voice_input(request: Request):
    """Create a new voice input request for MCP integration."""
    data = await request.json()
    language = data.get("language", "fr")

    request_id = secrets.token_hex(8)

    async with voice_requests_lock:
        voice_requests[request_id] = {
            "status": "pending",
            "transcript": None,
            "language": language,
            "created_at": asyncio.get_event_loop().time()
        }

    print(f"[Voice] Created request {request_id} for language={language}")
    return {"request_id": request_id, "status": "pending"}


@app.get("/api/pending-requests")
async def get_pending_requests():
    """Get list of pending voice requests."""
    async with voice_requests_lock:
        pending = [
            {"id": rid, "language": req["language"]}
            for rid, req in voice_requests.items()
            if req["status"] == "pending"
        ]
    return {"requests": pending}


@app.post("/api/claim-request/{request_id}")
async def claim_request(request_id: str):
    """Claim a pending request (marks it as 'recording' so it won't appear in pending list)."""
    async with voice_requests_lock:
        if request_id not in voice_requests:
            raise HTTPException(status_code=404, detail="Request not found")

        if voice_requests[request_id]["status"] != "pending":
            raise HTTPException(status_code=400, detail="Request already claimed")

        voice_requests[request_id]["status"] = "recording"

    print(f"[Voice/{request_id}] Request claimed by browser")
    return {"status": "recording"}


@app.post("/api/submit-voice/{request_id}")
async def submit_voice_input(request_id: str, audio: UploadFile = File(...)):
    """Receive and transcribe voice input from browser."""
    async with voice_requests_lock:
        if request_id not in voice_requests:
            raise HTTPException(status_code=404, detail="Request not found")

        # Accept both "pending" and "recording" status
        if voice_requests[request_id]["status"] not in ["pending", "recording"]:
            raise HTTPException(status_code=400, detail=f"Invalid request status: {voice_requests[request_id]['status']}")

        voice_requests[request_id]["status"] = "processing"
        language = voice_requests[request_id]["language"]

    print(f"[Voice/{request_id}] Received audio: {audio.filename}")

    # Save audio temporarily
    audio_path = TEMP_DIR / f"voice_{request_id}.wav"
    async with aiofiles.open(audio_path, "wb") as f:
        await f.write(await audio.read())

    try:
        # Transcribe
        transcript = await transcribe_audio(audio_path, language=language)

        # Store result
        async with voice_requests_lock:
            voice_requests[request_id]["transcript"] = transcript
            voice_requests[request_id]["status"] = "completed"

        print(f"[Voice/{request_id}] Transcript: {transcript}")
        return {"transcript": transcript, "status": "completed"}

    except Exception as e:
        async with voice_requests_lock:
            voice_requests[request_id]["status"] = "error"
            voice_requests[request_id]["error"] = str(e)
        raise
    finally:
        audio_path.unlink(missing_ok=True)


@app.get("/api/result/{request_id}")
async def get_voice_result(request_id: str):
    """Get result of voice request (polling endpoint for MCP)."""
    async with voice_requests_lock:
        if request_id not in voice_requests:
            raise HTTPException(status_code=404, detail="Request not found")

        req = voice_requests[request_id]
        return {
            "status": req["status"],
            "transcript": req.get("transcript"),
            "error": req.get("error")
        }


# === Original Voice-Text Endpoint ===

@app.post("/voice-text")
async def voice_text_interaction(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None)
):
    """
    Voice input, text output (no TTS)
    Faster for reading responses
    """
    # Get or create session
    sid, claude_session = get_session(session_id)
    request_id = str(uuid.uuid4())[:8]
    print(f"[{sid}/{request_id}] Voice-text request")

    # Save uploaded audio
    input_path = TEMP_DIR / f"{request_id}_input.wav"
    content = await audio.read()
    print(f"[{sid}/{request_id}] Received {len(content)} bytes")

    with open(input_path, "wb") as f:
        f.write(content)

    print(f"[{sid}/{request_id}] Saved to {input_path}, size: {input_path.stat().st_size}")

    try:
        # 1. Transcribe audio to text
        print(f"[{sid}/{request_id}] Transcribing...")
        text = await transcribe_audio(input_path)

        if not text:
            raise HTTPException(status_code=400, detail="No speech detected")

        print(f"[{sid}/{request_id}] Transcript: {text}")

        # 2. Send to Claude (DISABLED FOR TESTING)
        # print(f"[{sid}/{request_id}] Asking Claude...")
        # response = claude_session.send_message(text)
        # print(f"[{sid}/{request_id}] Response: {response[:100]}...")

        # FOR TESTING: Just echo back the transcript
        response = f"✅ Transcription successful! You said: {text}"
        print(f"[{sid}/{request_id}] ✅ Complete (Whisper only)")

        # Return JSON with text
        return {
            "session_id": sid,
            "transcript": text,
            "response": response
        }

    except Exception as e:
        print(f"[{sid}/{request_id}] ❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Keep input files for debugging (comment out to clean up)
        # if input_path.exists():
        #     input_path.unlink()
        pass


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "whisper": f"{WHISPER_HOST}:{WHISPER_PORT}",
        "piper": f"{PIPER_HOST}:{PIPER_PORT}",
    }


@app.get("/fresh", response_class=HTMLResponse)
async def fresh():
    """Serve fresh HTML with no cache - guaranteed new version"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        content = index_file.read_text()
        return Response(
            content=content,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "Clear-Site-Data": '"cache"'
            }
        )
    return "<h1>Error: index.html not found</h1>"


@app.post("/test-transcribe")
async def test_transcribe_only(audio: UploadFile = File(...)):
    """Test endpoint - transcribe only, no Claude"""
    request_id = str(uuid.uuid4())[:8]
    print(f"[TEST/{request_id}] Test transcribe request")

    # Save audio
    input_path = TEMP_DIR / f"{request_id}_test.wav"
    content = await audio.read()
    print(f"[TEST/{request_id}] Received {len(content)} bytes")

    with open(input_path, "wb") as f:
        f.write(content)

    try:
        # Transcribe only
        print(f"[TEST/{request_id}] Transcribing...")
        text = await transcribe_audio(input_path)
        print(f"[TEST/{request_id}] Got: '{text}'")

        return {"transcript": text, "status": "ok"}
    except Exception as e:
        print(f"[TEST/{request_id}] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8765,
        timeout_keep_alive=300,  # 5 minutes keepalive
        timeout_graceful_shutdown=30,
        limit_concurrency=10,
        limit_max_requests=1000,
        log_level="info"
    )
