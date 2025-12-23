"""Unit tests for FastAPI server endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import io


# Import server app
# We need to mock Wyoming dependencies before importing
with patch("wyoming.client.AsyncClient"):
    from server import app, voice_requests, voice_requests_lock


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def reset_voice_requests():
    """Reset voice requests before each test."""
    voice_requests.clear()
    yield
    voice_requests.clear()


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestVoiceRequestEndpoints:
    """Tests for MCP voice request endpoints."""

    def test_request_voice_creates_pending_request(self, client, reset_voice_requests):
        """Test creating a voice request."""
        response = client.post(
            "/api/request-voice",
            json={"language": "en"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["status"] == "pending"

        # Verify request is stored
        request_id = data["request_id"]
        assert request_id in voice_requests
        assert voice_requests[request_id]["language"] == "en"
        assert voice_requests[request_id]["status"] == "pending"

    def test_request_voice_default_language(self, client, reset_voice_requests):
        """Test creating request with default language."""
        response = client.post(
            "/api/request-voice",
            json={}
        )

        assert response.status_code == 200
        data = response.json()
        request_id = data["request_id"]

        # Should use default French
        assert voice_requests[request_id]["language"] == "fr"

    def test_get_pending_requests_empty(self, client, reset_voice_requests):
        """Test getting pending requests when none exist."""
        response = client.get("/api/pending-requests")

        assert response.status_code == 200
        data = response.json()
        assert data["requests"] == []

    def test_get_pending_requests_with_requests(self, client, reset_voice_requests):
        """Test getting pending requests."""
        # Create two requests
        response1 = client.post("/api/request-voice", json={"language": "en"})
        response2 = client.post("/api/request-voice", json={"language": "fr"})

        request_id1 = response1.json()["request_id"]
        request_id2 = response2.json()["request_id"]

        # Get pending requests
        response = client.get("/api/pending-requests")
        assert response.status_code == 200
        data = response.json()

        assert len(data["requests"]) == 2
        ids = [r["id"] for r in data["requests"]]
        assert request_id1 in ids
        assert request_id2 in ids

    def test_claim_request_success(self, client, reset_voice_requests):
        """Test claiming a pending request."""
        # Create request
        response = client.post("/api/request-voice", json={"language": "en"})
        request_id = response.json()["request_id"]

        # Claim it
        response = client.post(f"/api/claim-request/{request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recording"

        # Verify status changed
        assert voice_requests[request_id]["status"] == "recording"

        # Should not appear in pending requests anymore
        response = client.get("/api/pending-requests")
        data = response.json()
        assert len(data["requests"]) == 0

    def test_claim_request_not_found(self, client, reset_voice_requests):
        """Test claiming non-existent request."""
        response = client.post("/api/claim-request/nonexistent")
        assert response.status_code == 404

    @patch("server.transcribe_audio")
    def test_submit_voice_success(self, mock_transcribe, client, reset_voice_requests):
        """Test submitting voice recording."""
        # Mock transcription
        mock_transcribe.return_value = AsyncMock(return_value="Hello world")()

        # Create and claim request
        response = client.post("/api/request-voice", json={"language": "en"})
        request_id = response.json()["request_id"]
        client.post(f"/api/claim-request/{request_id}")

        # Create a fake WAV file
        wav_data = self._create_minimal_wav()

        # Submit audio
        response = client.post(
            f"/api/submit-voice/{request_id}",
            files={"audio": ("test.wav", wav_data, "audio/wav")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

        # Verify request is marked completed
        assert voice_requests[request_id]["status"] == "completed"

    def test_submit_voice_not_found(self, client, reset_voice_requests):
        """Test submitting to non-existent request."""
        wav_data = self._create_minimal_wav()
        response = client.post(
            "/api/submit-voice/nonexistent",
            files={"audio": ("test.wav", wav_data, "audio/wav")}
        )
        assert response.status_code == 404

    def test_get_result_completed(self, client, reset_voice_requests):
        """Test getting result of completed request."""
        # Create request and manually complete it
        response = client.post("/api/request-voice", json={"language": "en"})
        request_id = response.json()["request_id"]

        voice_requests[request_id]["status"] = "completed"
        voice_requests[request_id]["transcript"] = "Test transcript"

        # Get result
        response = client.get(f"/api/result/{request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["transcript"] == "Test transcript"
        assert data["error"] is None

    def test_get_result_pending(self, client, reset_voice_requests):
        """Test getting result of pending request."""
        response = client.post("/api/request-voice", json={"language": "en"})
        request_id = response.json()["request_id"]

        # Get result while still pending
        response = client.get(f"/api/result/{request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["transcript"] is None

    def test_get_result_not_found(self, client, reset_voice_requests):
        """Test getting result of non-existent request."""
        response = client.get("/api/result/nonexistent")
        assert response.status_code == 404

    @staticmethod
    def _create_minimal_wav():
        """Create a minimal valid WAV file for testing."""
        import wave
        import struct

        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)  # mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(16000)  # 16kHz
            # Write 1 second of silence
            frames = struct.pack('h' * 16000, *([0] * 16000))
            wav.writeframes(frames)

        output.seek(0)
        return output.read()


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root_returns_html(self, client):
        """Test root endpoint returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
