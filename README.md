# MCP Hands-Free - Voice Input MCP Server

> **"Why type when you can talk?"** - Every developer eating pizza while coding

## Why This Exists

Ever tried to:
- 🍕 Ask your AI assistant a question while eating lunch? (greasy keyboards are NOT fun)
- 🏃 Debug code while on the treadmill? (typing + running = broken ankles)
- 🧘 Practice your "hands-free workday" because your wrists hurt? (RSI is real, folks)
- 🛋️ Casually chat with your AI from across the room? (peak laziness achieved)
- 👶 Code with a baby in your arms? (multitasking level: parent - yes, this repo author does this, no shame)

**This MCP server lets you talk to any MCP-compatible AI instead of typing.** No more keyboard gymnastics. Just speak your mind, and your AI assistant listens.

Perfect for when your hands are busy, tired, dirty, or just... somewhere else.

---

Universal hands-free voice input for MCP-compatible AI assistants (Claude Code CLI, Gemini, Qwen, etc.) using Whisper speech-to-text.

## Architecture

```
MCP Client (Claude, Gemini, Qwen, etc.)
  ↓ calls get_voice_input() MCP tool
MCP Server (stdio)
  ↓ HTTP POST /api/request-voice
FastAPI Server (coordination)
  ↓ stores request_id
Browser Interface
  ↓ polls /api/pending-requests
  ↓ auto-starts recording
  ↓ user speaks
  ↓ POST audio to /api/submit-voice/{request_id}
FastAPI Server
  ↓ transcribes with Whisper via Wyoming protocol
MCP Server
  ↓ polls /api/result/{request_id}
  ↓ returns transcript
MCP Client
  └─ receives transcript as user input
```

## Features

- **Hands-Free Input** - Speak your requests instead of typing
- **Multi-Language Support** - French, English, Spanish, German, Italian
- **Browser-Based Recording** - No client software installation needed
- **Whisper STT** - High-quality speech recognition via Wyoming protocol
- **Universal MCP Integration** - Works with any MCP-compatible AI client
- **Auto-Recording** - Browser automatically starts recording when your AI requests voice input

## Prerequisites

- **FastAPI Server** - Coordination server with Whisper integration
- **Whisper Service** - Wyoming-compatible Whisper STT service (port 10300)
- **Browser** - Any modern browser with microphone access
- **MCP Client** - Any MCP-compatible AI assistant (Claude Code CLI, Gemini with MCP, etc.)

## Installation

### 1. Install MCP Server

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "voice-input": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "/path/to/mcp-hands-free/mcp-server",
        "claude-voice-mcp"
      ],
      "env": {
        "VOICE_SERVER_URL": "https://your-server:8766"
      }
    }
  }
}
```

### 2. Start FastAPI Server

```bash
cd /path/to/mcp-hands-free

# Install Python dependencies
pip3 install -r requirements.txt

# Start the server (with SSL for browser microphone access)
python3 server.py
```

Server runs on port 8766 (HTTPS).

### 3. Start Whisper Service

```bash
# Using Wyoming-compatible Whisper service
docker run -d \
  -p 10300:10300 \
  rhasspy/wyoming-faster-whisper \
  --model base \
  --language fr
```

### 4. Open Browser Interface

Navigate to:
```
https://your-server:8766/static/voice-input.html
```

Accept SSL certificate warning (self-signed) and grant microphone permissions.

## Usage

### Basic Voice Input

In your MCP client (Claude Code CLI, etc.):
```
You: "Get my next request via voice"
```

Your AI calls `get_voice_input()` tool, browser auto-starts recording, you speak, transcript is returned.

### With Language Parameter

```
You: "Get my next request via voice in English"
```

### Example Workflow

```
You: Get my next request via voice
[Browser automatically starts recording]
You: [speaking] "List my vault secrets"
AI: Voice input received: "List my vault secrets"
[AI then processes your request, using other MCP tools if needed]
```

## MCP Tool API

### get_voice_input

Request voice input from the user.

**Parameters:**
- `language` (optional): Language code (fr, en, es, de, it) - default: "fr"
- `timeout` (optional): Maximum seconds to wait - default: 60

**Returns:**
- Success: `Voice input received: "transcript text"`
- Timeout: `Voice input timed out. User did not provide input within the timeout period.`
- Error: `Error getting voice input: error message`

**Example:**
```python
# French (default)
get_voice_input()

# English
get_voice_input(language="en")

# With custom timeout
get_voice_input(timeout=30)
```

## API Endpoints

### POST /api/request-voice
Create a new voice input request (called by MCP server).

**Request:**
```json
{"language": "fr"}
```

**Response:**
```json
{"request_id": "abc123", "status": "pending"}
```

### GET /api/pending-requests
Get list of pending voice requests (polled by browser).

**Response:**
```json
{
  "requests": [
    {"id": "abc123", "language": "fr"}
  ]
}
```

### POST /api/claim-request/{request_id}
Claim a pending request to prevent duplicate processing.

**Response:**
```json
{"status": "recording"}
```

### POST /api/submit-voice/{request_id}
Submit recorded audio for transcription.

**Request:**
- Multipart form with audio file (WAV format, 16kHz, mono)

**Response:**
```json
{
  "transcript": "user's spoken text",
  "status": "completed"
}
```

### GET /api/result/{request_id}
Get transcription result (polled by MCP server).

**Response:**
```json
{
  "status": "completed",
  "transcript": "user's spoken text",
  "error": null
}
```

## Configuration

### Server Configuration

Edit `server.py`:

```python
WHISPER_HOST = "localhost"
WHISPER_PORT = 10300
PORT = 8766
```

### Whisper Model

Change Whisper model for speed/accuracy tradeoff:

```bash
# Faster, less accurate
--model tiny

# Balanced (default)
--model base

# Slower, more accurate
--model medium
```

### SSL Certificates

Generate self-signed certificates:

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

## Troubleshooting

### Browser Can't Access Microphone

**Check HTTPS:** Browsers require HTTPS for microphone access
```bash
# Verify server is running with SSL
curl -k https://localhost:8766/health
```

**Check Permissions:** Grant microphone access in browser settings

### MCP Server Not Loaded

**Restart Claude Code CLI:**
```bash
# Exit and restart claude command
```

**Check .mcp.json path:**
```bash
# Verify path to mcp-server directory is correct
ls /path/to/mcp-hands-free/mcp-server/pyproject.toml
```

### Whisper Service Not Responding

**Check Whisper is running:**
```bash
curl http://localhost:10300/
```

**Check Wyoming protocol:**
```bash
# Should show Wyoming service info
curl http://localhost:10300/v1/services
```

### Voice Input Times Out

**Check browser is open:** Ensure voice-input.html is loaded

**Check polling:** Open browser console, verify no errors

**Check network:** Ensure browser can reach FastAPI server

## Files

```
mcp-hands-free/
├── mcp-server/                    # MCP server package
│   ├── pyproject.toml
│   └── src/claude_voice_mcp/
│       ├── __init__.py            # Entry point
│       ├── server.py              # Tool definition
│       └── client.py              # HTTP client
├── server.py                      # FastAPI coordination server
├── static/
│   └── voice-input.html           # Browser recording interface
├── requirements.txt               # Python dependencies
├── .gitignore
└── README.md
```

## Security Notes

- **Self-Signed Certificates** - Browsers will warn, click "Accept"
- **No Authentication** - Use firewall or VPN to restrict access
- **In-Memory Storage** - Voice requests stored temporarily in memory
- **Auto-Cleanup** - Audio files deleted after transcription

## Advanced Usage

### Multiple Language Support

Switch languages dynamically:

```python
# Ask for French input
get_voice_input(language="fr")

# Ask for English input
get_voice_input(language="en")
```

### Custom Timeout

Adjust timeout for longer voice inputs:

```python
# Wait up to 2 minutes
get_voice_input(timeout=120)
```

### Integration with Other MCP Tools

Combine voice input with other MCP servers:

```
You: Get my next request via voice
[speaks] "What's in my vault?"
AI: [uses voice input tool, then vault MCP tool to query]
```

## Resources

- **Model Context Protocol**: https://github.com/anthropics/mcp
- **Whisper**: https://github.com/openai/whisper
- **Wyoming Protocol**: https://github.com/rhasspy/wyoming
- **Claude Code CLI**: https://claude.com/claude-code (tested MCP client)

## Compatibility

This MCP server follows the standard **Model Context Protocol** specification and should work with any MCP-compatible client:

- ✅ **Claude Code CLI** - Fully tested and working
- 🔜 **Other MCP Clients** - Should work out of the box (Gemini, Qwen, custom implementations)

If you test this with other MCP clients, please open an issue to share your experience!

## License

MIT License - Free for personal and commercial use.
