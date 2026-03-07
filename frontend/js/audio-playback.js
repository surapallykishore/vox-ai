/**
 * Plays back PCM Int16 audio chunks received from the server.
 * Uses Web Audio API with gapless scheduling.
 */
class AudioPlayback {
  constructor() {
    this.audioContext = null;
    this.nextStartTime = 0;
    this.sources = [];
    this.playing = false;
  }

  /**
   * Initialize the playback audio context. Must be called after user gesture.
   */
  async init() {
    if (!this.audioContext) {
      this.audioContext = new AudioContext({ sampleRate: 16000 });
    }
    // Browser autoplay policy: must resume after user gesture
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }
  }

  /**
   * Queue a PCM Int16 chunk for playback.
   * @param {ArrayBuffer} pcmBuffer - Raw Int16 PCM audio data.
   */
  async play(pcmBuffer) {
    if (!this.audioContext) await this.init();
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }

    const int16 = new Int16Array(pcmBuffer);
    if (int16.length === 0) return;

    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    const audioBuffer = this.audioContext.createBuffer(1, float32.length, 16000);
    audioBuffer.getChannelData(0).set(float32);

    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);

    // Schedule gapless playback
    const currentTime = this.audioContext.currentTime;
    const startTime = Math.max(currentTime + 0.01, this.nextStartTime);
    source.start(startTime);

    this.nextStartTime = startTime + audioBuffer.duration;
    this.sources.push(source);
    this.playing = true;

    source.onended = () => {
      const idx = this.sources.indexOf(source);
      if (idx !== -1) this.sources.splice(idx, 1);
      if (this.sources.length === 0) this.playing = false;
    };
  }

  /**
   * Stop all playback immediately (for barge-in).
   */
  stop() {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // Ignore if already stopped
      }
    }
    this.sources = [];
    this.nextStartTime = 0;
    this.playing = false;
  }
}

export default AudioPlayback;
