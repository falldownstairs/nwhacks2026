# agents/speech_to_text.py
"""
Speech-to-Text integration using Groq's Whisper API.
Provides fast, accurate transcription for voice-based health check-ins.
"""

import base64
import os
import tempfile
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqSpeechToText:
    """
    Speech-to-text transcription using Groq's Whisper API.
    Optimized for fast transcription of health-related conversations.
    """

    def __init__(self):
        """Initialize the Groq STT client."""
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in environment variables")

        self.api_key = GROQ_API_KEY
        self.model = "whisper-large-v3-turbo"  # Fast and accurate

    async def transcribe_audio(
        self,
        audio_data: bytes,
        audio_format: str = "webm",
        language: Optional[str] = "en",
    ) -> Dict[str, Any]:
        """
        Transcribe audio data to text.

        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format (webm, wav, mp3, etc.)
            language: Optional language hint (default: English)

        Returns:
            Dict with transcription result
        """
        try:
            # Create a temporary file with the audio data
            suffix = f".{audio_format}"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name

            # Make the API request
            async with httpx.AsyncClient() as client:
                with open(temp_path, "rb") as audio_file:
                    files = {
                        "file": (f"audio{suffix}", audio_file, f"audio/{audio_format}")
                    }
                    data = {
                        "model": self.model,
                        "response_format": "json",
                    }
                    if language:
                        data["language"] = language

                    response = await client.post(
                        GROQ_API_URL,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files=files,
                        data=data,
                        timeout=30.0,
                    )

            # Clean up temp file
            os.unlink(temp_path)

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "text": result.get("text", "").strip(),
                    "language": language or "en",
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code} - {response.text}",
                    "text": "",
                }

        except Exception as e:
            return {"success": False, "error": str(e), "text": ""}

    async def transcribe_base64(
        self,
        audio_base64: str,
        audio_format: str = "webm",
        language: Optional[str] = "en",
    ) -> Dict[str, Any]:
        """
        Transcribe base64-encoded audio data.

        Args:
            audio_base64: Base64-encoded audio string
            audio_format: Audio format (webm, wav, mp3, etc.)
            language: Optional language hint

        Returns:
            Dict with transcription result
        """
        try:
            # Decode base64 to bytes
            audio_bytes = base64.b64decode(audio_base64)
            return await self.transcribe_audio(audio_bytes, audio_format, language)
        except Exception as e:
            return {
                "success": False,
                "error": f"Base64 decode error: {str(e)}",
                "text": "",
            }


# Singleton instance for reuse
_stt_instance: Optional[GroqSpeechToText] = None


def get_stt_client() -> GroqSpeechToText:
    """Get or create the STT client singleton."""
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = GroqSpeechToText()
    return _stt_instance


async def transcribe_audio(
    audio_data: bytes, audio_format: str = "webm", language: str = "en"
) -> Dict[str, Any]:
    """
    Convenience function to transcribe audio.

    Args:
        audio_data: Raw audio bytes
        audio_format: Audio format
        language: Language hint

    Returns:
        Transcription result dict
    """
    client = get_stt_client()
    return await client.transcribe_audio(audio_data, audio_format, language)


async def transcribe_base64(
    audio_base64: str, audio_format: str = "webm", language: str = "en"
) -> Dict[str, Any]:
    """
    Convenience function to transcribe base64 audio.

    Args:
        audio_base64: Base64-encoded audio
        audio_format: Audio format
        language: Language hint

    Returns:
        Transcription result dict
    """
    client = get_stt_client()
    return await client.transcribe_base64(audio_base64, audio_format, language)
    return await client.transcribe_base64(audio_base64, audio_format, language)
