<template>
  <div class="stability-grid" aria-label="Sensitivity stability chart">
    <div v-for="group in groups" :key="group.sweep_variable" class="stability-item">
      <div class="stability-head">
        <span>{{ group.sweep_variable }}</span>
        <strong>{{ group.stable_open_sites ? 'stable' : 'changed' }}</strong>
      </div>
      <div class="stability-meter">
        <span :class="{ warn: !group.stable_open_sites }" :style="{ width: group.stable_open_sites ? '100%' : '42%' }" />
      </div>
      <div class="stability-meta">n={{ group.count }} · cost spread {{ formatPercent(group.cost_spread_pct || 0, 4) }}</div>
    </div>
  </div>
</template>

<script setup>
import { formatPercent } from '../utils/format'

defineProps({
  groups: { type: Array, default: () => [] },
})
</script>
