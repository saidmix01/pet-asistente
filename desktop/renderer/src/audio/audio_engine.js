/**
 * Audio Engine — ambient contextual sounds for the pet assistant.
 *
 * Tries to load mp3 files from /sounds/ (Vite public dir).
 * Falls back to base64 WAV beeps if mp3 not available.
 */

// ── Generate WAV beep as base64 data URI ──────────────────
function makeBeep(freq, duration, volume = 0.15) {
  const sampleRate = 44100
  const samples = Math.floor(sampleRate * duration)
  const buffer = new ArrayBuffer(44 + samples * 2)
  const view = new DataView(buffer)

  const writeStr = (off, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + samples * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, samples * 2, true)

  for (let i = 0; i < samples; i++) {
    const t = i / sampleRate
    const fade = 1 - (i / samples)
    const sample = Math.sin(2 * Math.PI * freq * t) * volume * fade
    view.setInt16(44 + i * 2, sample * 32767, true)
  }

  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return 'data:audio/wav;base64,' + btoa(binary)
}

function makeMultiBeep(...notes) {
  const sampleRate = 44100
  let totalSamples = 0
  const parts = notes.map(([freq, dur, vol]) => {
    const s = Math.floor(sampleRate * dur)
    totalSamples += s
    return { freq, samples: s, vol: vol || 0.12 }
  })

  const buffer = new ArrayBuffer(44 + totalSamples * 2)
  const view = new DataView(buffer)

  const writeStr = (off, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + totalSamples * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, totalSamples * 2, true)

  let offset = 44
  for (const p of parts) {
    for (let i = 0; i < p.samples; i++) {
      const t = i / sampleRate
      const fade = 1 - (i / p.samples)
      const sample = Math.sin(2 * Math.PI * p.freq * t) * p.vol * fade
      view.setInt16(offset, sample * 32767, true)
      offset += 2
    }
  }

  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return 'data:audio/wav;base64,' + btoa(binary)
}

// Fallback sounds (inline WAV beeps)
const FALLBACKS = {
  ladrido: makeMultiBeep([400, 0.08, 0.15], [600, 0.06, 0.12], [550, 0.04, 0.1]),
  ronquido: makeBeep(110, 0.6, 0.08),
  alerta: makeMultiBeep([880, 0.15, 0.12], [0, 0.05, 0], [880, 0.15, 0.12]),
}

const COOLDOWNS = {
  ladrido: 45000,
  ronquido: 300000,
  alerta: 60000,
}

const CHANCES = {
  ladrido: 0.6,
  ronquido: 1.0,
  alerta: 1.0,
}


class AudioEngine {
  constructor() {
    this._lastPlayed = {}
    this._isPlaying = false
    this._isMuted = false
    this._volume = 0.25
    this._quietMode = false
    this._initialized = false
    this._audioElements = {}
  }

  init() {
    if (this._initialized) return

    const soundNames = ['ladrido', 'ronquido', 'alerta']

    for (const name of soundNames) {
      let audio = null

      // Try loading mp3 from /sounds/
      try {
        const mp3 = new Audio(`/sounds/${name}.mp3`)
        mp3.preload = 'auto'
        // Quick test if it loads
        const canPlay = new Promise((resolve) => {
          mp3.addEventListener('canplaythrough', () => resolve(true), { once: true })
          mp3.addEventListener('error', () => resolve(false), { once: true })
          setTimeout(() => resolve(false), 2000) // 2s timeout
        })
        // We don't await here — just try both
        audio = mp3
      } catch (e) {
        audio = null
      }

      if (audio) {
        audio.volume = this._volume
        this._audioElements[name] = audio
      } else {
        // Fallback to inline beep
        const fallback = new Audio(FALLBACKS[name])
        fallback.preload = 'auto'
        fallback.volume = this._volume
        this._audioElements[name] = fallback
      }
    }

    this._initialized = true
    const sources = soundNames.map(n => {
      const src = this._audioElements[n]?.src || ''
      return src.startsWith('data:') ? `${n}(inline)` : `${n}(mp3)`
    })
    console.log(`[Audio] Ready: ${sources.join(', ')}`)
  }

  play(soundName) {
    if (this._quietMode) return
    if (this._isMuted) return
    if (this._isPlaying) return

    const audio = this._audioElements[soundName]
    if (!audio) return

    // Cooldown
    const last = this._lastPlayed[soundName] || 0
    if (Date.now() - last < (COOLDOWNS[soundName] || 60000)) return

    // Random chance
    if (Math.random() > (CHANCES[soundName] || 1.0)) return

    this._isPlaying = true
    this._lastPlayed[soundName] = Date.now()

    try {
      audio.currentTime = 0
      audio.volume = this._volume
      audio.play().then(() => {
        audio.onended = () => { this._isPlaying = false }
      }).catch(() => {
        this._isPlaying = false
      })
    } catch {
      this._isPlaying = false
    }

    setTimeout(() => { this._isPlaying = false }, 2000)
  }

  setVolume(v) { this._volume = Math.max(0, Math.min(1, v)) }
  mute() { this._isMuted = true }
  unmute() { this._isMuted = false }
  get isMuted() { return this._isMuted }
  enableQuietMode() { this._quietMode = true }
  disableQuietMode() { this._quietMode = false }
}


export { AudioEngine }
export default AudioEngine
