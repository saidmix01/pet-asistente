/**
 * Audio Engine — ambient contextual sounds.
 * Starts with inline beep (instant), upgrades to mp3 when loaded.
 */

function makeBeep(freq, dur, vol = 0.15) {
  const sr = 44100, s = Math.floor(sr * dur)
  const b = new ArrayBuffer(44 + s * 2)
  const v = new DataView(b)
  const w = (o, str) => { for (let i = 0; i < str.length; i++) v.setUint8(o + i, str.charCodeAt(i)) }
  w(0, 'RIFF'); v.setUint32(4, 36 + s * 2, true); w(8, 'WAVE')
  w(12, 'fmt '); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true)
  v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  w(36, 'data'); v.setUint32(40, s * 2, true)
  for (let i = 0; i < s; i++) {
    const fade = 1 - i / s
    const sample = Math.sin(2 * Math.PI * freq * i / sr) * vol * fade
    v.setInt16(44 + i * 2, sample * 32767, true)
  }
  const bytes = new Uint8Array(b)
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return 'data:audio/wav;base64,' + btoa(bin)
}

function makeMulti(...notes) {
  const sr = 44100
  let total = 0
  const parts = notes.map(([f, d, vol]) => {
    const s = Math.floor(sr * d); total += s
    return { freq: f, samples: s, vol: vol || 0.12 }
  })
  const b = new ArrayBuffer(44 + total * 2)
  const v = new DataView(b)
  const w = (o, str) => { for (let i = 0; i < str.length; i++) v.setUint8(o + i, str.charCodeAt(i)) }
  w(0, 'RIFF'); v.setUint32(4, 36 + total * 2, true); w(8, 'WAVE')
  w(12, 'fmt '); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true)
  v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  w(36, 'data'); v.setUint32(40, total * 2, true)
  let off = 44
  for (const p of parts) {
    for (let i = 0; i < p.samples; i++) {
      const fade = 1 - i / p.samples
      const sample = Math.sin(2 * Math.PI * p.freq * i / sr) * p.vol * fade
      v.setInt16(off, sample * 32767, true)
      off += 2
    }
  }
  const bytes = new Uint8Array(b)
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return 'data:audio/wav;base64,' + btoa(bin)
}

const SOUNDS = {
  ladrido: { fallback: makeMulti([400,0.08,0.15],[600,0.06,0.12],[550,0.04,0.1]), cooldown: 45000, chance: 0.6 },
  ronquido: { fallback: makeBeep(110, 0.6, 0.08), cooldown: 300000, chance: 1.0 },
  alerta: { fallback: makeMulti([880,0.15,0.12],[0,0.05,0],[880,0.15,0.12]), cooldown: 60000, chance: 1.0 },
}

class AudioEngine {
  constructor() {
    this._els = {}
    this._last = {}
    this._playing = false
    this._muted = false
    this._vol = 0.25
    this._quiet = false
  }

  init() {
    for (const [name, cfg] of Object.entries(SOUNDS)) {
      // Always start with fallback beep (instant)
      const el = new Audio(cfg.fallback)
      el.preload = 'auto'
      el.volume = this._vol
      this._els[name] = el

      // Try to load mp3 in background — swap when ready
      const mp3 = new Audio(`/sounds/${name}.mp3`)
      mp3.preload = 'auto'
      mp3.addEventListener('canplaythrough', () => {
        mp3.volume = this._vol
        this._els[name] = mp3
        console.log(`[Audio] ${name} → mp3`)
      }, { once: true })
    }
    console.log('[Audio] Ready')
  }

  play(name) {
    if (this._quiet || this._muted || this._playing) return
    const cfg = SOUNDS[name]
    if (!cfg) return
    if (Date.now() - (this._last[name] || 0) < cfg.cooldown) return
    if (Math.random() > cfg.chance) return

    const el = this._els[name]
    if (!el) return

    this._playing = true
    this._last[name] = Date.now()

    try {
      el.currentTime = 0
      el.volume = this._vol
      el.play().then(() => {
        el.onended = () => { this._playing = false }
      }).catch(() => { this._playing = false })
    } catch { this._playing = false }

    setTimeout(() => { this._playing = false }, 2000)
  }

  setVolume(v) { this._vol = Math.max(0, Math.min(1, v)) }
  mute() { this._muted = true }
  unmute() { this._muted = false }
  get isMuted() { return this._muted }
  enableQuietMode() { this._quiet = true }
  disableQuietMode() { this._quiet = false }
}

export { AudioEngine }
export default AudioEngine
