/**
 * Manages microphone capture and streams PCM audio over WebSocket.
 */
class AudioCapture {
  constructor() {
    this.audioContext = null;
    this.stream = null;
    this.source = null;
    this.workletNode = null;
    this.ws = null;
    this.active = false;
  }

  /**
   * Start capturing mic audio and streaming to the given WebSocket.
   * @param {WebSocket} ws
   */
  async start(ws) {
    this.ws = ws;

    // Request mic with preferred constraints
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.audioContext = new AudioContext({ sampleRate: 16000 });

    // Load the PCM processor worklet
    await this.audioContext.audioWorklet.addModule("/js/pcm-processor.js");

    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.workletNode = new AudioWorkletNode(
      this.audioContext,
      "pcm-processor"
    );

    // Send PCM chunks via WebSocket
    this.workletNode.port.onmessage = (event) => {
      if (this.active && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(event.data);
      }
    };

    this.source.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);

    this.active = true;
  }

  /**
   * Stop capturing and release resources.
   */
  stop() {
    this.active = false;

    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}

export default AudioCapture;
