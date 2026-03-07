import io
import logging
import struct
from typing import Callable, Awaitable

import edge_tts

from .config import EDGE_TTS_VOICE

logger = logging.getLogger(__name__)


def _resample_linear(pcm_data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit mono PCM using linear interpolation. No external deps."""
    if src_rate == dst_rate:
        return pcm_data

    # Unpack 16-bit signed samples
    n_samples = len(pcm_data) // 2
    if n_samples == 0:
        return b""
    samples = struct.unpack(f"<{n_samples}h", pcm_data)

    ratio = src_rate / dst_rate
    out_len = int(n_samples / ratio)
    out = []

    for i in range(out_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx

        if idx + 1 < n_samples:
            val = samples[idx] * (1 - frac) + samples[idx + 1] * frac
        else:
            val = samples[idx]

        out.append(max(-32768, min(32767, int(val))))

    return struct.pack(f"<{len(out)}h", *out)


def _decode_mp3_to_pcm(mp3_data: bytes) -> tuple[bytes, int]:
    """Decode MP3 bytes to raw PCM 16-bit mono. Returns (pcm_bytes, sample_rate).

    Uses the built-in `audioop` or `io` + `wave` if available, but for MP3 we
    need a decoder. We use the `minimp3` approach via the `io` module with a
    minimal MP3 frame parser. In practice, edge-tts MP3 is 24kHz mono.

    Falls back to using subprocess with ffmpeg if available, otherwise raises.
    """
    import subprocess
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg to use Edge TTS: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
        )

    # Use ffmpeg to decode MP3 → raw PCM 16-bit mono
    proc = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "24000",
            "-",
        ],
        input=mp3_data,
        capture_output=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.decode()}")

    return proc.stdout, 24000


class EdgeTTS:
    """Text-to-speech via Edge TTS (free, no API key).

    Uses Microsoft Edge's online TTS service. Outputs MP3 which is decoded
    to PCM via ffmpeg, then resampled from 24kHz to 16kHz.
    """

    async def synthesize(self, text: str, on_audio: Callable[[bytes], Awaitable[None]]):
        """Synthesize full text to PCM audio and deliver via callback.

        Args:
            text: Complete text to synthesize.
            on_audio: async callback(pcm_bytes) called with the audio data.
        """
        if not text.strip():
            return

        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)

        # Collect all MP3 chunks
        mp3_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        if not mp3_chunks:
            logger.warning("Edge TTS returned no audio")
            return

        mp3_data = b"".join(mp3_chunks)

        # Decode MP3 → PCM 24kHz
        pcm_24k, src_rate = _decode_mp3_to_pcm(mp3_data)

        # Resample 24kHz → 16kHz
        pcm_16k = _resample_linear(pcm_24k, src_rate, 16000)

        if pcm_16k:
            await on_audio(pcm_16k)
            logger.info(f"Edge TTS synthesized {len(text)} chars, {len(pcm_16k)} bytes audio")
