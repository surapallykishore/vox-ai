import asyncio
import logging

from .tts_elevenlabs import ElevenLabsTTS
from .tts_google import GoogleCloudTTS
from .tts_edge import EdgeTTS
from .config import GOOGLE_CLOUD_TTS_ENABLED

logger = logging.getLogger(__name__)


class TTSManager:
    """Unified TTS interface with ElevenLabs -> Google Cloud -> Edge fallback.

    Exposes the same API as ElevenLabsTTS so voice_pipeline.py needs minimal
    changes: connect(), send_text(), flush(), close(), reconnect().

    ElevenLabs supports token-by-token streaming. Google Cloud TTS and Edge TTS
    require the complete text, so tokens are buffered and synthesized on flush().
    """

    def __init__(self):
        self._elevenlabs = ElevenLabsTTS()
        self._google = GoogleCloudTTS()
        self._edge = EdgeTTS()

        self._on_audio = None
        self._active_provider = None  # "elevenlabs" | "google" | "edge"
        self._text_buffer = ""  # always accumulates text for fallback
        self._elevenlabs_available = True
        self._audio_received = False  # tracks if ElevenLabs actually sent audio

    async def connect(self, on_audio):
        """Connect to the best available TTS provider."""
        self._on_audio = on_audio
        self._text_buffer = ""
        self._audio_received = False

        if self._elevenlabs_available:
            try:
                await self._elevenlabs.connect(self._on_elevenlabs_audio)
                self._active_provider = "elevenlabs"
                logger.info("Using ElevenLabs TTS")
                return
            except Exception:
                logger.warning("ElevenLabs connection failed, marking unavailable")
                self._elevenlabs_available = False

        # Batch providers don't need a persistent connection
        if GOOGLE_CLOUD_TTS_ENABLED:
            self._active_provider = "google"
            logger.info("Using Google Cloud TTS (fallback)")
        else:
            self._active_provider = "edge"
            logger.info("Using Edge TTS (fallback)")

    async def _on_elevenlabs_audio(self, pcm_bytes: bytes):
        """Wrapper callback that tracks whether ElevenLabs delivered audio."""
        self._audio_received = True
        if self._on_audio:
            await self._on_audio(pcm_bytes)

    async def send_text(self, text: str):
        """Send a text token for synthesis.

        Always buffers text for fallback. If ElevenLabs is active, also
        forwards immediately for streaming synthesis.
        """
        # Always buffer — needed if ElevenLabs silently fails
        self._text_buffer += text

        if self._active_provider == "elevenlabs":
            try:
                await self._elevenlabs.send_text(text)
            except Exception:
                logger.warning("ElevenLabs send failed, will fallback on flush")
                self._elevenlabs_available = False
                self._active_provider = "google" if GOOGLE_CLOUD_TTS_ENABLED else "edge"

    async def flush(self):
        """Finalize synthesis for the current utterance.

        ElevenLabs: sends EOS and waits briefly for audio. If no audio arrives,
        falls back to batch providers with the full buffered text.
        """
        text = self._text_buffer.strip()
        self._text_buffer = ""

        if self._active_provider == "elevenlabs" and self._elevenlabs_available:
            try:
                await self._elevenlabs.flush()
                # Wait briefly for ElevenLabs to deliver audio
                await asyncio.sleep(0.5)

                if self._audio_received:
                    # ElevenLabs worked, we're done
                    self._audio_received = False
                    return

                # ElevenLabs didn't deliver audio — connection was likely killed
                logger.warning("ElevenLabs sent no audio, falling back")
                self._elevenlabs_available = False
            except Exception:
                logger.warning("ElevenLabs flush failed, falling back")
                self._elevenlabs_available = False

        if not text:
            return

        # Batch synthesis with fallback chain
        logger.info(f"Synthesizing via fallback ({len(text)} chars)")

        # Try Google Cloud TTS
        if GOOGLE_CLOUD_TTS_ENABLED:
            try:
                await self._google.synthesize(text, self._on_audio)
                self._active_provider = "google"
                logger.info("Fallback to Google Cloud TTS succeeded")
                return
            except Exception:
                logger.warning("Google Cloud TTS failed, falling back to Edge TTS")

        # Try Edge TTS
        try:
            await self._edge.synthesize(text, self._on_audio)
            self._active_provider = "edge"
            logger.info("Fallback to Edge TTS succeeded")
        except Exception:
            logger.exception("All TTS providers failed")

    async def close(self):
        """Close any active connections."""
        if self._active_provider == "elevenlabs":
            await self._elevenlabs.close()
        self._text_buffer = ""
        self._audio_received = False
        logger.info("TTSManager closed")

    async def reconnect(self, on_audio=None):
        """Close and re-open the connection (used for barge-in)."""
        cb = on_audio or self._on_audio
        await self.close()
        await self.connect(cb)
