import asyncio
import base64
import json
import logging
from urllib.parse import urlencode

import websockets

from .config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_OUTPUT_FORMAT,
    ELEVENLABS_VOICE_ID,
)

logger = logging.getLogger(__name__)


class ElevenLabsTTS:
    """Streaming text-to-speech via ElevenLabs WebSocket API."""

    def __init__(self):
        self._ws = None
        self._receive_task = None
        self._on_audio = None

    async def connect(self, on_audio):
        """Open a streaming connection to ElevenLabs.

        Args:
            on_audio: async callback(pcm_bytes: bytes) called for each audio chunk.
        """
        self._on_audio = on_audio

        params = urlencode({
            "model_id": ELEVENLABS_MODEL,
            "output_format": ELEVENLABS_OUTPUT_FORMAT,
        })
        url = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/"
            f"{ELEVENLABS_VOICE_ID}/stream-input?{params}"
        )

        self._ws = await websockets.connect(url)

        # Send BOS (beginning of stream) with API key and voice settings
        bos = {
            "text": " ",
            "xi_api_key": ELEVENLABS_API_KEY,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
            "generation_config": {
                "chunk_length_schedule": [120, 160, 250, 290],
            },
            "try_trigger_generation": True,
        }
        await self._ws.send(json.dumps(bos))

        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("ElevenLabs TTS connected")

    async def send_text(self, text: str):
        """Stream a text chunk to ElevenLabs for synthesis."""
        if self._ws and self._ws.open:
            msg = {
                "text": text,
                "try_trigger_generation": True,
            }
            await self._ws.send(json.dumps(msg))

    async def flush(self):
        """Send EOS (end of stream) to trigger final audio generation."""
        if self._ws and self._ws.open:
            await self._ws.send(json.dumps({"text": ""}))

    async def close(self):
        """Close the ElevenLabs connection."""
        if self._ws and self._ws.open:
            try:
                await self._ws.send(json.dumps({"text": ""}))
            except Exception:
                pass
            await self._ws.close()
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        logger.info("ElevenLabs TTS closed")

    async def reconnect(self, on_audio=None):
        """Close and re-open the connection (used for barge-in)."""
        cb = on_audio or self._on_audio
        await self.close()
        await self.connect(cb)

    async def _receive_loop(self):
        """Listen for audio chunks from ElevenLabs."""
        try:
            async for message in self._ws:
                data = json.loads(message)

                if data.get("audio"):
                    pcm_bytes = base64.b64decode(data["audio"])
                    if self._on_audio:
                        await self._on_audio(pcm_bytes)

                if data.get("isFinal"):
                    logger.debug("ElevenLabs stream complete")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"ElevenLabs connection closed: code={e.code} reason={e.reason}")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error in ElevenLabs receive loop")
