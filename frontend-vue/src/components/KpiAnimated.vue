<template>
  <div class="kpi-anim">
    <div class="kpi-anim-label">{{ label }}</div>
    <div class="kpi-anim-value">{{ display }}<span v-if="suffix" class="kpi-suffix">{{ suffix }}</span></div>
    <div v-if="delta" class="kpi-anim-delta" :class="deltaClass">{{ delta }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: [Number, String], default: 0 },
  suffix: { type: String, default: '' },
  delta: { type: String, default: '' },
  deltaClass: { type: String, default: 'positive' },
  decimals: { type: Number, default: 0 },
})

const display = ref('0')

function animateTo(target) {
  const num = Number(target)
  if (!isFinite(num)) {
    display.value = String(target)
    return
  }
  const start = performance.now()
  const dur = 900
  const from = 0
  function tick(now) {
    const t = Math.min(1, (now - start) / dur)
    const eased = 1 - Math.pow(1 - t, 3)
    const cur = from + (num - from) * eased
    display.value = cur.toLocaleString('en-US', {
      minimumFractionDigits: props.decimals,
      maximumFractionDigits: props.decimals,
    })
    if (t < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

onMounted(() => animateTo(props.value))
watch(() => props.value, (v) => animateTo(v))
</script>

<style scoped>
.kpi-anim {
  background: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(241,245,249,0.9));
  border: 1px solid rgba(148,163,184,0.25);
  border-radius: 14px;
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.kpi-anim:hover { transform: translateY(-3px); box-shadow: 0 12px 28px rgba(30,64,175,0.12); }
.kpi-anim-label { font-size: 12px; color: #64748b; letter-spacing: 0.5px; }
.kpi-anim-value { font-size: 30px; font-weight: 700; color: #0f172a; margin-top: 4px; line-height: 1.1; }
.kpi-suffix { font-size: 14px; font-weight: 500; color: #64748b; margin-left: 4px; }
.kpi-anim-delta { font-size: 12px; margin-top: 6px; }
.kpi-anim-delta.positive { color: #16a34a; }
.kpi-anim-delta.warn { color: #d97706; }
.kpi-anim-delta.neutral { color: #64748b; }
</style>
