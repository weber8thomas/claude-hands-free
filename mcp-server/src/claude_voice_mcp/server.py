import os
from mcp.server import Server
from mcp.types import TextContent, Tool
from typing import Sequence
from .client import VoiceClient

# Create MCP server instance
app = Server("claude-voice")

# Voice API client
VOICE_SERVER = os.getenv("VOICE_SERVER_URL", "https://192.168.0.122:8766")
voice_client = VoiceClient(VOICE_SERVER)

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available voice input tool."""
    return [
        Tool(
            name="get_voice_input",
            description=(
                "Get voice input from the user via browser microphone.\n\n"
                "The user will be prompted to speak via their browser interface. "
                "Audio is transcribed using Whisper (French by default).\n\n"
                "Returns the transcribed text.\n\n"
                "Example usage:\n"
                '  get_voice_input()  # French (default)\n'
                '  get_voice_input(language="en")  # English\n'
                '  get_voice_input(timeout=30)  # 30 second timeout'
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Language code for Whisper (fr, en, es, etc.)",
                        "enum": ["fr", "en", "es", "de", "it"],
                        "default": "fr"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Maximum seconds to wait for voice input",
                        "default": 60,
                        "minimum": 10,
                        "maximum": 120
                    }
                },
                "required": []
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
    """Execute the voice input tool."""
    if name != "get_voice_input":
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]

    language = arguments.get("language", "fr")
    timeout = arguments.get("timeout", 60)

    try:
        # Request voice input
        transcript = await voice_client.get_voice_input(
            language=language,
            timeout=timeout
        )

        return [TextContent(
            type="text",
            text=f'Voice input received: "{transcript}"'
        )]

    except TimeoutError:
        return [TextContent(
            type="text",
            text="⏱️ Voice input timed out. User did not provide input within the timeout period."
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error getting voice input: {str(e)}"
        )]
