<template>
  <div class="chart-list" aria-label="Baseline cost breakdown chart">
    <div v-for="item in items" :key="item.component || item.label" class="chart-bar-row">
      <div class="chart-bar-label">{{ item.label || item.component }}</div>
      <div class="chart-bar-track">
        <span class="chart-bar-fill" :style="{ width: `${Math.max(0, Number(item.share_pct || 0)).toFixed(2)}%` }" />
      </div>
      <div class="chart-bar-value">{{ formatPercent(item.share_pct || 0, 2) }}</div>
    </div>
  </div>
</template>

<script setup>
import { formatPercent } from '../utils/format'

defineProps({
  items: { type: Array, default: () => [] },
})
</script>
