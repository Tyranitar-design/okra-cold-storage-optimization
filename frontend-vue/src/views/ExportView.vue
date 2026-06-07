<template>
  <div>
    <section class="kpi-grid">
      <KpiAnimated label="核心指标条数" :value="metricCount" suffix="项" :decimals="0"
                   delta="可追溯到报告产物" delta-class="positive" />
      <KpiAnimated label="对比方法数" :value="methodCount" suffix="种" :decimals="0"
                   delta="v3.0 + OSM 同标尺" delta-class="neutral" />
      <KpiAnimated label="AI 加速比" :value="speedup" suffix="×" :decimals="2"
                   delta="warm start vs direct MIP" delta-class="positive" />
      <KpiAnimated label="证据是否齐备" :value="0" :decimals="0"
                   :delta="readyNote" :delta-class="paperReady ? 'positive' : 'warn'" :class="'state-kpi'" />
    </section>

    <section class="content-grid single">
      <PanelCard title="论文证据导出" subtitle="导出 v3.0 + direct MIP 主线证据与 warm start 关键指标" badge="P5" badge-class="ok">
        <div class="export-toolbar">
          <div class="tabs">
            <button class="tab" :class="{ active: tab === 'latex' }" @click="tab = 'latex'">LaTeX 表格</button>
            <button class="tab" :class="{ active: tab === 'markdown' }" @click="tab = 'markdown'">Markdown / Word</button>
          </div>
          <div class="actions">
            <button class="btn ghost" @click="copyCurrent">{{ copied ? '已复制 ✓' : '复制' }}</button>
            <button class="btn" @click="download('latex')">下载 .tex</button>
            <button class="btn" @click="download('markdown')">下载 .md</button>
          </div>
        </div>
        <pre class="export-pre" v-if="currentText">{{ currentText }}</pre>
        <p v-else class="boundary-note">暂无导出内容（后端 export 接口未返回数据）。</p>
        <p class="boundary-note">{{ researchBoundary }}</p>
        <p class="boundary-note" v-if="generatedAt">生成时间：{{ generatedAt }} · 所有数值来自已验证报告产物，未重新求解、未编造。</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import { useBootstrap } from '../utils/format'

useBootstrap() // keep for consistency (component lifecycle tracking)

const exportData = ref(null)
const tab = ref('latex')
const copied = ref(false)
const error = ref('')

const latex = computed(() => exportData.value?.latex || '')
const markdown = computed(() => exportData.value?.markdown || '')
const currentText = computed(() => (tab.value === 'latex' ? latex.value : markdown.value))
const generatedAt = computed(() => exportData.value?.generated_at || '')
const researchBoundary = computed(() => exportData.value?.research_boundary || '本导出为只读汇总：主线为 v3.0 + direct MIP，AI 强证据为 warm start；不重新运行优化或算法。')

const metrics = computed(() => exportData.value?.summary_metrics || {})
const metricCount = computed(() => Object.keys(metrics.value).length)
const methodCount = computed(() => {
  // count rows in the markdown method table (lines starting with "| " under 四方法)
  const md = markdown.value
  const idx = md.indexOf('四方法对比')
  if (idx < 0) return 0
  const tail = md.slice(idx)
  const rows = tail.split('\n').filter((l) => l.startsWith('| ') && !l.includes('---') && !l.includes('方法 |'))
  return rows.length
})
const speedup = computed(() => {
  const v = metrics.value['AI warm 加速比']
  if (!v) return 0
  return Number(String(v).replace('×', '')) || 0
})
const paperReady = computed(() => metrics.value['证据齐备'] === '是')
const readyNote = computed(() => metrics.value['证据齐备'] || '-')

async function loadExport() {
  try {
    const resp = await fetch('/api/v1/export/paper')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    exportData.value = await resp.json()
  } catch (err) {
    error.value = `导出加载失败：${err.message}`
  }
}

async function copyCurrent() {
  try {
    await navigator.clipboard.writeText(currentText.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // clipboard may be blocked in some contexts; ignore
  }
}

function download(fmt) {
  window.open(`/api/v1/export/paper/download?fmt=${encodeURIComponent(fmt)}`, '_blank')
}

onMounted(loadExport)
</script>

<style scoped>
.export-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.tabs { display: inline-flex; gap: 6px; }
.tab { padding: 6px 14px; border-radius: 8px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; font-size: 13px; color: #475569; }
.tab.active { background: #0f766e; color: #fff; border-color: #0f766e; }
.actions { display: inline-flex; gap: 8px; }
.export-pre { background: #0f172a; color: #e2e8f0; border-radius: 10px; padding: 16px; font-size: 12px; line-height: 1.6; max-height: 460px; overflow: auto; white-space: pre; font-family: 'Consolas', 'Courier New', monospace; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.5; }
:deep(.state-kpi .kpi-anim-value) { font-size: 16px; }
</style>
