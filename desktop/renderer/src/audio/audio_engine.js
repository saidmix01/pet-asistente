/**
 * Audio Engine — ambient contextual sounds for the pet assistant.
 *
 * Uses Web Audio API for programmatic beeps as fallback,
 * tries to load real mp3 files if available.
 */

// ── Constants ──────────────────────────────────────────────
const SOUND_PATHS = [
  '/sounds/',                    // Vite dev + build
  '../../sounds/',              // Relative from dist
  '../../../Desktop/sounds/',   // User's Desktop
]

const SOUND_CONFIG = {
  ladrido: {
    file: 'ladrido.mp3',
    cooldown: 45000,
    chance: 0.6,
    fallbackFreq: 600,
    fallbackDuration: 0.15,
  },
  ronquido: {
    file: 'ronquido.mp3',
    cooldown: 300000,
    chance: 1.0,
    fallbackFreq: 120,
    fallbackDuration: 0.8,
  },
  alerta: {
    file: 'alerta.mp3',
    cooldown: 60000,
    chance: 1.0,
    fallbackFreq: 880,
    fallbackDuration: 0.3,
  },
}

// ── Audio Engine ───────────────────────────────────────────
class AudioEngine {
  constructor() {
    this._audioCtx = null
    this._sounds = {}
    this._lastPlayed = {}
    this._isPlaying = false
    this._isMuted = false
    this._volume = 0.25
    this._quietMode = false
    this._initialized = false
    this._useFallback = false
    this._debug = []
  }

  // ── Initialization ──────────────────────────────────────

  init() {
    if (this._initialized) return

    // Try to initialize Web Audio API (for fallback sounds)
    try {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      // Try to resume immediately
      if (this._audioCtx.state === 'suspended') {
        this._audioCtx.resume()
      }
      // Also resume on user interaction
      const resume = () => {
        if (this._audioCtx?.state === 'suspended') {
          this._audioCtx.resume()
        }
        document.removeEventListener('click', resume)
        document.removeEventListener('keydown', resume)
      }
      document.addEventListener('click', resume)
      document.addEventListener('keydown', resume)
    } catch (e) {
      this._debug.push(`AudioContext: ${e.message}`)
    }

    // Try loading mp3 files from multiple paths
    for (const [name, config] of Object.entries(SOUND_CONFIG)) {
      let loaded = false
      for (const basePath of SOUND_PATHS) {
        const fullPath = basePath + config.file
        try {
          const audio = new Audio()
          audio.preload = 'auto'
          audio.src = fullPath
          // Test if it loads
          audio.addEventListener('canplaythrough', () => {
            this._debug.push(`${name}: loaded from ${fullPath}`)
          }, { once: true })
          audio.addEventListener('error', () => {
            // Try next path silently
          }, { once: true })
          this._sounds[name] = audio
          loaded = true
          break  // Found a working path
        } catch (e) {
          continue
        }
      }
      if (!loaded) {
        this._debug.push(`${name}: no mp3 found, using fallback`)
      }
    }

    // Always use fallback for reliability (mp3 is bonus)
    this._useFallback = true
    this._initialized = true
    console.log('[Audio] Engine initialized', this._debug.length ? `(${this._debug.length} messages)` : '')
  }

  // ── Playback ─────────────────────────────────────────────

  play(soundName) {
    if (this._quietMode) { console.log('[Audio] quiet mode, skipping'); return }
    if (this._isMuted) { console.log('[Audio] muted, skipping'); return }
    if (this._isPlaying) { console.log('[Audio] already playing, skipping'); return }

    const config = SOUND_CONFIG[soundName]
    if (!config) {
      console.warn(`[Audio] Unknown sound: ${soundName}`)
      return
    }

    // Cooldown check
    const last = this._lastPlayed[soundName] || 0
    if (Date.now() - last < config.cooldown) {
      console.log(`[Audio] ${soundName} on cooldown`)
      return
    }

    // Random chance
    if (Math.random() > config.chance) {
      console.log(`[Audio] ${soundName} random chance missed`)
      return
    }

    this._isPlaying = true
    this._lastPlayed[soundName] = Date.now()
    console.log(`[Audio] Playing ${soundName}`)

    // Try mp3 first
    const audio = this._sounds[soundName]
    if (audio && !this._useFallback) {
      audio.currentTime = 0
      audio.volume = config.fallbackDuration * 0.3
      audio.play().then(() => {
        audio.onended = () => { this._isPlaying = false }
      }).catch(() => {
        this._playFallback(config)
      })
    } else {
      this._playFallback(config)
    }
  }

  _playFallback(config) {
    if (!this._audioCtx) {
      this._isPlaying = false
      return
    }

    try {
      // Ensure AudioContext is running
      if (this._audioCtx.state === 'suspended') {
        this._audioCtx.resume()
      }

      const osc = this._audioCtx.createOscillator()
      const gain = this._audioCtx.createGain()

      osc.type = 'sine'
      osc.frequency.value = config.fallbackFreq
      gain.gain.value = config.fallbackDuration > 0.5 ? 0.08 : 0.12

      osc.connect(gain)
      gain.connect(this._audioCtx.destination)

      const duration = Math.max(config.fallbackDuration, 0.2)
      osc.start()
      gain.gain.exponentialRampToValueAtTime(0.001, this._audioCtx.currentTime + duration)
      osc.stop(this._audioCtx.currentTime + duration)

      osc.onended = () => { this._isPlaying = false }
      // Safety timeout in case onended doesn't fire
      setTimeout(() => { this._isPlaying = false }, (duration * 1000) + 200)
    } catch (e) {
      console.warn('[Audio] Fallback playback failed:', e.message)
      this._isPlaying = false
    }
  }

  // ── Volume control ───────────────────────────────────────

  setVolume(value) { this._volume = Math.max(0, Math.min(1, value)) }
  mute() { this._isMuted = true }
  unmute() { this._isMuted = false }
  get isMuted() { return this._isMuted }

  // ── Quiet mode ──────────────────────────────────────────

  enableQuietMode() { this._quietMode = true }
  disableQuietMode() { this._quietMode = false }
  get quietMode() { return this._quietMode }
}


// ── Export ─────────────────────────────────────────────────
export { AudioEngine }
export default AudioEngine
