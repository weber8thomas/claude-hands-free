# Claude Voice - Voice Interface for Claude Code CLI

Voice-enabled interface for Claude Code using Whisper STT and Piper TTS.

## Architecture

```
MacBook M1 (Client)
  ↓ Push-to-talk (sox)
  ↓ HTTP POST /voice
Proxmox LXC (Server)
  ├─ Whisper STT → text
  ├─ Claude Code CLI → response
  └─ Piper TTS → audio
  ↓ HTTP Response
MacBook M1 (Client)
  └─ afplay (audio playback)
```

## Features

✅ **Conversation Continuity** - Maintains context across interactions
✅ **Push-to-Talk** - Record with Ctrl+C to send
✅ **Session Management** - Resume conversations anytime
✅ **Fast STT** - Faster-Whisper (base model)
✅ **Natural TTS** - Piper neural voices

## Prerequisites

### Server (Proxmox LXC)
- Docker & Docker Compose
- Claude Code CLI installed
- Whisper service (port 10300)
- Piper service (port 10200)

### Client (MacBook)
- sox (audio recording)
- curl (HTTP client)
- afplay (native macOS, pre-installed)

## Installation

### 1. Server Setup

```bash
cd /workspace/proxmox-services/claude-voice

# Install Python dependencies
pip3 install -r requirements.txt

# Start the voice server
python3 server.py
```

Server runs on port 8765.

### 2. Start Whisper Service

```bash
cd /workspace/proxmox-services/whisper
cp .env.example .env
docker-compose up -d
```

### 3. Verify Piper is Running

```bash
cd /workspace/proxmox-services/piper
docker-compose ps
# Should show piper running on port 10200
```

### 4. MacBook Client Setup

```bash
# Install sox
brew install sox

# Download client script
scp user@server:/workspace/proxmox-services/claude-voice/client-macos.sh ~/claude-voice.sh
chmod +x ~/claude-voice.sh

# Run client
~/claude-voice.sh http://your-server:8765
```

## Usage

### Start Voice Chat

```bash
# On MacBook
./claude-voice.sh http://server-ip:8765
```

### Workflow

1. **Press Enter** when ready to speak
2. **Start talking** - recording begins
3. **Press Ctrl+C** to stop and send
4. **Wait** for Claude's response
5. **Listen** to audio response
6. **Repeat** - conversation context is maintained

### Commands

- Type `new` - Start fresh conversation
- Type `quit` - Exit client
- **Session persists** - Restart client to continue

### Example Conversation

```
You: "What files are in this directory?"
Claude: "I see three Python files: server.py, voice-claude.py, and requirements.txt..."

You: "What does server.py do?"
Claude: "Based on our previous context, server.py is the FastAPI server that handles..."
```

## How Conversations Work

### Session Management

1. **First request**: Server creates new session ID
2. **Response**: Returns audio + session ID in header
3. **Client saves**: Session ID stored in `~/.claude-voice-session`
4. **Next request**: Client sends audio + session ID
5. **Server maintains**: Conversation history per session

### Claude Integration

The server maintains an **interactive Claude CLI process** per session:

```python
# Keeps claude chat running
process = subprocess.Popen(["claude", "chat"], stdin=PIPE, stdout=PIPE)

# Each voice message goes to the same process
process.stdin.write(user_message + "\n")
response = process.stdout.readline()
```

This ensures true conversation continuity!

## API Endpoints

### POST /voice
Upload audio, get response audio

**Request:**
```bash
curl -X POST \
  -F "audio=@recording.wav" \
  -F "session_id=abc123" \
  http://server:8765/voice
```

**Response:**
- Body: WAV audio file
- Header: `X-Session-ID: abc123`

### POST /session/new
Create new conversation

```bash
curl -X POST http://server:8765/session/new
# Returns: {"session_id": "abc123"}
```

### POST /session/{id}/clear
Clear conversation history

```bash
curl -X POST http://server:8765/session/abc123/clear
# Returns: {"status": "cleared"}
```

### GET /health
Health check

```bash
curl http://server:8765/health
```

## Configuration

### Server (server.py)

```python
WHISPER_HOST = "localhost"
WHISPER_PORT = 10300
PIPER_HOST = "localhost"
PIPER_PORT = 10200
```

### Whisper Model

Edit `/workspace/proxmox-services/whisper/docker-compose.yml`:

```yaml
command: >
  --model base           # tiny, base, small, medium, large
  --language en
  --beam-size 5
```

### Piper Voice

Edit `/workspace/proxmox-services/piper/docker-compose.yml`:

```yaml
command: --voice en_US-lessac-medium  # Change voice
```

## Troubleshooting

### No Response from Server

```bash
# Check server is running
curl http://server:8765/health

# Check Whisper
curl http://server:10300/

# Check Piper
curl http://server:10200/
```

### Recording Issues (macOS)

```bash
# Test microphone
sox -d test.wav trim 0 3

# If fails, check microphone permissions
# System Settings → Privacy & Security → Microphone
```

### Conversation Not Continuing

```bash
# Check session file
cat ~/.claude-voice-session

# Clear and start fresh
rm ~/.claude-voice-session
```

### Claude CLI Not Found

```bash
# On server, verify Claude Code is installed
which claude
claude --version

# Should show: Claude Code CLI v1.x.x
```

## Performance

### Latency Breakdown

1. **Recording**: ~2-5 seconds (manual)
2. **Upload**: ~0.5 seconds (16kHz mono WAV)
3. **Whisper STT**: ~1-2 seconds (base model)
4. **Claude Processing**: ~2-10 seconds (depends on query)
5. **Piper TTS**: ~0.5-1 second
6. **Download + Play**: ~0.5 seconds

**Total**: ~7-20 seconds per interaction

### Optimization Tips

- Use `tiny` Whisper model for faster STT (less accurate)
- Keep messages short for faster TTS
- Use local network (not internet) for low latency

## Files

```
claude-voice/
├── server.py              # FastAPI server (main)
├── client-macos.sh        # MacBook client script
├── voice-claude.py        # Standalone Python script (alt)
├── requirements.txt       # Python dependencies
├── .env.example          # Configuration template
├── .gitignore            # Git ignore patterns
└── README.md             # This file
```

## Security Notes

- **No authentication** - Use firewall/VPN
- **Conversation history** stored in `/tmp/claude-voice/sessions/`
- **Audio files** deleted after processing
- **Session IDs** are random UUIDs (8 chars)

## Advanced Usage

### Use with Different Claude Commands

Modify `server.py` to change Claude behavior:

```python
# Research mode
subprocess.Popen(["claude", "chat", "--research"])

# Specific model
subprocess.Popen(["claude", "chat", "--model", "opus"])
```

### Custom Wake Word (Future)

Replace push-to-talk with wake word detection:
1. Add `wyoming-openwakeword` service
2. Stream audio continuously
3. Trigger on "Hey Claude"

### Multiple Users

Add authentication header:

```bash
curl -H "Authorization: Bearer user-token" ...
```

## Resources

- **Whisper**: https://github.com/openai/whisper
- **Piper TTS**: https://github.com/rhasspy/piper
- **Wyoming Protocol**: https://github.com/rhasspy/wyoming
- **Claude Code CLI**: https://claude.com/claude-code

## License

Personal use - part of CastleBlack homelab infrastructure.
