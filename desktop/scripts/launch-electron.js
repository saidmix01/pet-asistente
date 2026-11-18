const path = require('path')
const { spawn } = require('child_process')

const electronBin = require('electron')
const appDir = path.resolve(__dirname, '..')

const args = []

// On Linux, pass the Ozone platform BEFORE Electron initializes so browser and
// GPU processes match. Prefer X11/XWayland when DISPLAY is available so the
// pet stays always-on-top (override_redirect), moves freely across the desktop,
// and uses X11 setShape() for click-through with zero compositor shadow.
if (process.platform === 'linux') {
  args.push('--enable-transparent-visuals')
  const ozone =
    process.env.PET_OZONE_PLATFORM ||
    (process.env.DISPLAY ? 'x11' : (process.env.WAYLAND_DISPLAY ? 'wayland' : ''))
  if (ozone) {
    args.push(`--ozone-platform=${ozone}`)
  }
}

args.push(appDir, ...process.argv.slice(2))

const child = spawn(electronBin, args, {
  cwd: appDir,
  stdio: 'inherit',
  env: process.env,
})

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 0)
})

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    try { child.kill(sig) } catch {}
  })
}
