import { useEffect, useRef, useState } from 'react'
import { AudioEngine } from './audio/audio_engine.js'
import { VoiceRecorder } from './audio/voice_recorder.js'

const api = typeof window !== 'undefined' ? window.pet : null
const useCanvasMove = Boolean(!api || api.useCanvasMove)

const SPRITE_URL = './assets/pugasset-grid.png'
const SHEET = {
  width: 800, height: 512,
  frameWidth: 64, frameHeight: 64,
  offsetX: 95, offsetY: 0,
}
const WINDOW_W = 320

// ── Animation definitions ──────────────────────────────────
const ANIMS = {
  jump:     { row: 0, frames: 11, msPerFrame: 80,  speed: 7  },
  idle:     { row: 1, frames: 5,  msPerFrame: 150, speed: 0  },
  idle2:    { row: 2, frames: 5,  msPerFrame: 150, speed: 0  },
  sit:      { row: 3, frames: 9,  msPerFrame: 120, speed: 0  },
  walk:     { row: 4, frames: 5,  msPerFrame: 100, speed: 3  },
  run:      { row: 5, frames: 8,  msPerFrame: 70,  speed: 7  },
  sniff:    { row: 6, frames: 8,  msPerFrame: 100, speed: 0  },
  sniffwalk:{ row: 7, frames: 8,  msPerFrame: 100, speed: 3  },
}

const STATE_DURATIONS = {
  jump:     [1000, 3000],
  idle:     [4000, 8000],
  idle2:    [4000, 8000],
  sit:      [2000, 5000],
  walk:     [1500, 4000],
  run:      [1000, 3000],
  sniff:    [2000, 5000],
  sniffwalk:[1500, 4000],
}

const DEFAULT_STATES = ['idle', 'idle2']

// ── WebSocket config ───────────────────────────────────────
const WS_URL = 'ws://127.0.0.1:8000/ws/state'
const RECONNECT_MS = 5000
const OLLAMA_CHAT = 'http://127.0.0.1:11434/api/chat'
const BACKEND_CHAT = 'http://127.0.0.1:8000/ai/chat'

// ── Animaciones periódicas según modo activo ─────────────
const MODE_ANIMS = {
  coding:        [
    { state: 'jump', duration: 1500 },
    { state: 'run',  duration: 2000 },
  ],
  browsing:      [
    { state: 'sniffwalk', duration: 2000 },
    { state: 'sniff',     duration: 2000 },
  ],
  communication: [
    { state: 'walk', duration: 2500 },
    { state: 'sit',  duration: 3000 },
  ],
  reading:       [
    { state: 'sniff', duration: 2000 },
    { state: 'sit',   duration: 3000 },
  ],
  design:        [
    { state: 'sniff', duration: 2000 },
    { state: 'sit',   duration: 3000 },
  ],
}

// ── Speech messages per event ──────────────────────────────
function pick(arr) { return arr[Math.floor(Math.random() * arr.length)] }

const EVENT_SPEECH = {
  'activity.update': (data) => {
    const t = (data?.activity_type || '').toLowerCase()
    const map = {
      coding:        ['A programar 💻', 'Modo código ✨', 'Escribiendo código 🚀'],
      browsing:      ['Navegando 🌐', 'Investigando 🔍'],
      reading:       ['Leyendo 📚', 'Modo lectura 🤓'],
      communication: ['En llamada 💬'],
      design:        ['Diseñando 🎨', 'Modo creativo 🎭'],
    }
    return pick(map[t]) || null
  },
  'activity.switch': () => null,
  'activity.idle': () => null,
}

// ── AI pet thoughts via backend ────────────────────────────
let gConfig = { aiMode: 'antigravity', deepseekToken: '', assistantName: 'Pet', soundMuted: false }
let antigravityAvailable = false
let ollamaAvailable = false
let backendOnline = false

async function loadConfig() {
  if (api?.getConfig) {
    const cfg = await api.getConfig()
    if (cfg) gConfig = { ...gConfig, ...cfg }
  }
  return gConfig
}

async function checkOllama() {
  try {
    const r = await fetch('http://127.0.0.1:8000/ai/status')
    backendOnline = true
    const data = await r.json()
    antigravityAvailable = !!data.antigravity_available
    ollamaAvailable = !!data.ollama_available
    return antigravityAvailable || ollamaAvailable
  } catch {
    backendOnline = false
    return false
  }
}

async function generateThought(activityType) {
  if (!backendOnline) return null  // Don't spam when backend is down
  const mode = gConfig.aiMode || 'antigravity'
  if (mode === 'antigravity' && !antigravityAvailable) return null
  if (mode === 'local' && !ollamaAvailable) return null
  if (mode === 'remote' && !gConfig.deepseekToken) return null
  try {
    const r = await fetch(BACKEND_CHAT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: `¿Qué opinas de que estoy ${activityType || 'trabajando'}?`,
        mode,
        api_token: gConfig.deepseekToken,
      }),
    })
    if (!r.ok) return null
    const d = await r.json()
    return d.response?.trim()?.slice(0, 60) || null
  } catch { return null }
}

function rand(min, max) { return Math.random() * (max - min) + min }

function pickDefault(current) {
  const others = DEFAULT_STATES.filter(s => s !== current)
  return others[Math.floor(Math.random() * others.length)]
}

let gFallbackX = 0
const MAX_STEPS = 4
const STEP_HEIGHT_PX = 65

// ── Main App ───────────────────────────────────────────────
export default function App() {
  const elRef    = useRef(null)
  const bubbleRef = useRef(null)
  const stateRef    = useRef('idle')
  const dirRef      = useRef(1)
  const frameRef    = useRef(0)
  const posRef      = useRef({ x: 0, y: 0 })
  const screenRef   = useRef({ w: 1920, h: 1080 })
  const draggingRef = useRef(false)
  const hoveredRef  = useRef(false)
  const lastPtrRef  = useRef({ x: 0, y: 0 })
  const readyRef    = useRef(false)
  const wasDraggedRef = useRef(false)
  const petClickRef = useRef(null)
  const movingInFlightRef = useRef(false)
  const actionQueueRef = useRef([])
  const targetXRef = useRef(null)

  const [stepLevel, setStepLevel] = useState(0)
  const [showHearts, setShowHearts] = useState(false)
  const [showSnack, setShowSnack] = useState(false)
  const [hasBall, setHasBall] = useState(false)

  const stepLevelRef = useRef(0)
  const jumpArcYRef = useRef(0)
  const petWiggleCountRef = useRef(0)
  const lastWiggleDirRef = useRef(0)
  const lastWiggleTimeRef = useRef(0)
  const activeErrorSnippetRef = useRef(null)
  const audioEngineRef = useRef(null)
  const voiceRecorderRef = useRef(null)

  const jumpMotionRef = useRef({
    active: false,
    type: null,
    totalMs: 1100,
    elapsedMs: 0,
    stepHeightPx: STEP_HEIGHT_PX,
    startLevel: 0,
    targetLevel: 0,
    accumDy: 0,
  })
  const pendingDxRef = useRef(0)
  const pendingDyRef = useRef(0)

  const lastShapeKeyRef = useRef('')
  const lastVisualRef = useRef({ bg: '', transform: '', bubbleTransform: '' })

  const syncWindowShape = () => {
    if (!api?.updateShape || !elRef.current) return
    const rects = []
    const pr = elRef.current.getBoundingClientRect()
    if (pr.width > 0 && pr.height > 0) {
      rects.push({
        x: Math.max(0, Math.floor(pr.left) - 8),
        y: Math.max(0, Math.floor(pr.top) - 34),
        width: Math.ceil(pr.width) + 16,
        height: Math.ceil(pr.height) + 42,
      })
    }
    const bubble = bubbleRef.current
    if (bubble && bubble.classList.contains('show')) {
      const br = bubble.getBoundingClientRect()
      if (br.width > 0 && br.height > 0) {
        rects.push({
          x: Math.max(0, Math.floor(br.left) - 4),
          y: Math.max(0, Math.floor(br.top) - 4),
          width: Math.ceil(br.width) + 8,
          height: Math.ceil(br.height) + 8,
        })
      }
    }
    const key = rects.map(r => `${r.x},${r.y},${r.width},${r.height}`).join('|')
    if (key && key !== lastShapeKeyRef.current) {
      lastShapeKeyRef.current = key
      api.updateShape(rects)
    }
  }

  const applyVisual = () => {
    const el = elRef.current
    if (!el) return
    const anim = ANIMS[stateRef.current]
    const mirrored = dirRef.current < 0
    const offX = useCanvasMove ? posRef.current.x : 0
    const offY = (useCanvasMove ? posRef.current.y : 0) + (jumpArcYRef.current || 0)

    const newBg =
      `${-(SHEET.offsetX + frameRef.current * SHEET.frameWidth)}px ` +
      `${-(SHEET.offsetY + anim.row * SHEET.frameHeight)}px`
    if (newBg !== lastVisualRef.current.bg) {
      lastVisualRef.current.bg = newBg
      el.style.backgroundPosition = newBg
    }

    const newTransform = `translate(${offX}px, ${offY}px) scaleX(${mirrored ? -1 : 1})`
    if (newTransform !== lastVisualRef.current.transform) {
      lastVisualRef.current.transform = newTransform
      el.style.transform = newTransform
    }

    const bubble = bubbleRef.current
    if (bubble) {
      const newBubbleTransform = `translateX(-50%) scaleX(${mirrored ? -1 : 1})`
      if (newBubbleTransform !== lastVisualRef.current.bubbleTransform) {
        lastVisualRef.current.bubbleTransform = newBubbleTransform
        bubble.style.transform = newBubbleTransform
      }
    }
  }

  // First launch check — handled by electron main.js (opens config window)
  useEffect(() => {
    loadConfig()
  }, [])

  useEffect(() => {
    let rafId = null
    let lastTime = 0
    let frameAccum = 0
    let stateTimer = 0
    let lastKnownActivity = 'unknown'
    let aiThoughtInterval = 0
    let overdueCheckInterval = 0
    let mentionsCheckInterval = 0
    let lastOverdueNotified = new Set()
    let lastMentionNotified = new Set()
    let speechTimer = null
    let lastReactedType = ''
    let modeAnimTimer = 30000
    let pollInterval = null
    let lastPolledActivity = ''

    const showSpeech = (text, duration = 4000) => {
      if (!text) return
      const el = bubbleRef.current
      if (!el) return
      el.textContent = text
      el.classList.add('show')
      if (activeErrorSnippetRef.current) {
        el.classList.add('clickable')
      } else {
        el.classList.remove('clickable')
      }
      if (api?.platform === 'linux') requestAnimationFrame(syncWindowShape)
      // Longer text = longer display
      const adjustedDuration = Math.max(duration, text.length * 80)
      if (speechTimer) clearTimeout(speechTimer)
      speechTimer = setTimeout(() => {
        el.classList.remove('show')
        el.classList.remove('clickable')
        activeErrorSnippetRef.current = null
        if (api?.platform === 'linux') requestAnimationFrame(syncWindowShape)
      }, adjustedDuration)
    }

    if (bubbleRef.current) {
      bubbleRef.current.onclick = (e) => {
        e.stopPropagation()
        if (activeErrorSnippetRef.current) {
          const err = activeErrorSnippetRef.current
          activeErrorSnippetRef.current = null
          const el = bubbleRef.current
          if (el) {
            el.classList.remove('clickable')
            el.classList.remove('show')
          }
          if (api?.openChat) {
            api.openChat('chat').then(() => {
              if (api?.backendPost) {
                api.backendPost('/chat/send', {
                  message: `Por favor analiza este error de código y explícame la solución concreta paso a paso:\n\n\`\`\`\n${err.slice(0, 3000)}\n\`\`\``,
                }).catch(() => {})
              }
            }).catch(() => {})
          }
        }
      }
    }

    const stopPetVoiceRecording = async () => {
      const vr = voiceRecorderRef.current
      if (!vr || !vr.isRecording) return
      const wavBlob = vr.stop()
      if (!wavBlob) return

      showSpeech('🤔 Procesando...', 3000)
      audioEngine.play('alerta')

      try {
        const formData = new FormData()
        formData.append('file', wavBlob, 'command.wav')
        const r = await fetch('http://127.0.0.1:8000/voice/command', {
          method: 'POST',
          body: formData,
        })
        const d = await r.json()
        if (d.ok && d.text) {
          showSpeech(`🎙️ "${d.text}"`, 3000)
          setTimeout(() => {
            if (d.response) {
              showSpeech(d.response, 4500)
            }
          }, 3100)
          if (d.intent_matched && d.action && !d.dispatched) {
            runSingleStep(d.action)
          }
        } else {
          showSpeech(d.response || '¿Eh? No te escuché bien 🐾', 3500)
        }
      } catch {
        showSpeech('No pude procesar la voz 😵', 3000)
      }
    }

    const startPetVoiceRecording = async () => {
      let vr = voiceRecorderRef.current
      if (!vr) {
        vr = new VoiceRecorder({
          onAutoStop: () => stopPetVoiceRecording(),
        })
        voiceRecorderRef.current = vr
      }
      try {
        await vr.start()
        forceAnim('sniff', 7000, '🎙️ ¡Te escucho! Habla...')
        audioEngine.play('ladrido')
      } catch (err) {
        showSpeech('Permiso de micrófono no disponible 🎤❌', 3000)
      }
    }

    const forceAnim = (state, duration, speech) => {
      const validState = ANIMS[state] ? state : 'idle'
      stateRef.current = validState
      stateTimer = duration
      frameAccum = 0
      frameRef.current = 0
      if (speech !== undefined && speech !== null) showSpeech(speech, Math.max(3000, duration))
    }

    const computeTargetX = (moveTo) => {
      if (!moveTo) return null
      const sw = screenRef.current.w || 1920
      const boundW = useCanvasMove ? SHEET.frameWidth : WINDOW_W
      const maxX = Math.max(0, sw - boundW)
      if (moveTo === 'left') return 20
      if (moveTo === 'right') return Math.max(0, maxX - 20)
      if (moveTo === 'center') return Math.round(maxX / 2)
      return null
    }

    const triggerJumpStep = (type, speech, sound = 'ladrido', duration = 1200) => {
      const curLvl = stepLevelRef.current
      let targetLvl = curLvl
      let moveType = type
      let totalDy = 0

      if (moveType === 'up') {
        if (curLvl < MAX_STEPS) {
          targetLvl = curLvl + 1
          totalDy = -STEP_HEIGHT_PX
        } else {
          moveType = 'stay'
          targetLvl = curLvl
          totalDy = 0
          if (!speech) speech = '¡Ya estoy en el escalón más alto! 🪜'
        }
      } else if (moveType === 'down') {
        if (curLvl > 0) {
          targetLvl = curLvl - 1
          totalDy = STEP_HEIGHT_PX
        } else {
          moveType = 'stay'
          targetLvl = 0
          totalDy = 0
          if (!speech) speech = '¡Ya estoy en el suelo! 🐾'
        }
      } else if (moveType === 'reset') {
        targetLvl = 0
        const maxFloorY = screenRef.current.maxY || 800
        totalDy = Math.max(0, maxFloorY - posRef.current.y)
      } else {
        moveType = 'stay'
        totalDy = 0
      }

      jumpMotionRef.current = {
        active: true,
        type: moveType,
        totalMs: duration,
        elapsedMs: 0,
        totalDy: totalDy,
        startLevel: curLvl,
        targetLevel: targetLvl,
        accumDy: 0,
      }

      forceAnim('jump', duration, speech)
      if (sound && sound !== 'none') {
        audioEngine.play(sound)
      }
    }

    const runSingleStep = (step) => {
      if (!step) return
      if (typeof step.onExecute === 'function') {
        try { step.onExecute() } catch {}
      }
      let targetX = computeTargetX(step.move_to)
      if (typeof step.target_x === 'number') {
        targetX = step.target_x
      }
      targetXRef.current = targetX

      if (targetX !== null) {
        dirRef.current = targetX >= posRef.current.x ? 1 : -1
      } else if (step.direction === 'left') {
        dirRef.current = -1
      } else if (step.direction === 'right') {
        dirRef.current = 1
      } else if (step.direction === 'flip') {
        dirRef.current = -dirRef.current
      }

      const rawAction = String(step.action || '').toLowerCase()
      if (rawAction === 'step_up' || rawAction === 'jump_up') {
        triggerJumpStep('up', step.speech || '¡Arriba! 🪜', step.sound || 'ladrido', Number(step.duration_ms) || 1200)
        return
      }
      if (rawAction === 'step_down' || rawAction === 'jump_down') {
        triggerJumpStep('down', step.speech || '¡Bajando! 🐾', step.sound || 'none', Number(step.duration_ms) || 1200)
        return
      }
      if (rawAction === 'reset_step') {
        triggerJumpStep('reset', step.speech || '¡Al suelo! 🐾', step.sound || 'none', Number(step.duration_ms) || 1200)
        return
      }
      if (rawAction === 'jump') {
        const jumpMode = step.step || (stepLevelRef.current < MAX_STEPS ? 'up' : 'stay')
        triggerJumpStep(jumpMode, step.speech || (jumpMode === 'up' ? '¡Hop! 🪜' : '¡Boing! 🐾'), step.sound || 'ladrido', Number(step.duration_ms) || 1200)
        return
      }
      if (rawAction === 'climb_window') {
        ;(async () => {
          try {
            const wInfo = api?.backendFetch ? await api.backendFetch('/active-window') : null
            if (wInfo && wInfo.active && typeof wInfo.x === 'number') {
              const sw = screenRef.current.w || 1920
              const targetX = Math.max(30, Math.min(sw - 340, wInfo.x + wInfo.width - 240))
              const targetY = Math.max(30, wInfo.y - 120)
              const curX = posRef.current.x
              const curY = posRef.current.y
              const totalDy = targetY - curY

              dirRef.current = targetX >= curX ? 1 : -1
              targetXRef.current = targetX

              jumpMotionRef.current = {
                active: true,
                type: 'window',
                totalMs: 1400,
                elapsedMs: 0,
                totalDy: totalDy,
                startLevel: stepLevelRef.current,
                targetLevel: 2,
                accumDy: 0,
              }
              const appTitle = wInfo.app || (wInfo.title || 'tu ventana').slice(0, 20)
              forceAnim('jump', 1400, `🪟 ¡Acompañándote en ${appTitle}!`)
              audioEngine.play('ladrido')
              return
            }
          } catch {}
          triggerJumpStep('up', '¡Sube! 🪜', 'ladrido', 1200)
        })()
        return
      }
      if (rawAction === 'fetch_ball') {
        if (api?.launchBall) {
          api.launchBall().catch(() => {})
        } else {
          setHasBall(true)
          actionQueueRef.current = [
            {
              action: 'run',
              direction: 'right',
              duration_ms: 1600,
              speech: '¡Voy por la pelota! 🎾',
              sound: 'none',
            },
            {
              action: 'sniff',
              duration_ms: 800,
              speech: '¡La tengo! 🐾',
              sound: 'ladrido',
            },
            {
              action: 'run',
              direction: 'left',
              duration_ms: 1600,
              speech: '¡Te la traje de vuelta! 🎾✨',
              sound: 'none',
            },
            {
              action: 'jump',
              direction: 'keep',
              duration_ms: 1400,
              speech: '¿Jugamos otra vez? 🐶',
              sound: 'ladrido',
              onExecute: () => setHasBall(false),
            },
          ]
          const first = actionQueueRef.current.shift()
          runSingleStep(first)
        }
        return
      }
      if (rawAction === 'feed_snack') {
        setShowSnack(true)
        setTimeout(() => setShowSnack(false), 1800)
        actionQueueRef.current = [
          {
            action: 'sniff',
            duration_ms: 1500,
            speech: '¡Ñam ñam ñam! 🍪',
            sound: 'ladrido',
          },
          {
            action: 'jump',
            duration_ms: 1400,
            speech: '¡Gracias por el premio! ⚡ +10 Energía',
            sound: 'ladrido',
          },
        ]
        const first = actionQueueRef.current.shift()
        runSingleStep(first)
        return
      }

      let chosenAction = ANIMS[step.action] ? step.action : 'idle'
      // If AI requested a move_to target but picked a stationary pose, walk there first!
      if (targetX !== null && Math.abs(targetX - posRef.current.x) > 30 && ANIMS[chosenAction].speed === 0) {
        actionQueueRef.current.unshift({
          ...step,
          move_to: null,
          duration_ms: step.duration_ms || 2500,
        })
        chosenAction = 'walk'
      }

      const dur = Number(step.duration_ms) || 2800
      forceAnim(chosenAction, dur, step.speech || undefined)

      if (step.sound && step.sound !== 'none') {
        audioEngine.play(step.sound)
      }
    }

    const executeAiAction = (payload) => {
      if (!payload || typeof payload !== 'object') return
      actionQueueRef.current = []
      const seq = Array.isArray(payload.sequence) ? payload.sequence : []
      if (seq.length > 0) {
        // Carry top-level speech/sound into first step if first step doesn't override it
        const first = {
          ...seq[0],
          speech: seq[0].speech || payload.speech || null,
          sound: seq[0].sound && seq[0].sound !== 'none' ? seq[0].sound : (payload.sound || 'none'),
          move_to: seq[0].move_to || payload.move_to || null,
        }
        actionQueueRef.current = seq.slice(1)
        runSingleStep(first)
      } else {
        runSingleStep(payload)
      }
    }

    const setConnDot = (online) => {
      if (online) showSpeech(`${gConfig.assistantName} conectado 🟢`, 2000)
      else showSpeech(`${gConfig.assistantName} desconectado 🔴`, 4000)
    }

    // ── Audio Engine ──────────────────────────────────────────
    const audioEngine = new AudioEngine()
    audioEngine.init()
    audioEngineRef.current = audioEngine
    const syncMute = (cfg) => {
      if (cfg?.soundMuted) audioEngine.mute()
      else audioEngine.unmute()
    }
    syncMute(gConfig)
    const unsubscribeConfig = api?.onConfigUpdated
      ? api.onConfigUpdated((cfg) => {
          gConfig = { ...gConfig, ...(cfg || {}) }
          syncMute(gConfig)
        })
      : null

    let clickTimer = null
    petClickRef.current = () => {
      if (wasDraggedRef.current) return
      // Double-click detection
      if (clickTimer) {
        clearTimeout(clickTimer)
        clickTimer = null
        // Double click → config window
        if (api?.openConfig) api.openConfig().catch(() => {})
        showSpeech('⚙️ Ajustes', 2000)
        return
      }
      clickTimer = setTimeout(() => {
        clickTimer = null
        // Single click → chat hub
        if (!api?.openChat) {
          showSpeech('Chat no disponible 😴', 2000)
          return
        }
        api.openChat('chat').catch(() => {})
        showSpeech('💬', 1500)
      }, 300)
    }

    // ── Init ───────────────────────────────────────────────
    ;(async () => {
      await loadConfig()
      syncMute(gConfig)
      screenRef.current = { w: window.innerWidth || window.screen.width || 1920, h: window.innerHeight || window.screen.height || 1080, maxY: (window.innerHeight || 1080) - 260 }
      try {
        if (api?.getScreenSize) {
          const s = await api.getScreenSize()
          screenRef.current = { w: s.width ?? 1920, h: s.height ?? 1080, maxY: s.maxY ?? (s.height - 260) }
        }
        if (useCanvasMove) {
          const vw = window.innerWidth || 260
          const vh = window.innerHeight || 170
          screenRef.current = { w: vw, h: vh, maxY: vh - SHEET.frameHeight - 4 }
          posRef.current = {
            x: Math.max(0, Math.round((vw - SHEET.frameWidth) / 2)),
            y: Math.max(0, vh - SHEET.frameHeight - 4),
          }
        } else if (api?.getPosition) {
          const p = await api.getPosition()
          posRef.current = { x: p.x ?? 0, y: p.y ?? 0 }
          const maxFloorY = screenRef.current.maxY || 800
          if (p.y < maxFloorY - 20) {
            const calculatedLevel = Math.min(MAX_STEPS, Math.max(1, Math.round((maxFloorY - p.y) / STEP_HEIGHT_PX)))
            stepLevelRef.current = calculatedLevel
            setStepLevel(calculatedLevel)
          }
        }
      } catch {}
      await checkOllama()
      dirRef.current = Math.random() > 0.5 ? 1 : -1
      const d = STATE_DURATIONS['idle']
      stateTimer = rand(d[0], d[1])
      readyRef.current = true
      lastTime = performance.now()
      applyVisual()
      showSpeech(`👋 Soy ${gConfig.assistantName}`, 2500)
      setTimeout(() => audioEngine.play('ladrido'), 800)
    })()

    // ── Connectivity: use IPC bridge (main process handles WS + HTTP) ──
    // The main process connects to the backend WebSocket and forwards events via IPC
    if (api?.onBackendEvent) {
      api.onBackendEvent((msg) => {
        if (msg.type === 'connected') {
          showSpeech(`${gConfig.assistantName} conectado 🟢`, 2000)
          return
        }
        // Handle audio events
        _handleAudioEvent(audioEngine, msg)

        if (msg.type === 'event' && msg.data?.event) {
          const ev = msg.data.event
          const data = msg.data.data
          if (data?.activity_type) lastKnownActivity = data.activity_type
          const currentType = data?.activity_type || ''
          const isTypeChange = currentType && currentType !== lastReactedType

          if (ev === 'activity.switch' && isTypeChange) {
            lastReactedType = currentType
            const speech = EVENT_SPEECH['activity.update']?.(data)
            const reaction = getReaction(ev, data)
            if (reaction) forceAnim(reaction.state, reaction.duration, speech)
          }
          if (ev === 'activity.update' && isTypeChange) {
            lastReactedType = currentType
            const reaction = getReaction(ev, data)
            const speech = EVENT_SPEECH[ev]?.(data)
            if (reaction) forceAnim(reaction.state, reaction.duration, speech)
          }

          if (ev === 'pet.action' && data) {
            executeAiAction(data)
            return
          }

          // Push notifications
          if (ev === 'clickup.mention') {
            const text = data?.comment_text
              ? `📬 ${data.author}: "${data.comment_text.slice(0, 50)}"`
              : `📬 ${data?.author || 'Alguien'} te escribió en "${(data?.task_name || '').slice(0, 30)}"`
            forceAnim('jump', 6000, text)
            audioEngine.play('alerta')
          }
          if (ev === 'deadline.overdue') {
            forceAnim('jump', 5000, `⏰ ¡Tarea vencida! ${(data?.task_name || '').slice(0, 30)}`)
            audioEngine.play('alerta')
          }
          if (ev === 'pomodoro.completed') {
            forceAnim('jump', 4000, `🍅 ¡Pomodoro #${data?.session_count || 0} completado!`)
            audioEngine.play('ladrido')
          }
          if (ev === 'task.started') {
            forceAnim('run', 3000, `🚀 Empezaste: ${(data?.task_name || '').slice(0, 30)}`)
            audioEngine.play('ladrido')
          }
          if (ev === 'task.completed') {
            forceAnim('jump', 4000, `✅ ¡Completaste: ${(data?.task_name || '').slice(0, 28)}!`)
            audioEngine.play('ladrido')
          }
          if (ev === 'git.commit' && data) {
            forceAnim('jump', 4500, `🚀 ¡Commit en ${data.project}!\n"${(data.message || '').slice(0, 30)}"`)
            audioEngine.play('ladrido')
          }
          if (ev === 'git.uncommitted' && data) {
            forceAnim('sniff', 5000, `💾 ${data.count} cambios sin commit en ${data.project}`)
          }
          if (ev === 'clipboard.error' && data) {
            activeErrorSnippetRef.current = data.full_text || data.snippet
            if (bubbleRef.current) bubbleRef.current.classList.add('clickable')
            forceAnim('sniff', 7000, `🐞 ¿Analizo este error con IA? (Clic aquí)`)
            audioEngine.play('alerta')
          }
          if (ev === 'ball.settled' && data) {
            const targetPetX = typeof data.x === 'number' ? data.x : posRef.current.x
            const originX = typeof data.originX === 'number' ? data.originX : posRef.current.x
            const steps = []
            if (stepLevelRef.current > 0) {
              steps.push({
                action: 'reset_step',
                duration_ms: 600,
                speech: '¡Al suelo a buscarla! 🐾',
                sound: 'none',
              })
            }
            steps.push(
              {
                action: 'run',
                target_x: targetPetX,
                duration_ms: 4500,
                speech: '¡Voy por la pelota a toda velocidad! ⚡🎾',
              },
              {
                action: 'sniff',
                duration_ms: 900,
                speech: '¡La atrapé! 🐾',
                sound: 'ladrido',
                onExecute: () => {
                  if (api?.pickupBall) api.pickupBall().catch(() => {})
                  setHasBall(true)
                },
              },
              {
                action: 'run',
                target_x: originX,
                duration_ms: 4500,
                speech: '¡Te la traje de vuelta! 🎾✨',
              },
              {
                action: 'jump',
                duration_ms: 1500,
                speech: '¡Buen tiro! ¿Jugamos otra vez? 🐶🎾',
                sound: 'ladrido',
                onExecute: () => {
                  setHasBall(false)
                },
              }
            )
            actionQueueRef.current = steps
            const first = actionQueueRef.current.shift()
            runSingleStep(first)
            return
          }
          if (ev === 'voice.start_listening') {
            if (voiceRecorderRef.current?.isRecording) {
              stopPetVoiceRecording()
            } else {
              startPetVoiceRecording()
            }
            return
          }
        }
      })
    }

    // Also use polling as backup for activity state
    pollInterval = setInterval(async () => {
      try {
        const state = api?.backendFetch ? await api.backendFetch('/state') : null
        if (!state) return
        const activity = state.current_activity || ''
        if (activity && activity !== lastPolledActivity && activity !== 'idle') {
          lastPolledActivity = activity
          lastKnownActivity = activity
          // Only trigger animation if IPC bridge hasn't already
          if (activity !== lastReactedType) {
            const data = { activity_type: activity }
            const speech = EVENT_SPEECH['activity.update']?.(data)
            const reaction = getReaction('activity.update', data)
            if (reaction) forceAnim(reaction.state, reaction.duration, speech)
            lastReactedType = activity
          }
        }
      } catch {}
    }, 5000)

    // ── Game loop ──────────────────────────────────────────
    const loop = (now) => {
      if (!readyRef.current) { rafId = requestAnimationFrame(loop); return }
      const dt = Math.min(now - lastTime, 50)
      lastTime = now

      if (!draggingRef.current) {
        const anim = ANIMS[stateRef.current]
        frameAccum += dt
        while (frameAccum >= anim.msPerFrame) {
          frameAccum -= anim.msPerFrame
          const step = stateRef.current === 'sniff' ? 1 : dirRef.current
          frameRef.current = (frameRef.current + step + anim.frames) % anim.frames
        }

        let dy = 0
        if (stateRef.current === 'jump' && jumpMotionRef.current.active) {
          const jm = jumpMotionRef.current
          jm.elapsedMs += dt
          const progress = Math.min(1, jm.elapsedMs / jm.totalMs)

          // 1. Visual jump arc parabola inside window (peaks at progress 0.5, reaching -24px)
          jumpArcYRef.current = -Math.round(Math.sin(progress * Math.PI) * 24)

          // 2. Physical window movement across desktop
          if (jm.totalDy !== 0) {
            const ease = 0.5 - 0.5 * Math.cos(progress * Math.PI)
            const targetOffset = jm.totalDy * ease
            const delta = targetOffset - jm.accumDy
            jm.accumDy += delta
            pendingDyRef.current += delta
          }

          if (progress >= 1) {
            jm.active = false
            jumpArcYRef.current = 0
            stepLevelRef.current = jm.targetLevel
            setStepLevel(jm.targetLevel)
          }
        } else if (jumpArcYRef.current !== 0) {
          jumpArcYRef.current = 0
        }

        if (anim.speed > 0) {
          let stepDx = anim.speed * dirRef.current

          // If AI set a target screen coordinate, steer towards it and stop on arrival
          if (targetXRef.current !== null) {
            const dist = targetXRef.current - posRef.current.x
            if (Math.abs(dist) <= Math.max(12, anim.speed * 2)) {
              targetXRef.current = null
              stateTimer = 0 // Arrived → immediately advance to next queued pose!
              stepDx = 0
            } else {
              dirRef.current = dist > 0 ? 1 : -1
              stepDx = anim.speed * dirRef.current
            }
          }
          pendingDxRef.current += stepDx
        }

        const sendDx = Math.trunc(pendingDxRef.current)
        const sendDy = Math.trunc(pendingDyRef.current)

        if ((sendDx !== 0 || sendDy !== 0) && !movingInFlightRef.current) {
          pendingDxRef.current -= sendDx
          pendingDyRef.current -= sendDy

          let nx = posRef.current.x + sendDx
          let ny = posRef.current.y + sendDy
          const sw = screenRef.current.w
          const boundW = useCanvasMove ? SHEET.frameWidth : WINDOW_W
          if (nx + boundW >= sw) { nx = sw - boundW; dirRef.current = -1; targetXRef.current = null }
          else if (nx <= 0) { nx = 0; dirRef.current = 1; targetXRef.current = null }
          posRef.current = { x: nx, y: ny }

          if (!useCanvasMove && api?.moveBy) {
            movingInFlightRef.current = true
            api.moveBy(sendDx, sendDy).then((res) => {
              if (res && typeof res.x === 'number') {
                posRef.current = { x: res.x, y: res.y }
                if (res.hitLeft) { dirRef.current = 1; targetXRef.current = null }
                else if (res.hitRight) { dirRef.current = -1; targetXRef.current = null }
                if (res.hitBottom) {
                  stepLevelRef.current = 0
                  setStepLevel(0)
                }
              }
            }).catch(() => {}).finally(() => {
              movingInFlightRef.current = false
            })
          }
          else { gFallbackX += sendDx }
        }

        stateTimer -= dt
        if (stateTimer <= 0) {
          if (actionQueueRef.current.length > 0) {
            const nextStep = actionQueueRef.current.shift()
            runSingleStep(nextStep)
          } else {
            targetXRef.current = null
            const next = pickDefault(stateRef.current)
            const nextAnim = ANIMS[next]
            stateRef.current = next
            const d = STATE_DURATIONS[next]
            stateTimer = rand(d[0], d[1])
            frameAccum = 0
            frameRef.current = frameRef.current % nextAnim.frames
          }
        }

        modeAnimTimer -= dt
        if (modeAnimTimer <= 0 && lastReactedType && actionQueueRef.current.length === 0) {
          const pool = MODE_ANIMS[lastReactedType]
          if (pool && !gConfig.aiAutonomy) {
            const a = pool[Math.floor(Math.random() * pool.length)]
            forceAnim(a.state, a.duration, null)
          }
          modeAnimTimer = 25000 + Math.random() * 30000
        }

        // Autonomous AI thoughts & choreography are now orchestrated by backend PetBrain
        aiThoughtInterval = 0

        overdueCheckInterval += dt
        if (overdueCheckInterval > 60000) {
          overdueCheckInterval = 0
          // Overdue tasks are now pushed via WebSocket (deadline.overdue event)
          // No need to poll from frontend
        }

        mentionsCheckInterval += dt
        if (mentionsCheckInterval > 120000) {
          mentionsCheckInterval = 0
          // Mentions are now pushed via WebSocket (clickup.mention event)
          // No need to poll from frontend
        }

        applyVisual()
      }

      const anim = ANIMS[stateRef.current]
      const isDynamic =
        (anim && anim.speed > 0) ||
        jumpMotionRef.current.active ||
        actionQueueRef.current.length > 0 ||
        draggingRef.current ||
        pendingDxRef.current !== 0 ||
        pendingDyRef.current !== 0 ||
        targetXRef.current !== null

      if (isDynamic) {
        rafId = requestAnimationFrame(loop)
      } else {
        rafId = setTimeout(() => {
          rafId = requestAnimationFrame(loop)
        }, 70)
      }
    }
    rafId = requestAnimationFrame(loop)

    const healthInterval = setInterval(() => {
      const nowHour = new Date().getHours()
      if (nowHour >= 21 || nowHour < 6) {
        forceAnim('idle2', 5000, '🌙 Ya es de noche... no te quemes las pestañas.')
      } else {
        const reminders = [
          '💧 ¡Hora de hidratarse! Toma un vaso con agua.',
          '🧘 ¡Pausa activa: estira la espalda y relaja hombros!',
          '👀 Regla 20-20-20: mira a lo lejos 20 segundos.',
        ]
        const r = reminders[Math.floor(Math.random() * reminders.length)]
        forceAnim('sniff', 5000, r)
      }
    }, 45 * 60 * 1000)

    // ── Direct Keyboard Controls for the Pet ────────────────
    const handleKeyDown = (e) => {
      // Don't intercept if typing in an input
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
        return
      }

      const key = e.key.toLowerCase()

      // 1. Voice Command: V
      if (key === 'v') {
        e.preventDefault()
        if (voiceRecorderRef.current?.isRecording) {
          stopPetVoiceRecording()
        } else {
          startPetVoiceRecording()
        }
        return
      }

      // 2. Jump / Step Up: Space, ArrowUp, W
      if (key === ' ' || key === 'arrowup' || key === 'w') {
        e.preventDefault()
        if (e.shiftKey || key === 'arrowup' || key === 'w') {
          runSingleStep({ action: 'step_up', speech: '¡Subo de escalón! 🪜', sound: 'ladrido', mood: 'playful' })
        } else {
          runSingleStep({ action: 'jump', speech: '¡Hop hop! 🐾', sound: 'ladrido', mood: 'playful' })
        }
        return
      }

      // 3. Step Down / Floor: ArrowDown, S
      if (key === 'arrowdown' || key === 's') {
        e.preventDefault()
        if (stepLevelRef.current > 1) {
          runSingleStep({ action: 'step_down', speech: '¡Bajo de escalón! 🪜', sound: 'none', mood: 'calm' })
        } else {
          runSingleStep({ action: 'reset_step', speech: '¡De vuelta al piso! 🐾', sound: 'none', mood: 'calm' })
        }
        return
      }

      // 4. Walk left: ArrowLeft, A
      if (key === 'arrowleft' || key === 'a') {
        e.preventDefault()
        dirRef.current = -1
        forceAnim('walk', 2200, '¡Paseando por aquí! 🐾')
        return
      }

      // 5. Walk right: ArrowRight, D
      if (key === 'arrowright' || key === 'd') {
        e.preventDefault()
        dirRef.current = 1
        forceAnim('walk', 2200, '¡Paseando por acá! 🐾')
        return
      }

      // 6. Tennis Ball Game: P, B, or '2'
      if (key === 'p' || key === 'b' || key === '2') {
        e.preventDefault()
        runSingleStep({ action: 'fetch_ball', speech: '¡A por la pelota! 🎾', sound: 'ladrido', mood: 'playful' })
        return
      }

      // 7. Feed snack: G, F, or '5'
      if (key === 'g' || key === 'f' || key === '5') {
        e.preventDefault()
        runSingleStep({ action: 'feed_snack', speech: '¡Ñam ñam, gracias por la galleta! 🍪', sound: 'ladrido', mood: 'happy' })
        return
      }

      // 8. Open Chat Hub: C, Enter
      if (key === 'c' || key === 'enter') {
        e.preventDefault()
        if (api?.openChat) api.openChat('chat')
        return
      }

      // 9. Sleep / Rest: Z, or '6'
      if (key === 'z' || key === '6') {
        e.preventDefault()
        runSingleStep({ action: 'idle2', duration_ms: 6000, speech: 'Zzz... siesta merecida 😴💤', sound: 'ronquido', mood: 'sleepy' })
        return
      }

      // 10. Sniff / Inspect: H, O
      if (key === 'h' || key === 'o') {
        e.preventDefault()
        runSingleStep({ action: 'sniff', duration_ms: 2500, speech: '¡Sniff sniff! 🔍🐾', sound: 'none', mood: 'curious' })
        return
      }

      // 11. Quick numbers: 1 = jump, 3 = step up, 4 = ground
      if (key === '1') {
        e.preventDefault()
        runSingleStep({ action: 'jump', speech: '¡Hop hop! 🐾', sound: 'ladrido', mood: 'playful' })
        return
      }
      if (key === '3') {
        e.preventDefault()
        runSingleStep({ action: 'step_up', speech: '¡Subo de escalón! 🪜', sound: 'ladrido', mood: 'playful' })
        return
      }
      if (key === '4') {
        e.preventDefault()
        runSingleStep({ action: 'reset_step', speech: '¡Al piso! 🐾', sound: 'none', mood: 'calm' })
        return
      }

      // 12. Controls Hint: ?, K
      if (key === '?' || key === 'k') {
        e.preventDefault()
        showSpeech('⌨️ [Espacio] Saltar | [P] Pelota | [V] Voz | [G] Galleta | [W/S] Escalón | [C] Chat', 5000)
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      if (rafId) {
        cancelAnimationFrame(rafId)
        clearTimeout(rafId)
      }
      if (speechTimer) clearTimeout(speechTimer)
      if (pollInterval) clearInterval(pollInterval)
      if (healthInterval) clearInterval(healthInterval)
      if (unsubscribeConfig) unsubscribeConfig()
      if (voiceRecorderRef.current) voiceRecorderRef.current.cancel()
    }
  }, [])

  // ── Audio event handler (inside useEffect closure) ───────
  function _handleAudioEvent(engine, msg) {
    const type = msg.type
    const data = msg.data || {}

    switch (type) {
      case 'thought':
        const tType = data.thought?.type
        if (tType === 'focus' || tType === 'encouragement') engine.play('ladrido')
        break

      case 'mood_change':
        if (data.mood === 'excited') engine.play('ladrido')
        break

      case 'event':
        const ev = data.event || ''
        const evData = data.data || {}
        if (ev === 'task.completed') engine.play('ladrido')
        if (ev === 'clickup.mention' || ev === 'deadline.approaching') engine.play('alerta')
        if (ev === 'behavior.request' && evData.behavior === 'sleep') engine.play('ronquido')
        break

      case 'behavior.request':
        if (data.behavior === 'sleep') engine.play('ronquido')
        break
    }
  }

  const setInteractive = (val) => { if (!api?.setInteractive) return; api.setInteractive(val).catch(() => {}) }
  const moveWindowBy = (dx, dy) => {
    if (!useCanvasMove && api?.moveBy) { api.moveBy(dx, dy).catch(() => {}); return }
    const maxX = Math.max(0, (window.innerWidth || screenRef.current.w) - SHEET.frameWidth)
    const maxY = Math.max(0, (window.innerHeight || screenRef.current.h) - SHEET.frameHeight)
    const nx = Math.min(maxX, Math.max(0, posRef.current.x + dx))
    const ny = Math.min(maxY, Math.max(0, posRef.current.y + dy))
    gFallbackX = nx
    posRef.current = { x: nx, y: ny }
    applyVisual()
  }
  // ── Mouse tracking for transparent window hit-test ────────
  // On Windows/macOS, forward:true forwards mousemove even when ignoring.
  // On Linux, Electron ignores forward:true, so we report the pet hitbox to
  // the main process which tracks the OS cursor position.
  useEffect(() => {
    const reportHitbox = () => {
      if (!elRef.current || !api?.updateHitbox) return
      const rect = elRef.current.getBoundingClientRect()
      api.updateHitbox({
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      })
    }
    reportHitbox()
    window.addEventListener('resize', reportHitbox)

    let lastMoveCheck = 0
    const onMouseMove = (e) => {
      if (!elRef.current) return
      const now = performance.now()
      if (now - lastMoveCheck < 35) return
      lastMoveCheck = now
      const rect = elRef.current.getBoundingClientRect()
      const over = e.clientX >= rect.left && e.clientX <= rect.right &&
                   e.clientY >= rect.top  && e.clientY <= rect.bottom
      if (over !== hoveredRef.current) {
        hoveredRef.current = over
        if (!draggingRef.current) setInteractive(over)
      }
    }
    document.addEventListener('mousemove', onMouseMove, { passive: true })
    return () => {
      window.removeEventListener('resize', reportHitbox)
      document.removeEventListener('mousemove', onMouseMove)
    }
  }, [])

  const onPointerEnter = () => { hoveredRef.current = true; setInteractive(true) }
  const onPointerLeave = () => { if (!draggingRef.current) setInteractive(false) }

  const onPointerDown = (e) => {
    if (e.button !== 0) return
    window.focus()
    if (elRef.current) elRef.current.focus()
    if (api?.focusWindow) api.focusWindow().catch(() => {})
    draggingRef.current = true
    wasDraggedRef.current = false
    lastPtrRef.current = {
      x: useCanvasMove ? e.clientX : e.screenX,
      y: useCanvasMove ? e.clientY : e.screenY,
    }
    if (api?.setDragging) api.setDragging(true).catch(() => {})
    setInteractive(true); e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e) => {
    if (draggingRef.current) {
      const curX = useCanvasMove ? e.clientX : e.screenX
      const curY = useCanvasMove ? e.clientY : e.screenY
      const dx = curX - lastPtrRef.current.x
      const dy = curY - lastPtrRef.current.y
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) wasDraggedRef.current = true
      lastPtrRef.current = { x: curX, y: curY }
      if (useCanvasMove) {
        moveWindowBy(dx, dy)
      }
    } else {
      // Petting detection: moving cursor back & forth over pet
      const now = performance.now()
      if (now - lastWiggleTimeRef.current > 1200) {
        petWiggleCountRef.current = 0
      }
      lastWiggleTimeRef.current = now
      const currentDir = e.movementX > 0 ? 1 : (e.movementX < 0 ? -1 : 0)
      if (currentDir !== 0 && currentDir !== lastWiggleDirRef.current) {
        lastWiggleDirRef.current = currentDir
        petWiggleCountRef.current += 1
        if (petWiggleCountRef.current >= 4) {
          petWiggleCountRef.current = 0
          setShowHearts(true)
          setTimeout(() => setShowHearts(false), 2000)
          audioEngineRef.current?.play('ronquido')
          const bubble = bubbleRef.current
          if (bubble) {
            bubble.textContent = '¡Awww, caricias! 🥰'
            bubble.classList.add('show')
            setTimeout(() => bubble?.classList.remove('show'), 2500)
          }
        }
      }
    }
  }
  const stopDrag = (e) => {
    if (!draggingRef.current) return; draggingRef.current = false
    if (api?.setDragging) api.setDragging(false).catch(() => {})
    if (!useCanvasMove && api?.getPosition) {
      api.getPosition().then((p) => {
        if (p && typeof p.x === 'number') {
          posRef.current = { x: p.x, y: p.y }
          const maxFloorY = screenRef.current.maxY || 800
          if (p.y >= maxFloorY - 20) {
            stepLevelRef.current = 0
            setStepLevel(0)
          } else {
            const calculatedLevel = Math.min(MAX_STEPS, Math.max(1, Math.round((maxFloorY - p.y) / STEP_HEIGHT_PX)))
            stepLevelRef.current = calculatedLevel
            setStepLevel(calculatedLevel)
          }
        }
      }).catch(() => {})
    }
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
    if (api?.platform === 'linux') requestAnimationFrame(syncWindowShape)
    if (!hoveredRef.current) setInteractive(false)
  }

  return (
      <div className="stage" style={useCanvasMove ? { display: 'block', position: 'relative', paddingBottom: 0 } : undefined}>
        {useCanvasMove && (
          <div className="wayland-drag-handle" title="Arrastra para mover la mascota">
            ⠿
          </div>
        )}
        <div
          ref={elRef}
          className="pet"
          tabIndex={0}
          style={{
            position: useCanvasMove ? 'absolute' : 'relative',
            ...(useCanvasMove ? { left: 0, top: 0 } : {}),
            width: SHEET.frameWidth, height: SHEET.frameHeight,
            transform: 'translate(0px, 0px) scaleX(1)',
            backgroundImage: `url(${SPRITE_URL})`,
            backgroundRepeat: 'no-repeat',
            backgroundPosition: `${-(SHEET.offsetX)}px ${-(SHEET.offsetY)}px`,
            backgroundSize: `${SHEET.width}px ${SHEET.height}px`,
          }}
          onPointerEnter={onPointerEnter}
          onPointerLeave={onPointerLeave}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={stopDrag}
          onPointerCancel={stopDrag}
          onClick={(e) => petClickRef.current?.(e)}
          onContextMenu={(e) => {
            e.preventDefault()
            if (api?.showContextMenu) api.showContextMenu().catch(() => {})
          }}
        >
          <div ref={bubbleRef} className="speech-bubble" />
          {showHearts && (
            <div className="heart-particles">
              <span>❤️</span>
              <span>💖</span>
              <span>✨</span>
            </div>
          )}
          {showSnack && <div className="snack-drop">🍪</div>}
          {hasBall && (
            <div className="tennis-ball-actor" title="¡Pelota!">
              <svg viewBox="0 0 100 100" width="16" height="16">
                <defs>
                  <radialGradient id="feltMouth" cx="35%" cy="30%" r="65%">
                    <stop offset="0%" stop-color="#e2fca8"/>
                    <stop offset="35%" stop-color="#bef264"/>
                    <stop offset="70%" stop-color="#84cc16"/>
                    <stop offset="100%" stop-color="#3f6212"/>
                  </radialGradient>
                </defs>
                <circle cx="50" cy="50" r="46" fill="url(#feltMouth)"/>
                <path d="M 20,24 C 38,36 38,64 20,76" fill="none" stroke="#365314" stroke-width="7" stroke-linecap="round" opacity="0.6"/>
                <path d="M 80,24 C 62,36 62,64 80,76" fill="none" stroke="#365314" stroke-width="7" stroke-linecap="round" opacity="0.6"/>
                <path d="M 20,24 C 38,36 38,64 20,76" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/>
                <path d="M 80,24 C 62,36 62,64 80,76" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/>
              </svg>
            </div>
          )}
          <div
            className={`step-platform ${stepLevel > 0 ? 'visible' : ''}`}
            title={`Escalón nivel ${stepLevel}`}
          >
            <div className="platform-beam" />
            <div className="platform-dots">
              {Array.from({ length: stepLevel }).map((_, i) => (
                <span key={i} className="platform-dot" />
              ))}
            </div>
          </div>
        </div>
      </div>
  )
}

// ── Event → Animation reactions ────────────────────────────
function getReaction(eventType, data) {
  const t = (data?.activity_type || '').toLowerCase()
  const pick = (states) => states[Math.floor(Math.random() * states.length)]

  switch (eventType) {
    case 'activity.switch':
    case 'activity.update':
      if (t === 'coding')
        return pick([
          { state: 'jump',  duration: 1500 },
          { state: 'run',   duration: 2000 },
          { state: 'walk',  duration: 2500 },
        ])
      if (t === 'browsing')
        return pick([
          { state: 'sniffwalk', duration: 2000 },
          { state: 'walk',      duration: 2500 },
        ])
      if (t === 'reading' || t === 'design')
        return pick([
          { state: 'sniff', duration: 2000 },
          { state: 'sit',   duration: 3000 },
        ])
      if (t === 'communication')
        return { state: 'sniff', duration: 2000 }
      return null
    default:
      return null
  }
}
