"""Unit tests for VoiceClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from claude_voice_mcp.client import VoiceClient


@pytest.fixture
def voice_client():
    """Create a VoiceClient instance for testing."""
    return VoiceClient("https://test-server:8766")


class TestVoiceClient:
    """Test suite for VoiceClient class."""

    def test_init(self):
        """Test client initialization."""
        client = VoiceClient("https://test-server:8766")
        assert client.base_url == "https://test-server:8766"
        assert isinstance(client.client, httpx.AsyncClient)

    def test_init_strips_trailing_slash(self):
        """Test that trailing slashes are removed from base_url."""
        client = VoiceClient("https://test-server:8766/")
        assert client.base_url == "https://test-server:8766"

    @pytest.mark.asyncio
    async def test_get_voice_input_success(self, voice_client):
        """Test successful voice input retrieval."""
        # Mock HTTP responses
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"request_id": "test-123"}
        mock_post_response.raise_for_status = MagicMock()

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "status": "completed",
            "transcript": "Hello world"
        }
        mock_get_response.raise_for_status = MagicMock()

        # Patch the client methods
        voice_client.client.post = AsyncMock(return_value=mock_post_response)
        voice_client.client.get = AsyncMock(return_value=mock_get_response)

        # Execute
        result = await voice_client.get_voice_input(language="en", timeout=60)

        # Verify
        assert result == "Hello world"
        voice_client.client.post.assert_called_once_with(
            "https://test-server:8766/api/request-voice",
            json={"language": "en"}
        )

    @pytest.mark.asyncio
    async def test_get_voice_input_timeout(self, voice_client):
        """Test timeout when user doesn't provide input."""
        # Mock responses - request creation succeeds
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"request_id": "test-123"}
        mock_post_response.raise_for_status = MagicMock()

        # Get response always returns pending status
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "status": "pending",
            "transcript": None
        }
        mock_get_response.raise_for_status = MagicMock()

        voice_client.client.post = AsyncMock(return_value=mock_post_response)
        voice_client.client.get = AsyncMock(return_value=mock_get_response)

        # Should timeout quickly
        with pytest.raises(TimeoutError, match="No voice input received within 1s"):
            await voice_client.get_voice_input(language="en", timeout=1)

    @pytest.mark.asyncio
    async def test_get_voice_input_http_error(self, voice_client):
        """Test handling of HTTP errors."""
        # Mock POST to raise an error
        voice_client.client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=MagicMock(status_code=500)
            )
        )

        # Should propagate the HTTP error
        with pytest.raises(httpx.HTTPStatusError):
            await voice_client.get_voice_input(language="en")

    @pytest.mark.asyncio
    async def test_get_voice_input_default_parameters(self, voice_client):
        """Test using default language and timeout parameters."""
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"request_id": "test-123"}
        mock_post_response.raise_for_status = MagicMock()

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "status": "completed",
            "transcript": "Bonjour"
        }
        mock_get_response.raise_for_status = MagicMock()

        voice_client.client.post = AsyncMock(return_value=mock_post_response)
        voice_client.client.get = AsyncMock(return_value=mock_get_response)

        result = await voice_client.get_voice_input()

        # Verify default language is French
        voice_client.client.post.assert_called_once_with(
            "https://test-server:8766/api/request-voice",
            json={"language": "fr"}
        )
        assert result == "Bonjour"
