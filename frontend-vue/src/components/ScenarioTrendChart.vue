<template>
  <div class="scenario-chart" aria-label="Scenario cost and runtime chart">
    <svg viewBox="0 0 640 260" role="img">
      <line x1="56" y1="214" x2="606" y2="214" class="axis" />
      <line x1="56" y1="32" x2="56" y2="214" class="axis" />
      <g v-for="point in chartPoints" :key="point.scenario">
        <rect :x="point.x - 24" :y="point.costY" width="22" :height="214 - point.costY" class="bar-primary" />
        <rect :x="point.x + 2" :y="point.runtimeY" width="22" :height="214 - point.runtimeY" class="bar-secondary" />
        <text :x="point.x" y="236" text-anchor="middle" class="axis-label">{{ point.label }}</text>
      </g>
      <text x="56" y="22" class="chart-caption">cost/runtime normalized by current result range</text>
      <text x="440" y="22" class="legend">
        <tspan class="legend-cost">■</tspan> cost
        <tspan dx="14" class="legend-runtime">■</tspan> runtime
      </text>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

function scaled(value, min, max) {
  if (max === min) return 110
  return 214 - ((Number(value) - min) / (max - min)) * 162
}

const chartPoints = computed(() => {
  const rows = props.items
  const costs = rows.map((item) => Number(item.total_cost || 0))
  const runtimes = rows.map((item) => Number(item.solve_time_sec || 0))
  const minCost = Math.min(...costs, 0)
  const maxCost = Math.max(...costs, 1)
  const minRuntime = Math.min(...runtimes, 0)
  const maxRuntime = Math.max(...runtimes, 1)
  const span = rows.length > 1 ? 520 / (rows.length - 1) : 0
  return rows.map((item, idx) => ({
    scenario: item.scenario,
    label: item.scenario?.replace('_candidates', '') || `S${idx + 1}`,
    x: 74 + idx * span,
    costY: scaled(item.total_cost, minCost, maxCost),
    runtimeY: scaled(item.solve_time_sec, minRuntime, maxRuntime),
  }))
})
</script>
