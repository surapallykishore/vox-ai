import AudioCapture from "./audio-capture.js";
import AudioPlayback from "./audio-playback.js";

const capture = new AudioCapture();
const playback = new AudioPlayback();

// DOM elements
const micBtn = document.getElementById("mic-btn");
const micIcon = document.getElementById("mic-icon");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const stateLabel = document.getElementById("state-label");
const transcript = document.getElementById("transcript");

let ws = null;
let isActive = false;

// --- WebSocket ---

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws/voice`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    statusDot.classList.add("connected");
    statusText.textContent = "Connected";
  };

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      // Binary = PCM audio from TTS
      console.log(`Audio chunk received: ${event.data.byteLength} bytes`);
      playback.play(event.data);
    } else {
      // JSON control message
      const data = JSON.parse(event.data);
      handleControlMessage(data);
    }
  };

  ws.onclose = () => {
    statusDot.classList.remove("connected");
    statusText.textContent = "Disconnected";
    if (isActive) {
      // Auto-reconnect after 2s
      setTimeout(connectWebSocket, 2000);
    }
  };

  ws.onerror = () => {
    console.error("WebSocket error");
  };
}

function handleControlMessage(data) {
  switch (data.type) {
    case "transcript":
      addTranscript(data.role, data.text);
      break;

    case "status":
      updateState(data.state);
      break;

    case "stop_playback":
      playback.stop();
      break;
  }
}

// --- UI ---

function addTranscript(role, text) {
  const div = document.createElement("div");
  div.classList.add("message", role);

  const label = document.createElement("span");
  label.classList.add("message-label");
  label.textContent = role === "user" ? "You" : "AI";

  const content = document.createElement("span");
  content.classList.add("message-text");
  content.textContent = text;

  div.appendChild(label);
  div.appendChild(content);
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
}

function updateState(state) {
  micBtn.className = "mic-btn " + state;
  const labels = {
    idle: "Click to start",
    listening: "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
  };
  stateLabel.textContent = labels[state] || "";
}

// --- Mic Button ---

micBtn.addEventListener("click", async () => {
  if (!isActive) {
    await startSession();
  } else {
    stopSession();
  }
});

async function startSession() {
  isActive = true;
  await playback.init();
  connectWebSocket();

  // Wait for WS to open
  await new Promise((resolve) => {
    const check = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        clearInterval(check);
        resolve();
      }
    }, 50);
  });

  await capture.start(ws);
  updateState("listening");
  micIcon.textContent = "\u23F9"; // stop icon
}

function stopSession() {
  isActive = false;
  capture.stop();
  playback.stop();

  if (ws) {
    ws.send(JSON.stringify({ type: "stop" }));
    ws.close();
    ws = null;
  }

  updateState("idle");
  micIcon.textContent = "\uD83C\uDF99"; // mic icon
}
