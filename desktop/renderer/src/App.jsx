import { useEffect, useRef } from 'react'

const api = typeof window !== 'undefined' ? window.pet : null

const SPRITE_URL = '/assets/pugasset-grid.png'
const SHEET = {
  width: 800, height: 512,
  frameWidth: 64, frameHeight: 64,
  offsetX: 95, offsetY: 0,
}
const WINDOW_W = 120
const WINDOW_H = 120

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
  idle:     [2000, 4000],
  idle2:    [2000, 4000],
  sit:      [2000, 5000],
  walk:     [1500, 4000],
  run:      [1000, 3000],
  sniff:    [2000, 5000],
  sniffwalk:[1500, 4000],
}

const STATES = Object.keys(ANIMS)

// ── WebSocket config ───────────────────────────────────────
const WS_URL = 'ws://127.0.0.1:8000/ws/state'
const RECONNECT_MS = 3000

// ── Event → Animation reactions ────────────────────────────
function getReaction(eventType, data) {
  const t = (data?.activity_type || '').toLowerCase()
  switch (eventType) {
    case 'activity.update':
      if (t === 'coding')  return { state: 'jump',     duration: 1500 }
      if (t === 'browsing') return { state: 'sniffwalk',duration: 2000 }
      if (t === 'reading' || t === 'design')
                            return { state: 'sniff',    duration: 2000 }
      return { state: 'walk', duration: 1500 }
    case 'activity.switch':
      return { state: 'sniff', duration: 1200 }
    case 'activity.idle':
      return { state: 'idle', duration: 4000 }
    default:
      return null
  }
}

function rand(min, max) { return Math.random() * (max - min) + min }
function pickNext(current) {
  const others = STATES.filter(s => s !== current)
  return others[Math.floor(Math.random() * others.length)]
}

let gFallbackX = 0

export default function App() {
  const elRef     = useRef(null)
  const dotRef    = useRef(null)

  // ── Refs (game-loop state) ───────────────────────────────
  const stateRef    = useRef('sniff')
  const dirRef      = useRef(1)
  const frameRef    = useRef(0)
  const posRef      = useRef({ x: 0, y: 0 })
  const screenRef   = useRef({ w: 1920, h: 1080 })
  const draggingRef = useRef(false)
  const hoveredRef  = useRef(false)
  const lastPtrRef  = useRef({ x: 0, y: 0 })
  const readyRef    = useRef(false)

  // ── Apply visual state to DOM ────────────────────────────
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
  }

  const setConnDot = (online) => {
    const dot = dotRef.current
    if (!dot) return
    dot.className = `conn-dot ${online ? 'online' : 'offline'}`
  }

  // ── Game loop + WebSocket ────────────────────────────────
  useEffect(() => {
    let rafId = null
    let lastTime = 0
    let frameAccum = 0
    let stateTimer = 0

    // ── WebSocket ──────────────────────────────────────────
    let ws = null
    let reconnectTimer = null

    function connectWs() {
      if (ws) try { ws.close() } catch {}
      ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setConnDot(true)
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'event' && msg.data?.event) {
            const reaction = getReaction(msg.data.event, msg.data.data)
            if (reaction) {
              stateRef.current = reaction.state
              stateTimer = reaction.duration > 0
                ? reaction.duration
                : rand(STATE_DURATIONS[reaction.state][0], STATE_DURATIONS[reaction.state][1])
              frameAccum = 0
              frameRef.current = 0
            }
          }
        } catch { /* malformed msg */ }
      }

      ws.onclose = () => {
        setConnDot(false)
        reconnectTimer = setTimeout(connectWs, RECONNECT_MS)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connectWs()

    // ── Init ───────────────────────────────────────────────
    ;(async () => {
      screenRef.current = {
        w: window.screen.width || 1920,
        h: window.screen.height || 1080,
      }
      try {
        if (api?.getPosition) {
          const p = await api.getPosition()
          posRef.current = { x: p.x ?? 0, y: p.y ?? 0 }
        }
        if (api?.getScreenSize) {
          const s = await api.getScreenSize()
          screenRef.current = { w: s.width ?? 1920, h: s.height ?? 1080 }
        }
      } catch { /* ok */ }

      dirRef.current = Math.random() > 0.5 ? 1 : -1
      const d = STATE_DURATIONS[stateRef.current]
      stateTimer = rand(d[0], d[1])
      readyRef.current = true
      lastTime = performance.now()
      applyVisual()
    })()

    // ── Game loop ──────────────────────────────────────────
    const loop = (now) => {
      if (!readyRef.current) {
        rafId = requestAnimationFrame(loop)
        return
      }

      const dt = Math.min(now - lastTime, 50)
      lastTime = now

      if (!draggingRef.current) {
        const anim = ANIMS[stateRef.current]

        // ── Animation frame advance ──
        frameAccum += dt
        while (frameAccum >= anim.msPerFrame) {
          frameAccum -= anim.msPerFrame
          const step = stateRef.current === 'sniff' ? 1 : dirRef.current
          frameRef.current = (frameRef.current + step + anim.frames) % anim.frames
        }

        // ── Movement ──
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

        // ── State transitions ──
        stateTimer -= dt
        if (stateTimer <= 0) {
          const next = pickNext(stateRef.current)
          const nextAnim = ANIMS[next]
          stateRef.current = next
          const d = STATE_DURATIONS[next]
          stateTimer = rand(d[0], d[1])
          frameAccum = 0
          frameRef.current = frameRef.current % nextAnim.frames
        }

        applyVisual()
      }

      rafId = requestAnimationFrame(loop)
    }

    rafId = requestAnimationFrame(loop)

    // ── Cleanup ────────────────────────────────────────────
    return () => {
      if (rafId) cancelAnimationFrame(rafId)
      if (ws) ws.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [])

  // ── Drag / interact handlers ────────────────────────────
  const setInteractive = (val) => {
    if (!api?.setInteractive) return
    api.setInteractive(val).catch(() => {})
  }
  const moveWindowBy = (dx, dy) => {
    if (api?.moveBy) { api.moveBy(dx, dy).catch(() => {}); return }
    gFallbackX += dx
    posRef.current = { x: gFallbackX, y: posRef.current.y + dy }
  }
  const onPointerEnter = () => { hoveredRef.current = true; setInteractive(true) }
  const onPointerLeave = () => { if (!draggingRef.current) setInteractive(false) }
  const onPointerDown = (e) => {
    if (e.button !== 0) return
    draggingRef.current = true
    lastPtrRef.current = { x: e.screenX, y: e.screenY }
    setInteractive(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e) => {
    if (!draggingRef.current) return
    const dx = e.screenX - lastPtrRef.current.x
    const dy = e.screenY - lastPtrRef.current.y
    lastPtrRef.current = { x: e.screenX, y: e.screenY }
    posRef.current = { x: posRef.current.x + dx, y: posRef.current.y + dy }
    moveWindowBy(dx, dy)
  }
  const stopDrag = (e) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
    if (!hoveredRef.current) setInteractive(false)
  }

  // ── Render ───────────────────────────────────────────────
  return (
    <div className="stage">
      <div
        ref={elRef}
        className="pet"
        style={{
          width: SHEET.frameWidth,
          height: SHEET.frameHeight,
          transform: 'translate(0px, 0px) scaleX(1)',
          backgroundImage: `url(${SPRITE_URL})`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition:
            `${-(SHEET.offsetX)}px ${-(SHEET.offsetY + 6 * SHEET.frameHeight)}px`,
          backgroundSize: `${SHEET.width}px ${SHEET.height}px`,
        }}
        onPointerEnter={onPointerEnter}
        onPointerLeave={onPointerLeave}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      />
      <div ref={dotRef} className="conn-dot offline" />
    </div>
  )
}
