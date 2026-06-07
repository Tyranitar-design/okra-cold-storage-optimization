<template>
  <div class="status-list">
    <div v-for="item in items" :key="item.label" class="status-row">
      <div class="status-label">{{ item.label }}</div>
      <div class="status-value" :class="item.className || ''">{{ item.value }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
})
</script>
