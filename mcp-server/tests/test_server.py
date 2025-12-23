"""Unit tests for MCP server."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import TextContent
from claude_voice_mcp.server import list_tools, call_tool


class TestMCPServer:
    """Test suite for MCP server functionality."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test that list_tools returns the voice input tool."""
        tools = await list_tools()

        assert len(tools) == 1
        assert tools[0].name == "get_voice_input"
        assert "voice input" in tools[0].description.lower()

        # Verify schema
        schema = tools[0].inputSchema
        assert schema["type"] == "object"
        assert "language" in schema["properties"]
        assert "timeout" in schema["properties"]

        # Verify language options
        lang_schema = schema["properties"]["language"]
        assert lang_schema["type"] == "string"
        assert "fr" in lang_schema["enum"]
        assert "en" in lang_schema["enum"]

        # Verify timeout constraints
        timeout_schema = schema["properties"]["timeout"]
        assert timeout_schema["type"] == "number"
        assert timeout_schema["default"] == 60
        assert timeout_schema["minimum"] == 10
        assert timeout_schema["maximum"] == 120

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self):
        """Test calling an unknown tool returns error."""
        result = await call_tool("unknown_tool", {})

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].type == "text"
        assert "Unknown tool" in result[0].text

    @pytest.mark.asyncio
    @patch("claude_voice_mcp.server.voice_client")
    async def test_call_tool_success(self, mock_voice_client):
        """Test successful voice input."""
        # Mock the client to return a transcript
        mock_voice_client.get_voice_input = AsyncMock(
            return_value="Hello from user"
        )

        result = await call_tool("get_voice_input", {
            "language": "en",
            "timeout": 30
        })

        # Verify response
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].type == "text"
        assert "Voice input received:" in result[0].text
        assert "Hello from user" in result[0].text

        # Verify client was called with correct params
        mock_voice_client.get_voice_input.assert_called_once_with(
            language="en",
            timeout=30
        )

    @pytest.mark.asyncio
    @patch("claude_voice_mcp.server.voice_client")
    async def test_call_tool_timeout(self, mock_voice_client):
        """Test timeout handling."""
        # Mock timeout error
        mock_voice_client.get_voice_input = AsyncMock(
            side_effect=TimeoutError("Timeout")
        )

        result = await call_tool("get_voice_input", {})

        # Verify timeout message
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "timed out" in result[0].text.lower()

    @pytest.mark.asyncio
    @patch("claude_voice_mcp.server.voice_client")
    async def test_call_tool_error(self, mock_voice_client):
        """Test error handling."""
        # Mock general error
        mock_voice_client.get_voice_input = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        result = await call_tool("get_voice_input", {})

        # Verify error message
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Error getting voice input" in result[0].text
        assert "Connection failed" in result[0].text

    @pytest.mark.asyncio
    @patch("claude_voice_mcp.server.voice_client")
    async def test_call_tool_default_arguments(self, mock_voice_client):
        """Test that default arguments are used when not provided."""
        mock_voice_client.get_voice_input = AsyncMock(
            return_value="Bonjour"
        )

        # Call without arguments
        result = await call_tool("get_voice_input", {})

        # Verify defaults (French, 60s timeout)
        mock_voice_client.get_voice_input.assert_called_once_with(
            language="fr",
            timeout=60
        )
        assert "Bonjour" in result[0].text

    @pytest.mark.asyncio
    @patch("claude_voice_mcp.server.voice_client")
    async def test_call_tool_partial_arguments(self, mock_voice_client):
        """Test with only language specified."""
        mock_voice_client.get_voice_input = AsyncMock(
            return_value="Hello"
        )

        result = await call_tool("get_voice_input", {"language": "en"})

        # Should use default timeout
        mock_voice_client.get_voice_input.assert_called_once_with(
            language="en",
            timeout=60
        )
