import logging
from typing import Callable, Awaitable

from google.cloud import texttospeech

from .config import GOOGLE_CLOUD_TTS_ENABLED

logger = logging.getLogger(__name__)


class GoogleCloudTTS:
    """Text-to-speech via Google Cloud TTS (Standard voices).

    Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service
    account JSON file. Uses standard voices (4M chars/mo free tier).
    """

    def __init__(self):
        self._client = None
        self._voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Standard-F",
        )
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
        )

    async def synthesize(self, text: str, on_audio: Callable[[bytes], Awaitable[None]]):
        """Synthesize full text to PCM audio and deliver via callback.

        Args:
            text: Complete text to synthesize.
            on_audio: async callback(pcm_bytes) called with the audio data.
        """
        if not GOOGLE_CLOUD_TTS_ENABLED:
            raise RuntimeError("Google Cloud TTS not configured")

        if not text.strip():
            return

        if self._client is None:
            self._client = texttospeech.TextToSpeechAsyncClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        response = await self._client.synthesize_speech(
            input=synthesis_input,
            voice=self._voice,
            audio_config=self._audio_config,
        )

        # LINEAR16 response has a WAV header (44 bytes) — strip it
        audio_data = response.audio_content
        if len(audio_data) > 44:
            audio_data = audio_data[44:]

        if audio_data:
            await on_audio(audio_data)
            logger.info(f"Google Cloud TTS synthesized {len(text)} chars, {len(audio_data)} bytes audio")
