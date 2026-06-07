<template>
  <div ref="el" class="echart" :style="{ height: height }"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// 按需引入 ECharts 核心 + 用到的图表类型 + 渲染器
// 这样 tree-shaking 后 ECharts 从 ~900KB → ~200KB
import { init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, ScatterChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkPointComponent,
} from 'echarts/components'

// 注册所需组件（全局只需一次，但在组件内注册安全且 tree-shakeable）
use([
  CanvasRenderer,
  BarChart,
  LineChart,
  ScatterChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkPointComponent,
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '360px' },
})

const el = ref(null)
let chart = null

function render() {
  if (!el.value) return
  if (!chart) chart = init(el.value, null, { renderer: 'canvas' })
  chart.setOption(props.option, true)
  chart.resize()
}

function onResize() {
  if (chart) chart.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.echart { width: 100%; }
</style>
