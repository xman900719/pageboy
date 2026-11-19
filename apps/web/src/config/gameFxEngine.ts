/**
 * 书童轻量混合游戏特效微引擎：
 * - 顶层 pointer-events: none 60fps Canvas 2D 重力粒子爆卡/破甲火花
 * - 零外部音频文件的原生 Web Audio 合成音效（选牌、破雾、SSR爆卡、陷阱受击）
 * - 遵循 prefers-reduced-motion 无障碍动效降级规范
 */

export type GameSoundKind = 'tap' | 'win' | 'error'
export type ParticleBurstMode = 'gold' | 'red'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  color: string
  alpha: number
  rot: number
  vrot: number
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function playGameSound(kind: GameSoundKind, enabled = true): void {
  if (!enabled || typeof window === 'undefined') return
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) return
  try {
    const ctx = new AudioCtx()
    const now = ctx.currentTime
    const notes =
      kind === 'win'
        ? [523.25, 659.25, 783.99, 1046.5]
        : kind === 'error'
          ? [196, 146.83]
          : [440, 587.33]
    const oscType: OscillatorType = kind === 'win' ? 'triangle' : kind === 'error' ? 'sawtooth' : 'sine'
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = oscType
      osc.frequency.setValueAtTime(freq, now + idx * 0.065)
      gain.gain.setValueAtTime(0.09, now + idx * 0.065)
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.065 + 0.22)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now + idx * 0.065)
      osc.stop(now + idx * 0.065 + 0.24)
    })
  } catch {
    // 忽略浏览器自动播放策略拦截
  }
}

export class CanvasParticleFx {
  private canvas: HTMLCanvasElement | null = null
  private ctx: CanvasRenderingContext2D | null = null
  private particles: Particle[] = []
  private rafId: number | null = null

  attach(canvas: HTMLCanvasElement | null): void {
    this.canvas = canvas
    this.ctx = canvas ? canvas.getContext('2d') : null
    this.resize()
  }

  resize(): void {
    if (!this.canvas || typeof window === 'undefined') return
    this.canvas.width = window.innerWidth
    this.canvas.height = window.innerHeight
  }

  clear(): void {
    this.particles = []
    if (this.rafId !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
    if (this.ctx && this.canvas) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    }
  }

  burst(mode: ParticleBurstMode = 'gold', originX?: number, originY?: number): void {
    if (prefersReducedMotion() || !this.canvas || !this.ctx || typeof requestAnimationFrame !== 'function') {
      return
    }
    this.resize()
    const cx = originX ?? this.canvas.width * 0.5
    const cy = originY ?? this.canvas.height * 0.42
    const palette =
      mode === 'gold'
        ? ['#f59e0b', '#fbbf24', '#1e7a4c', '#8b5cf6', '#ec4899']
        : ['#e74c3c', '#c0392b', '#f39c12']
    const count = mode === 'gold' ? 56 : 28
    for (let i = 0; i < count; i += 1) {
      const angle = Math.random() * Math.PI * 2
      const speed = 2.8 + Math.random() * 8.2
      this.particles.push({
        x: cx,
        y: cy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 3.2,
        size: 5 + Math.random() * 5,
        color: palette[i % palette.length],
        alpha: 1,
        rot: Math.random() * Math.PI * 2,
        vrot: (Math.random() - 0.5) * 0.24,
      })
    }
    if (this.rafId === null) {
      this.tick()
    }
  }

  private tick = (): void => {
    if (!this.ctx || !this.canvas) {
      this.rafId = null
      return
    }
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    this.particles = this.particles.filter(p => p.alpha > 0.03)
    for (const p of this.particles) {
      p.x += p.vx
      p.y += p.vy
      p.vy += 0.26
      p.alpha *= 0.955
      p.rot += p.vrot
      this.ctx.save()
      this.ctx.globalAlpha = p.alpha
      this.ctx.translate(p.x, p.y)
      this.ctx.rotate(p.rot)
      this.ctx.fillStyle = p.color
      this.ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.65)
      this.ctx.restore()
    }
    if (this.particles.length > 0) {
      this.rafId = requestAnimationFrame(this.tick)
    } else {
      this.rafId = null
    }
  }
}
