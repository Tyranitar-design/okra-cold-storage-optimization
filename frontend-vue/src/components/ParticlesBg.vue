<template>
  <canvas ref="cv" class="particles"></canvas>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

// Lightweight particle network background (no external dependency).
// Draws drifting nodes with proximity links; pauses when tab is hidden.
const cv = ref(null)
let ctx = null
let raf = null
let particles = []
let w = 0
let h = 0
const COUNT = 46
const LINK_DIST = 130

function resize() {
  if (!cv.value) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  w = cv.value.clientWidth
  h = cv.value.clientHeight
  cv.value.width = w * dpr
  cv.value.height = h * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function seed() {
  particles = Array.from({ length: COUNT }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.35,
    vy: (Math.random() - 0.5) * 0.35,
    r: 1.2 + Math.random() * 1.8,
  }))
}

function step() {
  if (!ctx) return
  ctx.clearRect(0, 0, w, h)
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    if (p.x < 0 || p.x > w) p.vx *= -1
    if (p.y < 0 || p.y > h) p.vy *= -1
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(56, 189, 248, 0.55)'
    ctx.fill()
  }
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const a = particles[i]
      const b = particles[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const dist = Math.hypot(dx, dy)
      if (dist < LINK_DIST) {
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.strokeStyle = `rgba(99, 179, 237, ${0.18 * (1 - dist / LINK_DIST)})`
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }
  }
  raf = requestAnimationFrame(step)
}

function onVisibility() {
  if (document.hidden) {
    if (raf) cancelAnimationFrame(raf)
    raf = null
  } else if (!raf) {
    raf = requestAnimationFrame(step)
  }
}

onMounted(() => {
  ctx = cv.value.getContext('2d')
  resize()
  seed()
  raf = requestAnimationFrame(step)
  window.addEventListener('resize', () => { resize(); seed() })
  document.addEventListener('visibilitychange', onVisibility)
})

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped>
.particles {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
  opacity: 0.8;
}
</style>
