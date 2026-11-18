/**
 * VoiceRecorder — In-browser audio capture and WAV encoder for voice commands.
 * Captures clean 16kHz mono audio directly from microphone and encodes to 16-bit PCM WAV.
 */

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i))
  }
}

export function encodeWavBlob(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // Mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // Byte rate
  view.setUint16(32, 2, true) // Block align
  view.setUint16(34, 16, true) // Bits per sample
  writeString(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

export class VoiceRecorder {
  constructor(options = {}) {
    this.sampleRate = options.sampleRate || 16000
    this.silenceThreshold = options.silenceThreshold || 0.015
    this.silenceDurationMs = options.silenceDurationMs || 1500
    this.maxDurationMs = options.maxDurationMs || 10000

    this.audioContext = null
    this.mediaStream = null
    this.processor = null
    this.source = null
    this.chunks = []
    this.totalSamples = 0
    this.isRecording = false

    this.hasSpoken = false
    this.lastSpeechTime = 0
    this.maxTimer = null

    this.onStateChange = options.onStateChange || null
    this.onVolume = options.onVolume || null
    this.onAutoStop = options.onAutoStop || null
  }

  async start() {
    if (this.isRecording) return
    this.chunks = []
    this.totalSamples = 0
    this.hasSpoken = false
    this.lastSpeechTime = Date.now()

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })

      const AudioCtx = window.AudioContext || window.webkitAudioContext
      this.audioContext = new AudioCtx({ sampleRate: this.sampleRate })
      this.source = this.audioContext.createMediaStreamSource(this.mediaStream)
      this.processor = this.audioContext.createScriptProcessor(4096, 1, 1)

      this.processor.onaudioprocess = (e) => {
        if (!this.isRecording) return
        const inputData = e.inputBuffer.getChannelData(0)
        const copy = new Float32Array(inputData.length)
        copy.set(inputData)
        this.chunks.push(copy)
        this.totalSamples += copy.length

        // Measure audio volume (RMS)
        let sum = 0
        for (let i = 0; i < copy.length; i++) {
          sum += copy[i] * copy[i]
        }
        const rms = Math.sqrt(sum / copy.length)
        if (typeof this.onVolume === 'function') {
          this.onVolume(rms)
        }

        // Voice activity & silence detection
        const now = Date.now()
        if (rms > this.silenceThreshold) {
          this.hasSpoken = true
          this.lastSpeechTime = now
        } else if (this.hasSpoken && now - this.lastSpeechTime > this.silenceDurationMs) {
          // User finished speaking, auto stop
          if (typeof this.onAutoStop === 'function') {
            this.onAutoStop()
          }
        }
      }

      this.source.connect(this.processor)
      this.processor.connect(this.audioContext.destination)
      this.isRecording = true

      if (this.maxTimer) clearTimeout(this.maxTimer)
      this.maxTimer = setTimeout(() => {
        if (this.isRecording && typeof this.onAutoStop === 'function') {
          this.onAutoStop()
        }
      }, this.maxDurationMs)

      if (typeof this.onStateChange === 'function') {
        this.onStateChange(true)
      }
    } catch (err) {
      this.cleanup()
      throw err
    }
  }

  stop() {
    if (!this.isRecording) return null
    this.isRecording = false
    if (this.maxTimer) clearTimeout(this.maxTimer)

    const samples = new Float32Array(this.totalSamples)
    let offset = 0
    for (const chunk of this.chunks) {
      samples.set(chunk, offset)
      offset += chunk.length
    }

    const wavBlob = encodeWavBlob(samples, this.sampleRate)
    this.cleanup()

    if (typeof this.onStateChange === 'function') {
      this.onStateChange(false)
    }

    return wavBlob
  }

  cancel() {
    this.isRecording = false
    if (this.maxTimer) clearTimeout(this.maxTimer)
    this.cleanup()
    if (typeof this.onStateChange === 'function') {
      this.onStateChange(false)
    }
  }

  cleanup() {
    if (this.processor) {
      try {
        this.processor.disconnect()
        this.processor.onaudioprocess = null
      } catch {}
      this.processor = null
    }
    if (this.source) {
      try {
        this.source.disconnect()
      } catch {}
      this.source = null
    }
    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((t) => t.stop())
      } catch {}
      this.mediaStream = null
    }
    if (this.audioContext) {
      try {
        this.audioContext.close()
      } catch {}
      this.audioContext = null
    }
    this.chunks = []
    this.totalSamples = 0
  }
}
