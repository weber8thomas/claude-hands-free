# Quick Start Guide - MCP Hands-Free

Get voice interaction with your MCP-compatible AI running in 5 minutes!

## TL;DR

```bash
# Server
cd /path/to/mcp-hands-free
pip3 install -r requirements.txt
python3 server.py

# Client (Browser)
# Open https://your-server:8766/static/voice-input.html
```

## Step-by-Step

### 1. Start Whisper Service

Using Docker (recommended):

```bash
docker run -d \
  --name whisper \
  -p 10300:10300 \
  rhasspy/wyoming-faster-whisper \
  --model base \
  --language en

# Verify
docker logs whisper
curl http://localhost:10300/
```

Or install locally following [Wyoming Whisper docs](https://github.com/rhasspy/wyoming-faster-whisper).

### 2. Start FastAPI Server

```bash
cd /path/to/mcp-hands-free
pip3 install -r requirements.txt
python3 server.py
```

You should see:
```
✅ Starting server on https://0.0.0.0:8766
INFO: Started server process
```

### 3. Configure MCP Client

Add to your `.mcp.json` (or MCP client configuration):

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

Replace `/path/to/mcp-hands-free` with your actual path.

### 4. Open Browser Interface

Navigate to:
```
https://your-server:8766/static/voice-input.html
```

Accept the self-signed certificate warning and grant microphone permissions.

### 5. Use Voice Input!

In your AI agent CLI:

```
You: "Get my next request via voice"
```

The browser will automatically start recording, you speak, and your AI receives the transcript.

## First Conversation

```
You: Get my next request via voice
[Browser automatically starts recording]
You: [speaking] "List the files in the current directory"
AI: Voice input received: "List the files in the current directory"
[AI processes the request using available tools]
```

## Testing the API

Test endpoints directly:

```bash
# Test voice request creation
curl -X POST https://localhost:8766/api/request-voice \
  -H "Content-Type: application/json" \
  -d '{"language": "en"}' \
  -k

# Check health
curl https://localhost:8766/health -k
```

## Troubleshooting

### Server won't start

```bash
# Check ports are free
lsof -i :8766  # FastAPI server
lsof -i :10300 # Whisper service

# Check Whisper is running
docker ps | grep whisper
curl http://localhost:10300/
```

### Browser can't connect

```bash
# Test server health
curl https://your-server:8766/health -k

# Check firewall (if applicable)
# sudo ufw allow 8766/tcp
```

### Browser can't access microphone

- Ensure you're using **HTTPS** (browsers require it for microphone access)
- Check browser permissions: Settings → Privacy → Microphone
- Accept the self-signed certificate warning

### MCP server not loading

```bash
# Verify path in .mcp.json is correct
ls /path/to/mcp-hands-free/mcp-server/pyproject.toml

# Restart your MCP client
# The MCP server is loaded when your AI agent CLI starts
```

### Voice input times out

- Ensure browser interface is open and active
- Check browser console for errors (F12 → Console)
- Verify network connectivity between browser and server
- Check that Whisper service is running and responding

## What's Next?

- Try different languages: `get_voice_input(language="fr")`
- Adjust timeout: `get_voice_input(timeout=120)`
- Combine with other MCP tools for powerful workflows

## Architecture

```
MCP Client (Claude Code, Gemini, etc.)
  ↓ calls get_voice_input()
MCP Server (stdio)
  ↓ HTTP POST
FastAPI Server
  ↓ stores request
Browser Interface
  ↓ polls for requests
  ↓ records audio
  ↓ submits audio
FastAPI Server
  ↓ sends to Whisper
Whisper Service (Wyoming)
  ↓ transcribes
MCP Client
  └─ receives transcript
```

Enjoy hands-free AI interactions!
