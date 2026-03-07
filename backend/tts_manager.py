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
        self._text_buffer = ""
        self._elevenlabs_available = True

    async def connect(self, on_audio):
        """Connect to the best available TTS provider.

        Tries ElevenLabs first. If it fails, marks it unavailable and falls
        back to batch providers (Google/Edge) which don't need a connection.
        """
        self._on_audio = on_audio
        self._text_buffer = ""

        if self._elevenlabs_available:
            try:
                await self._elevenlabs.connect(on_audio)
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

    async def send_text(self, text: str):
        """Send a text token for synthesis.

        ElevenLabs: forwards immediately for streaming synthesis.
        Batch providers: buffers text until flush().
        """
        if self._active_provider == "elevenlabs":
            try:
                await self._elevenlabs.send_text(text)
            except Exception:
                logger.warning("ElevenLabs send failed, will fallback on flush")
                self._elevenlabs_available = False
                self._active_provider = "google" if GOOGLE_CLOUD_TTS_ENABLED else "edge"
                # Buffer this token and all future ones
                self._text_buffer += text
        else:
            self._text_buffer += text

    async def flush(self):
        """Finalize synthesis for the current utterance.

        ElevenLabs: sends EOS marker.
        Batch providers: synthesizes the full buffered text.
        """
        if self._active_provider == "elevenlabs" and self._elevenlabs_available:
            try:
                await self._elevenlabs.flush()
                return
            except Exception:
                logger.warning("ElevenLabs flush failed, falling back")
                self._elevenlabs_available = False

        # Batch synthesis with fallback chain
        text = self._text_buffer.strip()
        self._text_buffer = ""

        if not text:
            return

        # Try Google Cloud TTS
        if GOOGLE_CLOUD_TTS_ENABLED:
            try:
                await self._google.synthesize(text, self._on_audio)
                if self._active_provider != "google":
                    logger.info("ElevenLabs failed, fell back to Google Cloud TTS")
                    self._active_provider = "google"
                return
            except Exception:
                logger.warning("Google Cloud TTS failed, falling back to Edge TTS")

        # Try Edge TTS
        try:
            await self._edge.synthesize(text, self._on_audio)
            if self._active_provider != "edge":
                logger.info("Fell back to Edge TTS")
                self._active_provider = "edge"
        except Exception:
            logger.exception("All TTS providers failed")

    async def close(self):
        """Close any active connections."""
        if self._active_provider == "elevenlabs":
            await self._elevenlabs.close()
        self._text_buffer = ""
        logger.info("TTSManager closed")

    async def reconnect(self, on_audio=None):
        """Close and re-open the connection (used for barge-in)."""
        cb = on_audio or self._on_audio
        await self.close()
        await self.connect(cb)
