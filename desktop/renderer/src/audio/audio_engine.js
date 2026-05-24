/**
 * Audio Engine — ambient contextual sounds for the pet assistant.
 *
 * Loads sound files and plays them based on WebSocket events.
 * Anti-spam, volume control, and quiet mode built in.
 *
 * Sound files expected at: desktop/renderer/public/sounds/
 *   - ladrido.mp3 (bark)
 *   - ronquido.mp3 (snore)
 *   - alerta.mp3  (alert)
 */

// ── Constants ──────────────────────────────────────────────
const SOUNDS_DIR = '/sounds/'

const SOUND_CONFIG = {
  ladrido: { file: 'ladrido.mp3', cooldown: 45000, volume: 0.25, chance: 0.6 },
  ronquido: { file: 'ronquido.mp3', cooldown: 300000, volume: 0.2, chance: 1.0 },
  alerta:  { file: 'alerta.mp3',  cooldown: 60000,  volume: 0.25, chance: 1.0 },
}

// ── Audio Engine ───────────────────────────────────────────
class AudioEngine {
  constructor() {
    this._sounds = {}
    this._lastPlayed = {}
    this._isPlaying = false
    this._isMuted = false
    this._volume = 0.25
    this._quietMode = false
    this._initialized = false
  }

  // ── Initialization ──────────────────────────────────────

  init() {
    if (this._initialized) return

    for (const [name, config] of Object.entries(SOUND_CONFIG)) {
      try {
        const audio = new Audio()
        audio.preload = 'auto'
        audio.src = SOUNDS_DIR + config.file
        audio.volume = config.volume * this._volume
        this._sounds[name] = audio
      } catch (e) {
        console.warn(`[Audio] Failed to load ${name}:`, e.message)
      }
    }

    this._initialized = true
    console.log('[Audio] Engine initialized with sounds:', Object.keys(this._sounds).join(', '))
  }

  // ── Playback ─────────────────────────────────────────────

  play(soundName) {
    if (this._quietMode) return
    if (this._isMuted) return
    if (this._isPlaying) return  // no overlapping

    const config = SOUND_CONFIG[soundName]
    if (!config) {
      console.warn(`[Audio] Unknown sound: ${soundName}`)
      return
    }

    // Cooldown check
    const last = this._lastPlayed[soundName] || 0
    if (Date.now() - last < config.cooldown) return

    // Random chance
    if (Math.random() > config.chance) return

    const audio = this._sounds[soundName]
    if (!audio) return

    // Reset and play
    audio.currentTime = 0
    audio.volume = config.volume * this._volume
    this._isPlaying = true
    this._lastPlayed[soundName] = Date.now()

    audio.play().then(() => {
      audio.onended = () => {
        this._isPlaying = false
      }
    }).catch((e) => {
      // Autoplay may be blocked — ignore silently
      this._isPlaying = false
    })
  }

  // ── Volume control ───────────────────────────────────────

  setVolume(value) {
    this._volume = Math.max(0, Math.min(1, value))
    for (const audio of Object.values(this._sounds)) {
      audio.volume = this._volume * 0.25
    }
  }

  mute() {
    this._isMuted = true
  }

  unmute() {
    this._isMuted = false
  }

  get isMuted() { return this._isMuted }

  // ── Quiet mode ──────────────────────────────────────────

  enableQuietMode() { this._quietMode = true }
  disableQuietMode() { this._quietMode = false }
  get quietMode() { return this._quietMode }
}


// ── WebSocket event listener integration ───────────────────
function connectAudioToEvents(audioEngine, wsUrl = 'ws://127.0.0.1:8000/ws/state') {
  audioEngine.init()

  let ws = null
  let reconnectTimer = null

  function connect() {
    if (ws) try { ws.close() } catch {}
    ws = new WebSocket(wsUrl)

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        handleEvent(audioEngine, msg)
      } catch {}
    }

    ws.onclose = () => {
      reconnectTimer = setTimeout(connect, 5000)
    }

    ws.onerror = () => { ws?.close() }
  }

  connect()
  return () => {
    if (ws) ws.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  }
}

function handleEvent(audioEngine, msg) {
  const type = msg.type
  const data = msg.data || {}

  switch (type) {
    case 'thought':
      // Ambient thoughts may trigger subtle sounds
      const thoughtType = data.thought?.type
      if (thoughtType === 'focus' || thoughtType === 'encouragement') {
        audioEngine.play('ladrido')
      }
      break

    case 'mood_change':
      if (data.mood === 'excited') {
        audioEngine.play('ladrido')
      }
      break

    case 'event':
      const eventType = data.event || ''
      const eventData = data.data || {}

      if (eventType === 'task.completed') {
        audioEngine.play('ladrido')
      }

      if (eventType === 'clickup.mention' || eventType === 'deadline.approaching') {
        audioEngine.play('alerta')
      }

      if (eventType === 'behavior.request') {
        const behavior = eventData.behavior
        if (behavior === 'sleep') {
          audioEngine.play('ronquido')
        }
        if (behavior === 'wake') {
          // Wake up — no sound needed
        }
      }
      break

    case 'behavior.request':
      if (data.behavior === 'sleep') {
        audioEngine.play('ronquido')
      }
      break
  }
}


// ── Export ─────────────────────────────────────────────────
export { AudioEngine, connectAudioToEvents }
export default AudioEngine
