import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .voice_pipeline import VoicePipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Voice Agent")

# Serve frontend static files
app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")


@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    await ws.accept()
    logger.info("Browser WebSocket connected")

    pipeline = VoicePipeline(ws)

    try:
        await pipeline.start()

        while True:
            message = await ws.receive()

            if message.get("bytes"):
                # Binary = PCM audio from mic
                await pipeline.handle_audio(message["bytes"])
            elif message.get("text"):
                # JSON control messages from browser
                import json
                data = json.loads(message["text"])
                msg_type = data.get("type", "")

                if msg_type == "stop":
                    break

    except WebSocketDisconnect:
        logger.info("Browser WebSocket disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        await pipeline.stop()
        logger.info("Voice session ended")
