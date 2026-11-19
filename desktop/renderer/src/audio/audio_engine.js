/**
 * Audio Engine — ambient contextual sounds (ladrido, alerta, ronquido, snack, pop).
 * Uses real WAV sound assets with automatic fallback to Web Audio API synthesis.
 */

const SOUND_CONFIGS = {
  ladrido: { cooldown: 1000 },
  alerta: { cooldown: 1800 },
  ronquido: { cooldown: 4000 },
  snack: { cooldown: 800 },
  pop: { cooldown: 200 },
}

class AudioEngine {
  constructor() {
    this._els = {}
    this._last = {}
    this._muted = false
    this._vol = 0.85
    this._quiet = false
    this._ctx = null
  }

  getAudioContext() {
    if (!this._ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext
      if (AudioCtx) {
        this._ctx = new AudioCtx()
      }
    }
    if (this._ctx && this._ctx.state === 'suspended') {
      this._ctx.resume().catch(() => {})
    }
    return this._ctx
  }

  init() {
    // Pre-load audio elements with multiple path fallbacks
    for (const name of Object.keys(SOUND_CONFIGS)) {
      const candidatePaths = [
        `./sounds/${name}.wav`,
        `/sounds/${name}.wav`,
        `sounds/${name}.wav`,
        `../assets/sounds/${name}.wav`,
      ]

      const audio = new Audio()
      audio.preload = 'auto'
      audio.volume = this._vol

      let pathIndex = 0
      const tryNextPath = () => {
        if (pathIndex < candidatePaths.length) {
          audio.src = candidatePaths[pathIndex++]
          audio.load()
        }
      }

      audio.addEventListener('error', () => {
        tryNextPath()
      })

      tryNextPath()
      this._els[name] = audio
    }

    // Auto-resume AudioContext on first user interaction
    const unlock = () => {
      this.getAudioContext()
      window.removeEventListener('click', unlock)
      window.removeEventListener('keydown', unlock)
      window.removeEventListener('touchstart', unlock)
    }
    window.addEventListener('click', unlock, { once: true })
    window.addEventListener('keydown', unlock, { once: true })
    window.addEventListener('touchstart', unlock, { once: true })

    console.log('[Audio] AudioEngine ready with assets and WebAudio fallback')
  }

  play(name) {
    if (this._quiet || this._muted) return
    const cfg = SOUND_CONFIGS[name] || { cooldown: 1000 }
    const now = Date.now()
    if (now - (this._last[name] || 0) < cfg.cooldown) return

    this._last[name] = now
    this._executePlay(name)
  }

  forcePlay(name) {
    if (this._muted) return
    this._last[name] = Date.now()
    this._executePlay(name)
  }

  _executePlay(name) {
    const audio = this._els[name]
    let handled = false

    if (audio && audio.src && audio.readyState >= 2) {
      try {
        audio.currentTime = 0
        audio.volume = this._vol
        const promise = audio.play()
        if (promise !== undefined) {
          promise.catch(() => {
            this._synthesize(name)
          })
          handled = true
        }
      } catch {
        // Fallback below
      }
    }

    if (!handled) {
      this._synthesize(name)
    }
  }

  _synthesize(name) {
    try {
      const ctx = this.getAudioContext()
      if (!ctx) return

      const now = ctx.currentTime
      const vol = this._vol

      if (name === 'ladrido') {
        // Double bark: "Arf-arf!"
        this._synthBark(ctx, now, 0.11, 720, 310, vol * 0.9)
        this._synthBark(ctx, now + 0.16, 0.14, 780, 260, vol * 1.0)
      } else if (name === 'alerta') {
        // 4-note ascending chime (C5, E5, G5, C6)
        const notes = [
          [0.00, 523.25, 0.45],
          [0.09, 659.25, 0.55],
          [0.18, 783.99, 0.65],
          [0.27, 1046.50, 0.75],
        ]
        for (const [offset, freq, noteVol] of notes) {
          const osc = ctx.createOscillator()
          const gain = ctx.createGain()
          osc.type = 'sine'
          osc.frequency.setValueAtTime(freq, now + offset)
          gain.gain.setValueAtTime(vol * noteVol, now + offset)
          gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.35)
          osc.connect(gain)
          gain.connect(ctx.destination)
          osc.start(now + offset)
          osc.stop(now + offset + 0.36)
        }
      } else if (name === 'ronquido') {
        // Low gentle snore
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sawtooth'
        osc.frequency.setValueAtTime(70, now)
        osc.frequency.linearRampToValueAtTime(85, now + 0.5)
        osc.frequency.linearRampToValueAtTime(60, now + 1.2)
        gain.gain.setValueAtTime(0.001, now)
        gain.gain.linearRampToValueAtTime(vol * 0.4, now + 0.5)
        gain.gain.linearRampToValueAtTime(0.001, now + 1.3)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now)
        osc.stop(now + 1.35)
      } else if (name === 'snack') {
        // Crunch / munch
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'triangle'
        osc.frequency.setValueAtTime(500, now)
        osc.frequency.exponentialRampToValueAtTime(900, now + 0.2)
        gain.gain.setValueAtTime(vol * 0.7, now)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now)
        osc.stop(now + 0.23)
      } else {
        // Pop / default
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.setValueAtTime(250, now)
        osc.frequency.exponentialRampToValueAtTime(800, now + 0.05)
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.1)
        gain.gain.setValueAtTime(vol * 0.8, now)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.11)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now)
        osc.stop(now + 0.12)
      }
    } catch (e) {
      console.warn('[Audio] Synthesis error:', e)
    }
  }

  _synthBark(ctx, startTime, dur, fStart, fEnd, vol) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sawtooth'
    osc.frequency.setValueAtTime(fStart, startTime)
    osc.frequency.exponentialRampToValueAtTime(fEnd, startTime + dur)

    gain.gain.setValueAtTime(0.01, startTime)
    gain.gain.linearRampToValueAtTime(vol, startTime + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + dur)

    const filter = ctx.createBiquadFilter()
    filter.type = 'bandpass'
    filter.frequency.setValueAtTime(850, startTime)
    filter.Q.setValueAtTime(1.8, startTime)

    osc.connect(filter)
    filter.connect(gain)
    gain.connect(ctx.destination)

    osc.start(startTime)
    osc.stop(startTime + dur + 0.02)
  }

  setVolume(v) {
    this._vol = Math.max(0, Math.min(1, v))
    for (const audio of Object.values(this._els)) {
      try { audio.volume = this._vol } catch {}
    }
  }

  get volume() { return this._vol }
  mute() { this._muted = true }
  unmute() { this._muted = false }
  get isMuted() { return this._muted }
  enableQuietMode() { this._quiet = true }
  disableQuietMode() { this._quiet = false }
}

export { AudioEngine }
export default AudioEngine
