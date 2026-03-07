import os
from dotenv import load_dotenv

load_dotenv(override=True)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_PARAMS = {
    "model": "nova-3",
    "encoding": "linear16",
    "sample_rate": "16000",
    "channels": "1",
    "interim_results": "true",
    "endpointing": "300",
    "utterance_end_ms": "1000",
    "smart_format": "true",
    "punctuate": "true",
    "vad_events": "true",
}

ELEVENLABS_MODEL = "eleven_turbo_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "pcm_16000"

GOOGLE_CLOUD_TTS_ENABLED = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")

LLM_MODEL = "claude-haiku-4-5-20251001"
