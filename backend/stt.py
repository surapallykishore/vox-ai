import asyncio
import json
import logging
from urllib.parse import urlencode

import websockets

from .config import DEEPGRAM_API_KEY, DEEPGRAM_URL, DEEPGRAM_PARAMS

logger = logging.getLogger(__name__)


class DeepgramSTT:
    """Streaming speech-to-text via Deepgram Nova-3 WebSocket API."""

    def __init__(self):
        self._ws = None
        self._receive_task = None
        self._on_transcript = None
        self._on_speech_started = None
        self._keepalive_task = None

    async def connect(self, on_transcript, on_speech_started=None):
        """Open a streaming connection to Deepgram.

        Args:
            on_transcript: async callback(text: str) called on final transcripts.
            on_speech_started: async callback() called when speech is detected.
        """
        self._on_transcript = on_transcript
        self._on_speech_started = on_speech_started

        url = f"{DEEPGRAM_URL}?{urlencode(DEEPGRAM_PARAMS)}"
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        self._ws = await websockets.connect(url, extra_headers=headers)
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        logger.info("Deepgram STT connected")

    async def send_audio(self, audio_bytes: bytes):
        """Forward raw PCM audio to Deepgram."""
        if self._ws and self._ws.open:
            await self._ws.send(audio_bytes)

    async def close(self):
        """Gracefully close the Deepgram connection."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._ws and self._ws.open:
            # Send close message per Deepgram protocol
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            await self._ws.close()
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        logger.info("Deepgram STT closed")

    async def _keepalive_loop(self):
        """Send periodic KeepAlive to prevent Deepgram timeout."""
        try:
            while True:
                await asyncio.sleep(8)
                if self._ws and self._ws.open:
                    await self._ws.send(json.dumps({"type": "KeepAlive"}))
        except asyncio.CancelledError:
            pass

    async def _receive_loop(self):
        """Listen for transcription results from Deepgram."""
        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "SpeechStarted":
                    if self._on_speech_started:
                        await self._on_speech_started()

                elif msg_type == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if not alternatives:
                        continue

                    transcript = alternatives[0].get("transcript", "").strip()
                    is_final = data.get("is_final", False)
                    speech_final = data.get("speech_final", False)

                    if transcript and (is_final or speech_final):
                        logger.info(f"STT final: {transcript}")
                        if self._on_transcript:
                            await self._on_transcript(transcript)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Deepgram connection closed")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error in Deepgram receive loop")
