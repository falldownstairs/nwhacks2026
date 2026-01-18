"""
Text-to-Speech module using ElevenLabs API for Pulsera voice interactions.
Provides streaming audio synthesis for real-time conversational AI.
"""

import asyncio
import base64
import os
from typing import AsyncGenerator, Optional

from elevenlabs import ElevenLabs, VoiceSettings

# ElevenLabs client - initialized lazily
_client: Optional[ElevenLabs] = None

# Default voice settings for warm, compassionate nurse persona
DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # "Sarah" - warm female voice
DEFAULT_MODEL = "eleven_turbo_v2_5"  # Fast, high-quality model for streaming

# Voice settings for consistent, empathetic tone
VOICE_SETTINGS = VoiceSettings(
    stability=0.7,  # Higher stability for consistent medical communication
    similarity_boost=0.8,  # Natural voice matching
    style=0.4,  # Moderate expressiveness - warm but professional
    use_speaker_boost=True,
)


def get_client() -> ElevenLabs:
    """Get or create the ElevenLabs client."""
    global _client
    if _client is None:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable not set")
        _client = ElevenLabs(api_key=api_key)
    return _client


async def synthesize_speech_streaming(
    text: str, voice_id: Optional[str] = None, model: Optional[str] = None
) -> AsyncGenerator[bytes, None]:
    """
    Stream audio synthesis for real-time playback.

    Args:
        text: The text to synthesize
        voice_id: ElevenLabs voice ID (defaults to warm female voice)
        model: ElevenLabs model ID (defaults to turbo for speed)

    Yields:
        Audio chunks as bytes (mp3 format)
    """
    client = get_client()
    voice = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    model_id = model or DEFAULT_MODEL

    # Run the synchronous generator in a thread pool to not block the event loop
    def generate_audio():
        return client.text_to_speech.convert(
            text=text,
            voice_id=voice,
            model_id=model_id,
            voice_settings=VOICE_SETTINGS,
            output_format="mp3_44100_128",
        )

    # Get the generator from thread pool
    loop = asyncio.get_event_loop()
    audio_generator = await loop.run_in_executor(None, generate_audio)

    # Yield chunks from the generator
    for chunk in audio_generator:
        if chunk:
            yield chunk


async def synthesize_speech(
    text: str, voice_id: Optional[str] = None, model: Optional[str] = None
) -> str:
    """
    Synthesize speech and return as base64-encoded audio.

    Args:
        text: The text to synthesize
        voice_id: ElevenLabs voice ID (defaults to warm female voice)
        model: ElevenLabs model ID (defaults to turbo for speed)

    Returns:
        Base64-encoded MP3 audio string
    """
    chunks = []
    async for chunk in synthesize_speech_streaming(text, voice_id, model):
        chunks.append(chunk)

    audio_bytes = b"".join(chunks)
    return base64.b64encode(audio_bytes).decode("utf-8")


async def synthesize_speech_bytes(
    text: str, voice_id: Optional[str] = None, model: Optional[str] = None
) -> bytes:
    """
    Synthesize speech and return as raw bytes.

    Args:
        text: The text to synthesize
        voice_id: ElevenLabs voice ID (defaults to warm female voice)
        model: ElevenLabs model ID (defaults to turbo for speed)

    Returns:
        Raw MP3 audio bytes
    """
    chunks = []
    async for chunk in synthesize_speech_streaming(text, voice_id, model):
        chunks.append(chunk)

    return b"".join(chunks)


def get_available_voices() -> list:
    """
    Get list of available ElevenLabs voices for configuration.

    Returns:
        List of voice dictionaries with id, name, and description
    """
    client = get_client()
    response = client.voices.get_all()
    return [
        {
            "id": voice.voice_id,
            "name": voice.name,
            "description": getattr(voice, "description", None),
            "labels": getattr(voice, "labels", {}),
        }
        for voice in response.voices
    ]
