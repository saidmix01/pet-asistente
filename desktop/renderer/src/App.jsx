import { useEffect, useRef } from 'react'

const api = typeof window !== 'undefined' ? window.pet : null

const SPRITE_URL = '/assets/pugasset-grid.png'
const SHEET = {
  width: 800, height: 512,
  frameWidth: 64, frameHeight: 64,
  offsetX: 95, offsetY: 0,
}
const WINDOW_W = 400

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
const RECONNECT_MS = 3000
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
let gConfig = { aiMode: 'local', deepseekToken: '', assistantName: 'Pet' }
let ollamaAvailable = false

async function loadConfig() {
  if (api?.getConfig) {
    const cfg = await api.getConfig()
    if (cfg) gConfig = cfg
  }
}

async function checkOllama() {
  try {
    const r = await fetch('http://127.0.0.1:8000/ai/status')
    const data = await r.json()
    ollamaAvailable = data.ollama_available
    return ollamaAvailable
  } catch { return false }
}

async function generateThought(activityType) {
  if (!ollamaAvailable && gConfig.aiMode !== 'remote') return null
  try {
    const r = await fetch(BACKEND_CHAT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: `¿Qué opinas de que estoy ${activityType || 'trabajando'}?`,
        mode: gConfig.aiMode,
        api_token: gConfig.deepseekToken,
      }),
    })
    if (!r.ok) return null
    const d = await r.json()
    return d.response?.trim()?.slice(0, 60) || null
  } catch { return null }
}

// ── Overdue tasks check ────────────────────────────────────
async function checkOverdueTasks() {
  try {
    const r = await fetch('http://127.0.0.1:8000/integrations/clickup/tasks')
    if (!r.ok) return []
    const data = await r.json()
    const tasks = data.tasks || []
    const now = Date.now()
    return tasks.filter(t => {
      if (!t.due_date) return false
      const due = parseInt(t.due_date)
      return due < now && t.status?.toLowerCase() !== 'done' && t.status?.toLowerCase() !== 'closed'
    })
  } catch { return [] }
}

// ── ClickUp mentions check ──────────────────────────────────
async function checkNewMentions() {
  try {
    const r = await fetch('http://127.0.0.1:8000/clickup/mentions/check')
    if (!r.ok) return []
    const data = await r.json()
    return data.new_mentions || []
  } catch { return [] }
}

function rand(min, max) { return Math.random() * (max - min) + min }

function pickDefault(current) {
  const others = DEFAULT_STATES.filter(s => s !== current)
  return others[Math.floor(Math.random() * others.length)]
}

let gFallbackX = 0

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

  const applyVisual = () => {
    const el = elRef.current
    if (!el) return
    const anim = ANIMS[stateRef.current]
    const mirrored = dirRef.current < 0
    const offX = api ? 0 : posRef.current.x
    const offY = api ? 0 : posRef.current.y
    el.style.backgroundPosition =
      `${-(SHEET.offsetX + frameRef.current * SHEET.frameWidth)}px ` +
      `${-(SHEET.offsetY + anim.row * SHEET.frameHeight)}px`
    el.style.transform =
      `translate(${offX}px, ${offY}px) scaleX(${mirrored ? -1 : 1})`
    const bubble = bubbleRef.current
    if (bubble) {
      bubble.style.transform = `translateX(-50%) scaleX(${mirrored ? -1 : 1})`
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

    const showSpeech = (text, duration = 4000) => {
      if (!text) return
      const el = bubbleRef.current
      if (!el) return
      el.textContent = text
      el.classList.add('show')
      if (speechTimer) clearTimeout(speechTimer)
      speechTimer = setTimeout(() => { el.classList.remove('show') }, duration)
    }

    const forceAnim = (state, duration, speech) => {
      stateRef.current = state
      stateTimer = duration
      frameAccum = 0
      frameRef.current = 0
      if (speech !== undefined) showSpeech(speech)
    }

    const setConnDot = (online) => {
      if (online) showSpeech(`${gConfig.assistantName} conectado 🟢`, 2000)
      else showSpeech(`${gConfig.assistantName} desconectado 🔴`, 4000)
    }

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
        // Single click → chat
        if (!api?.openChat) {
          showSpeech('Chat no disponible 😴', 2000)
          return
        }
        api.openChat().catch(() => {})
        showSpeech('💬', 1500)
      }, 300)
    }

    // ── WebSocket ──────────────────────────────────────────
    let ws = null
    let reconnectTimer = null

    function connectWs() {
      if (ws) try { ws.close() } catch {}
      ws = new WebSocket(WS_URL)
      ws.onopen = () => { setConnDot(true) }
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
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
          }
        } catch {}
      }
      ws.onclose = () => { setConnDot(false); reconnectTimer = setTimeout(connectWs, RECONNECT_MS) }
      ws.onerror = () => { ws?.close() }
    }

    // ── Init ───────────────────────────────────────────────
    ;(async () => {
      screenRef.current = { w: window.screen.width || 1920, h: window.screen.height || 1080 }
      try {
        if (api?.getPosition) { const p = await api.getPosition(); posRef.current = { x: p.x ?? 0, y: p.y ?? 0 } }
        if (api?.getScreenSize) { const s = await api.getScreenSize(); screenRef.current = { w: s.width ?? 1920, h: s.height ?? 1080 } }
      } catch {}
      await checkOllama()
      dirRef.current = Math.random() > 0.5 ? 1 : -1
      const d = STATE_DURATIONS['idle']
      stateTimer = rand(d[0], d[1])
      readyRef.current = true
      lastTime = performance.now()
      applyVisual()
      showSpeech(`👋 Soy ${gConfig.assistantName}`, 2500)
    })()

    connectWs()

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

        if (anim.speed > 0) {
          const dx = anim.speed * dirRef.current
          let nx = posRef.current.x + dx
          const sw = screenRef.current.w
          if (nx + WINDOW_W >= sw) { nx = sw - WINDOW_W; dirRef.current = -1 }
          else if (nx <= 0) { nx = 0; dirRef.current = 1 }
          posRef.current = { x: nx, y: posRef.current.y }
          if (api?.moveBy) { api.moveBy(dx, 0).catch(() => {}) }
          else { gFallbackX += dx }
        }

        stateTimer -= dt
        if (stateTimer <= 0) {
          const next = pickDefault(stateRef.current)
          const nextAnim = ANIMS[next]
          stateRef.current = next
          const d = STATE_DURATIONS[next]
          stateTimer = rand(d[0], d[1])
          frameAccum = 0
          frameRef.current = frameRef.current % nextAnim.frames
        }

        modeAnimTimer -= dt
        if (modeAnimTimer <= 0 && lastReactedType) {
          const pool = MODE_ANIMS[lastReactedType]
          if (pool) {
            const a = pool[Math.floor(Math.random() * pool.length)]
            forceAnim(a.state, a.duration, null)
          }
          modeAnimTimer = 20000 + Math.random() * 30000
        }

        aiThoughtInterval += dt
        if (aiThoughtInterval > 180000) {
          aiThoughtInterval = 0
          generateThought(lastKnownActivity).then(thought => {
            if (thought) showSpeech(thought, 5000)
          })
        }

        overdueCheckInterval += dt
        if (overdueCheckInterval > 60000) {
          overdueCheckInterval = 0
          checkOverdueTasks().then(tasks => {
            const newOverdue = tasks.filter(t => !lastOverdueNotified.has(t.id))
            if (newOverdue.length > 0) {
              newOverdue.forEach(t => lastOverdueNotified.add(t.id))
              const names = newOverdue.map(t => t.name).slice(0, 2).join(', ')
              forceAnim('jump', 2000, `¡Tarea atrasada! ${names} ⏰`)
            }
          })
        }

        mentionsCheckInterval += dt
        if (mentionsCheckInterval > 120000) {
          mentionsCheckInterval = 0
          checkNewMentions().then(mentions => {
            const newMentions = mentions.filter(m => !lastMentionNotified.has(m.id))
            if (newMentions.length > 0) {
              newMentions.forEach(m => lastMentionNotified.add(m.id))
              const first = newMentions[0]
              const text = first.comment_text
                ? `📬 ${first.author}: "${first.comment_text.slice(0, 40)}"`
                : `📬 ${first.author} comentó en "${first.task_name.slice(0, 25)}"`
              forceAnim('jump', 4000, text)
            }
          })
        }

        applyVisual()
      }

      rafId = requestAnimationFrame(loop)
    }
    rafId = requestAnimationFrame(loop)

    return () => {
      if (rafId) cancelAnimationFrame(rafId)
      if (ws) ws.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (speechTimer) clearTimeout(speechTimer)
    }
  }, [])

  const setInteractive = (val) => { if (!api?.setInteractive) return; api.setInteractive(val).catch(() => {}) }
  const moveWindowBy = (dx, dy) => {
    if (api?.moveBy) { api.moveBy(dx, dy).catch(() => {}); return }
    gFallbackX += dx; posRef.current = { x: gFallbackX, y: posRef.current.y + dy }
  }
  const onPointerEnter = () => { hoveredRef.current = true; setInteractive(true) }
  const onPointerLeave = () => { if (!draggingRef.current) setInteractive(false) }
  const wasDraggedRef = useRef(false)
  const petClickRef = useRef(null)

  const onPointerDown = (e) => {
    if (e.button !== 0) return
    draggingRef.current = true
    wasDraggedRef.current = false
    lastPtrRef.current = { x: e.screenX, y: e.screenY }
    setInteractive(true); e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e) => {
    if (!draggingRef.current) return
    const dx = e.screenX - lastPtrRef.current.x
    const dy = e.screenY - lastPtrRef.current.y
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) wasDraggedRef.current = true
    lastPtrRef.current = { x: e.screenX, y: e.screenY }
    posRef.current = { x: posRef.current.x + dx, y: posRef.current.y + dy }
    moveWindowBy(dx, dy)
  }
  const stopDrag = (e) => {
    if (!draggingRef.current) return; draggingRef.current = false
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
    if (!hoveredRef.current) setInteractive(false)
  }

  return (
      <div className="stage">
        <div
          ref={elRef}
          className="pet"
          style={{
            position: 'relative',
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
        >
          <div ref={bubbleRef} className="speech-bubble" />
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
