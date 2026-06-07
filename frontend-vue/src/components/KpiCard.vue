<template>
  <section class="kpi-card">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value">{{ value }}</div>
    <div class="kpi-delta" :class="deltaClass">{{ delta }}</div>
  </section>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  delta: { type: String, default: '-' },
  deltaClass: { type: String, default: 'neutral' },
})
</script>
