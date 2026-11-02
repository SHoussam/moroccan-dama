const MUTE_STORAGE_KEY = "dama_sound_muted";

function readStoredMute() {
  try {
    return localStorage.getItem(MUTE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStoredMute(muted) {
  try {
    localStorage.setItem(MUTE_STORAGE_KEY, muted ? "1" : "0");
  } catch {
    // Ignore storage errors
  }
}

/**
 * Zero-dependency Web Audio synthesizer crafted for Moroccan Street Dama:
 * - Bottle caps ("white"): metallic tin-cap clinks & rattles on wood
 * - Street pebbles ("black"): stony pebble taps & knocks on cedar wood
 * - Promotion, multi-jump rising combos, Moroccan mint-tea glass clink on taunts, and win chords
 */
export class SoundEngine {
  constructor() {
    this.muted = readStoredMute();
    this.ctx = null;
    this._noiseBuffer = null;
    this._bindUnlock();
  }

  _bindUnlock() {
    const unlock = () => {
      this._ensureContext();
    };
    window.addEventListener("pointerdown", unlock, { passive: true });
    window.addEventListener("keydown", unlock, { passive: true });
  }

  _ensureContext() {
    if (this.muted) return null;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;

    if (!this.ctx) {
      try {
        this.ctx = new AudioCtx();
      } catch {
        return null;
      }
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  _getNoiseBuffer(ctx) {
    if (this._noiseBuffer) return this._noiseBuffer;
    const length = Math.floor(ctx.sampleRate * 0.15);
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) {
      data[i] = Math.random() * 2 - 1;
    }
    this._noiseBuffer = buffer;
    return buffer;
  }

  isMuted() {
    return this.muted;
  }

  toggleMute() {
    this.muted = !this.muted;
    writeStoredMute(this.muted);
    if (!this.muted) {
      this._ensureContext();
      this.playSelect("white");
    }
    return this.muted;
  }

  _tone(ctx, { freq, endFreq = null, type = "sine", start = 0, duration = 0.08, gain = 0.12 }) {
    const t0 = ctx.currentTime + start;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (endFreq !== null) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(20, endFreq), t0 + duration);
    }
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
    osc.connect(g);
    g.connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + duration + 0.01);
  }

  _noiseBurst(ctx, { filterFreq = 1200, q = 2.5, start = 0, duration = 0.045, gain = 0.12 }) {
    const t0 = ctx.currentTime + start;
    const src = ctx.createBufferSource();
    src.buffer = this._getNoiseBuffer(ctx);

    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.setValueAtTime(filterFreq, t0);
    filter.Q.setValueAtTime(q, t0);

    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);

    src.connect(filter);
    filter.connect(g);
    g.connect(ctx.destination);
    src.start(t0);
    src.stop(t0 + duration + 0.01);
  }

  playSelect(color = "white") {
    const ctx = this._ensureContext();
    if (!ctx) return;
    if (color === "white") {
      // Crisp finger tap on tin bottle cap
      this._tone(ctx, { freq: 2350, endFreq: 1900, type: "triangle", duration: 0.032, gain: 0.06 });
      this._tone(ctx, { freq: 3820, type: "sine", duration: 0.024, gain: 0.035 });
    } else {
      // Dry stone pebble tap
      this._noiseBurst(ctx, { filterFreq: 920, q: 3.2, duration: 0.028, gain: 0.09 });
      this._tone(ctx, { freq: 440, endFreq: 210, type: "triangle", duration: 0.03, gain: 0.055 });
    }
  }

  playMove(color = "white") {
    const ctx = this._ensureContext();
    if (!ctx) return;
    if (color === "white") {
      // Bottle cap slide + double tinny rim clink on wooden board
      this._noiseBurst(ctx, { filterFreq: 2600, q: 2.0, duration: 0.04, gain: 0.07 });
      this._tone(ctx, { freq: 210, endFreq: 115, type: "sine", duration: 0.055, gain: 0.09 });
      this._tone(ctx, { freq: 1890, endFreq: 1720, type: "triangle", start: 0.006, duration: 0.065, gain: 0.08 });
      this._tone(ctx, { freq: 3140, type: "sine", start: 0.018, duration: 0.055, gain: 0.055 });
    } else {
      // Street rock solid pebble knock on cedar board
      this._tone(ctx, { freq: 165, endFreq: 82, type: "sine", duration: 0.075, gain: 0.16 });
      this._tone(ctx, { freq: 590, endFreq: 280, type: "triangle", duration: 0.045, gain: 0.09 });
      this._noiseBurst(ctx, { filterFreq: 820, q: 2.6, duration: 0.042, gain: 0.12 });
    }
  }

  playCaptureHop(moverColor = "white", hopIndex = 0) {
    const ctx = this._ensureContext();
    if (!ctx) return;
    const mult = Math.pow(1.13, Math.min(hopIndex, 5));

    // Heavy slam + clatter of captured piece flying off
    this._tone(ctx, {
      freq: 175 * mult,
      endFreq: 78,
      type: "sine",
      duration: 0.095,
      gain: 0.19,
    });
    this._noiseBurst(ctx, {
      filterFreq: (moverColor === "white" ? 2400 : 1050) * mult,
      q: 2.1,
      duration: 0.06,
      gain: 0.14,
    });
    // Captured piece rattle bounce
    this._tone(ctx, {
      freq: (moverColor === "white" ? 1650 : 720) * mult,
      endFreq: 420 * mult,
      type: "triangle",
      start: 0.03,
      duration: 0.085,
      gain: 0.11,
    });
  }

  playPromote(color = "white") {
    const ctx = this._ensureContext();
    if (!ctx) return;
    this.playMove(color);
    // Warm Moroccan-inspired coronation arpeggio (D4 - F#4 - A4 - D5)
    const notes = [293.66, 369.99, 440.0, 587.33];
    notes.forEach((freq, idx) => {
      this._tone(ctx, {
        freq,
        type: "triangle",
        start: 0.05 + idx * 0.065,
        duration: 0.24,
        gain: 0.095,
      });
    });
  }

  playTaunt() {
    const ctx = this._ensureContext();
    if (!ctx) return;
    // Moroccan mint-tea glass clink ("kass d'atay")
    this._tone(ctx, { freq: 2180, type: "sine", duration: 0.14, gain: 0.075 });
    this._tone(ctx, { freq: 3290, type: "sine", start: 0.012, duration: 0.11, gain: 0.045 });
  }

  playChat() {
    const ctx = this._ensureContext();
    if (!ctx) return;
    // Friendly, crisp two-tone chat chime (F5 -> A5)
    this._tone(ctx, { freq: 698.46, type: "sine", duration: 0.08, gain: 0.06 });
    this._tone(ctx, { freq: 880.0, type: "sine", start: 0.065, duration: 0.11, gain: 0.065 });
  }

  playWin(iWon = true) {
    const ctx = this._ensureContext();
    if (!ctx) return;
    const seq = iWon
      ? [392.0, 493.88, 587.33, 783.99] // G4 B4 D5 G5
      : [392.0, 349.23, 329.63, 293.66]; // G4 F4 E4 D4
    seq.forEach((freq, idx) => {
      this._tone(ctx, {
        freq,
        type: "triangle",
        start: idx * 0.09,
        duration: idx === seq.length - 1 ? 0.36 : 0.16,
        gain: iWon ? 0.11 : 0.08,
      });
    });
  }

  playIllegal() {
    const ctx = this._ensureContext();
    if (!ctx) return;
    this._tone(ctx, { freq: 165, endFreq: 130, type: "sawtooth", duration: 0.07, gain: 0.055 });
  }
}
