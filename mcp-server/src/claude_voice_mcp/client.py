import httpx
import asyncio

class VoiceClient:
    """HTTP client for voice server API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(verify=False)  # Self-signed cert

    async def get_voice_input(
        self,
        language: str = "fr",
        timeout: int = 60
    ) -> str:
        """
        Request voice input and wait for transcript.

        Returns:
            Transcript text

        Raises:
            TimeoutError: If user doesn't provide input within timeout
            Exception: On other errors
        """
        # 1. Create voice request
        response = await self.client.post(
            f"{self.base_url}/api/request-voice",
            json={"language": language}
        )
        response.raise_for_status()
        data = response.json()
        request_id = data["request_id"]

        # 2. Poll for result
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"No voice input received within {timeout}s")

            # Check result
            response = await self.client.get(
                f"{self.base_url}/api/result/{request_id}"
            )
            response.raise_for_status()
            result = response.json()

            if result["status"] == "completed":
                return result["transcript"]

            # Wait before next poll
            await asyncio.sleep(1)
