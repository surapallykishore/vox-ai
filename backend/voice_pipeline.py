import asyncio
import json
import logging
import time

from .stt import DeepgramSTT
from .tts_manager import TTSManager
from .llm import LLMStream

logger = logging.getLogger(__name__)

# Ignore barge-in for this many seconds after TTS starts speaking,
# to avoid echo from the speaker triggering false interruptions.
BARGE_IN_GRACE_PERIOD = 1.5


class VoicePipeline:
    """Orchestrates the full voice pipeline: STT → LLM → TTS.

    Manages barge-in (user interruption) and streams audio back to the browser.
    """

    def __init__(self, ws):
        """
        Args:
            ws: The browser WebSocket connection (FastAPI WebSocket).
        """
        self._ws = ws
        self._stt = DeepgramSTT()
        self._tts = TTSManager()
        self._llm = LLMStream()
        self._is_speaking = False  # True while TTS audio is being sent
        self._speaking_since = 0.0  # timestamp when TTS audio started
        self._current_gen_task = None
        self._running = False

    async def start(self):
        """Initialize STT connection. TTS connects on-demand per response."""
        self._running = True
        await self._stt.connect(
            on_transcript=self._on_transcript,
            on_speech_started=self._on_speech_started,
        )
        logger.info("Voice pipeline started")

    async def stop(self):
        """Tear down all connections."""
        self._running = False
        if self._current_gen_task and not self._current_gen_task.done():
            self._current_gen_task.cancel()
        await self._stt.close()
        await self._tts.close()
        logger.info("Voice pipeline stopped")

    async def handle_audio(self, audio_bytes: bytes):
        """Forward incoming browser audio to Deepgram STT."""
        await self._stt.send_audio(audio_bytes)

    # --- Callbacks ---

    async def _on_transcript(self, text: str):
        """Called when Deepgram produces a final transcript."""
        logger.info(f"User said: {text}")

        # Send transcript to browser for display
        await self._send_control({
            "type": "transcript",
            "role": "user",
            "text": text,
        })

        # Update status
        await self._send_control({"type": "status", "state": "thinking"})

        # Start LLM → TTS pipeline
        if self._current_gen_task and not self._current_gen_task.done():
            self._current_gen_task.cancel()
        self._current_gen_task = asyncio.create_task(self._generate_response(text))

    async def _on_speech_started(self):
        """Called when Deepgram detects the user started speaking (barge-in)."""
        if not self._is_speaking:
            return

        # Ignore barge-in shortly after TTS starts — likely speaker echo
        elapsed = time.monotonic() - self._speaking_since
        if elapsed < BARGE_IN_GRACE_PERIOD:
            logger.debug(f"Ignoring barge-in (echo grace period, {elapsed:.1f}s)")
            return

        logger.info("Barge-in detected — interrupting AI response")

        # Cancel LLM generation
        self._llm.cancel()
        if self._current_gen_task and not self._current_gen_task.done():
            self._current_gen_task.cancel()

        # Tell browser to stop playing audio
        await self._send_control({"type": "stop_playback"})
        self._is_speaking = False

        # Reconnect TTS for a fresh stream
        await self._tts.reconnect(on_audio=self._on_tts_audio)

        # Update status
        await self._send_control({"type": "status", "state": "listening"})

    async def _on_tts_audio(self, pcm_bytes: bytes):
        """Called when TTS produces an audio chunk."""
        if not self._is_speaking:
            self._speaking_since = time.monotonic()
        self._is_speaking = True
        logger.info(f"TTS audio chunk: {len(pcm_bytes)} bytes")
        try:
            await self._ws.send_bytes(pcm_bytes)
        except Exception:
            logger.warning("Failed to send audio to browser")

    # --- Internal ---

    async def _generate_response(self, user_text: str):
        """Run LLM streaming → TTS streaming."""
        full_response = ""
        try:
            await self._send_control({"type": "status", "state": "speaking"})

            # Connect TTS fresh for this response
            await self._tts.close()
            await self._tts.connect(on_audio=self._on_tts_audio)
            logger.info("TTS connected for new response")

            async for token in self._llm.generate(user_text):
                full_response += token
                await self._tts.send_text(token)

            # Signal end of text to TTS
            await self._tts.flush()
            logger.info(f"LLM done, sent flush. Response length: {len(full_response)}")

            # Send full response text to browser for display
            if full_response:
                await self._send_control({
                    "type": "transcript",
                    "role": "assistant",
                    "text": full_response,
                })

            # Wait for TTS to finish sending audio before closing
            await asyncio.sleep(3)
            self._is_speaking = False
            await self._send_control({"type": "status", "state": "listening"})

        except asyncio.CancelledError:
            logger.info("Response generation cancelled")
        except Exception:
            logger.exception("Error in response generation")
            await self._send_control({"type": "status", "state": "listening"})

    async def _send_control(self, data: dict):
        """Send a JSON control message to the browser."""
        try:
            await self._ws.send_text(json.dumps(data))
        except Exception:
            logger.warning("Failed to send control message to browser")
