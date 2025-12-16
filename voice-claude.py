#!/usr/bin/env python3
"""
Voice wrapper for Claude Code CLI
Handles: Audio → Whisper STT → Claude CLI → Piper TTS → Audio
"""

import asyncio
import subprocess
import sys
import wave
import io
from pathlib import Path
from typing import Optional

# Wyoming protocol for Whisper/Piper
from wyoming.audio import wav_to_chunks
from wyoming.client import AsyncClient
from wyoming.asr import Transcribe
from wyoming.tts import Synthesize


class VoiceClaude:
    def __init__(
        self,
        whisper_host: str = "localhost",
        whisper_port: int = 10300,
        piper_host: str = "localhost",
        piper_port: int = 10200,
    ):
        self.whisper_host = whisper_host
        self.whisper_port = whisper_port
        self.piper_host = piper_host
        self.piper_port = piper_port

    async def transcribe_audio(self, audio_path: Path) -> str:
        """Convert audio file to text using Whisper"""
        async with AsyncClient.from_server(self.whisper_host, self.whisper_port) as client:
            # Read WAV file
            with wave.open(str(audio_path), "rb") as wav_file:
                rate = wav_file.getframerate()
                width = wav_file.getsampwidth()
                channels = wav_file.getnchannels()
                audio_data = wav_file.readframes(wav_file.getnframes())

            # Send transcription request
            await client.write_event(
                Transcribe(rate=rate, width=width, channels=channels).event()
            )

            # Stream audio chunks
            for chunk in wav_to_chunks(audio_data, rate, width, channels):
                await client.write_event(chunk.event())

            # Get transcript
            transcript = ""
            while True:
                event = await client.read_event()
                if event is None:
                    break
                if event.type == "transcript":
                    transcript = event.data.get("text", "")
                    break

            return transcript.strip()

    async def synthesize_speech(self, text: str, output_path: Path):
        """Convert text to speech using Piper"""
        async with AsyncClient.from_server(self.piper_host, self.piper_port) as client:
            # Send TTS request
            await client.write_event(Synthesize(text=text).event())

            # Collect audio data
            audio_chunks = []
            while True:
                event = await client.read_event()
                if event is None:
                    break
                if event.type == "audio-chunk":
                    audio_chunks.append(event.data.get("audio", b""))
                elif event.type == "audio-stop":
                    break

            # Write WAV file
            if audio_chunks:
                # Wyoming protocol sends raw PCM data
                # We need to wrap it in WAV format
                audio_data = b"".join(audio_chunks)
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(22050)  # Piper default
                    wav_file.writeframes(audio_data)

    def run_claude(self, prompt: str) -> str:
        """Run Claude Code CLI with the prompt"""
        try:
            result = subprocess.run(
                ["claude", "chat", "-m", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "Claude timed out. Please try again."
        except Exception as e:
            return f"Error running Claude: {e}"

    async def process_voice_input(self, audio_input: Path, audio_output: Path):
        """Complete voice interaction pipeline"""
        print("🎤 Transcribing audio...")
        text = await self.transcribe_audio(audio_input)

        if not text:
            print("❌ No speech detected")
            return

        print(f"📝 You said: {text}")
        print("🤔 Asking Claude...")

        response = self.run_claude(text)
        print(f"💬 Claude: {response}")

        print("🔊 Generating speech...")
        await self.synthesize_speech(response, audio_output)
        print(f"✅ Audio saved to: {audio_output}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: voice-claude.py <input.wav> [output.wav]")
        print("Example: voice-claude.py recording.wav response.wav")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2] if len(sys.argv) > 2 else "response.wav")

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    voice_claude = VoiceClaude()
    await voice_claude.process_voice_input(input_path, output_path)


if __name__ == "__main__":
    asyncio.run(main())
