# Quick Start Guide - Claude Voice

Get voice interaction with Claude Code running in 5 minutes!

## TL;DR

```bash
# Server (Proxmox LXC)
cd /workspace/proxmox-services/claude-voice
./start-server.sh

# MacBook
brew install sox
./client-macos.sh http://server-ip:8765
```

## Step-by-Step

### 1. Start Whisper (Server)

```bash
cd /workspace/proxmox-services/whisper
cp .env.example .env
docker-compose up -d

# Verify
docker logs whisper
curl http://localhost:10300/
```

### 2. Verify Piper is Running (Server)

```bash
cd /workspace/proxmox-services/piper
docker-compose ps

# Should show piper running
# If not: docker-compose up -d
```

### 3. Start Voice Server (Server)

```bash
cd /workspace/proxmox-services/claude-voice
./start-server.sh
```

You should see:
```
✅ Starting server on http://0.0.0.0:8765
INFO: Started server process
```

### 4. Install Client (MacBook)

```bash
# Install sox for recording
brew install sox

# Download client script (if not already on your Mac)
# Either copy via scp or create locally
```

### 5. Connect and Talk!

```bash
# On MacBook
./client-macos.sh http://your-server-ip:8765
```

**Usage:**
1. Press **Enter** to start recording
2. Speak your question
3. Press **Ctrl+C** to stop and send
4. Listen to Claude's response
5. Repeat - conversation continues!

## First Conversation

```
You: "Hi Claude, can you list the files in the current directory?"

🎤 Recording...
✅ Recording saved
📤 Sending to Claude...
✅ Response received
🔊 Playing response...

Claude: "I see several files including server.py, client-macos.sh,
        and requirements.txt. Would you like me to explain what
        each file does?"

You: "Yes, tell me about server.py"

[Continues conversation with context...]
```

## Testing Without Client

Test the API directly:

```bash
# Record a test message
sox -d -r 16000 -c 1 test.wav trim 0 5

# Send to server
curl -X POST \
  -F "audio=@test.wav" \
  http://localhost:8765/voice \
  -o response.wav

# Play response
afplay response.wav
```

## Troubleshooting

### Server won't start

```bash
# Check ports are free
lsof -i :8765
lsof -i :10300
lsof -i :10200

# Check services
docker ps | grep -E "whisper|piper"
```

### Client can't connect

```bash
# Test server health
curl http://server-ip:8765/health

# Check firewall
# On server: sudo ufw allow 8765/tcp
```

### No audio playback (Mac)

```bash
# Check afplay works
afplay /System/Library/Sounds/Ping.aiff

# Check downloaded audio file
file response.wav
# Should show: WAVE audio, 22050 Hz, mono
```

### Recording doesn't work (Mac)

```bash
# Test sox
sox -d test.wav trim 0 3

# If fails, grant microphone permission:
# System Settings → Privacy & Security → Microphone → Terminal
```

## What's Next?

- **Type `new`** to start a fresh conversation
- **Type `quit`** to exit
- **Close client** - your session persists! Restart to continue

## Architecture Reminder

```
Your MacBook:
  [Microphone] → sox → WAV file
       ↓ HTTP POST
  Your Server:
    Whisper → "text"
       ↓
    Claude Code CLI → response text
       ↓
    Piper → WAV audio
       ↓ HTTP Response
Your MacBook:
  [Speakers] ← afplay ← WAV file
```

Session state maintained server-side in `/tmp/claude-voice/sessions/`

Enjoy talking to Claude! 🎤
