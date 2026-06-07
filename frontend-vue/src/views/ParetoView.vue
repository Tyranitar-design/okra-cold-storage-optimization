<template>
  <div>
    <!-- v3.0 + OSM 四方法对比（核心论文表）─────────────────────────────── -->
    <section class="content-grid stagger">
      <PanelCard title="v3.0 + OSM 四方法对比 (论文核心)" subtitle="同模型同矩阵：精确 / AI增强 / NSGA-III / ALNS"
                 badge="v3.0" badge-class="ok">
        <SectionTable :headers="['方法', '最优成本', 'gap%', '时间(s)', '前沿', '类型']" :rows="v3MethodRows" />
      </PanelCard>
      <PanelCard title="启发式 Pareto 前沿规模" subtitle="ALNS / NSGA-III 在 v3.0 上的非支配点数">
        <EChart :option="v3FrontSizeChart" height="280px" />
      </PanelCard>
    </section>

    <!-- 原 v2.1 多目标前沿散点图（保留作为多场景多目标参考）─────────── -->
    <section class="content-grid single">
      <PanelCard title="多目标 Pareto 前沿 (v2.1 多场景)" subtitle="成本 vs 腐损（点大小=碳排放）· 精确 vs 启发式叠加">
        <div class="pareto-toolbar">
          <label>场景：
            <select v-model="selectedScenario">
              <option v-for="s in scenarioNames" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <span class="legend-chip exact">精确 ε-约束</span>
          <span class="legend-chip nsga">NSGA-III</span>
          <span class="legend-chip alns">ALNS</span>
        </div>
        <EChart :option="paretoChart" height="440px" />
        <p class="boundary-note">{{ boundary }}</p>
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="方法质量-时间权衡" subtitle="成本 gap (%) vs 运行时（对数）">
        <EChart :option="tradeoffChart" height="320px" />
      </PanelCard>
      <PanelCard title="支配性与超体积" subtitle="启发式前沿被精确前沿支配的程度" badge="MOO" badge-class="neutral">
        <SectionTable :headers="['场景', '方法', 'gap%', '超体积比', '非支配率']" :rows="methodRows" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import SectionTable from '../components/SectionTable.vue'
import EChart from '../components/EChart.vue'
import { formatNumber, formatPercent, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const pareto = computed(() => (b.value || {}).pareto_front || {})
const four = computed(() => (b.value || {}).v3_four_methods_report || {})
const scenarios = computed(() => safeArray(pareto.value.scenarios))
const scenarioNames = computed(() => scenarios.value.map((s) => s.scenario))

const selectedScenario = ref('')
watch(scenarioNames, (v) => { if (v.length && !scenarioNames.value.includes(selectedScenario.value)) selectedScenario.value = v[0] }, { immediate: true })

const activeScenario = computed(() => scenarios.value.find((s) => s.scenario === selectedScenario.value) || scenarios.value[0] || {})

// ── v3.0 四方法表 ────────────────────────────────────────────────────────────
const v3MethodRows = computed(() =>
  safeArray(four.value?.methods).map((m) => ({
    方法: m.label,
    最优成本: formatNumber(Math.round(m.best_cost || 0)),
    'gap%': Number(m.gap_pct || 0).toFixed(2),
    '时间(s)': Number(m.elapsed_sec || 0).toFixed(1),
    前沿: Number(m.front_size || 0).toFixed(m.front_size > 1.5 ? 1 : 0),
    类型: m.kind === 'exact' ? '精确' : m.kind === 'exact_ai' ? '精确+AI' : '启发式',
  })),
)

const v3FrontSizeChart = computed(() => {
  const heuristics = safeArray(four.value?.methods).filter((m) => m.kind === 'heuristic')
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 50, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: heuristics.map((m) => m.label) },
    yAxis: { type: 'value', name: '非支配点数(均值)' },
    series: [{
      type: 'bar',
      data: heuristics.map((m) => ({
        value: Number(m.front_size || 0),
        itemStyle: { color: '#f59e0b', borderRadius: [6, 6, 0, 0] },
      })),
      label: { show: true, position: 'top', formatter: (d) => d.value.toFixed(1), fontWeight: 600 },
    }],
  }
})

// ── 原 v2.1 散点图保留 ───────────────────────────────────────────────────────
function toSeries(front, color, name, symbolSize) {
  const pts = safeArray(front)
  return {
    name,
    type: 'scatter',
    symbolSize: symbolSize || ((val) => 8 + (val[2] || 0) * 3),
    itemStyle: { color, opacity: 0.85 },
    emphasis: { focus: 'series' },
    data: pts.map((p) => [p[0] / 1e6, p[1], p[2]]),
  }
}

const paretoChart = computed(() => {
  const s = activeScenario.value
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.seriesName}<br/>成本 ${p.value[0].toFixed(2)} 百万元<br/>腐损 ${p.value[1].toFixed(2)} 吨<br/>碳 ${p.value[2].toFixed(3)} 吨`,
    },
    legend: { top: 0 },
    grid: { left: 60, right: 30, top: 36, bottom: 50 },
    xAxis: { type: 'value', name: '总成本 (百万元)', scale: true, nameGap: 28 },
    yAxis: { type: 'value', name: '腐损 (吨)', scale: true },
    series: [
      { ...toSeries(s.exact_front, '#2563eb', '精确 ε-约束'), symbol: 'diamond', symbolSize: (v) => 10 + (v[2] || 0) * 3, lineStyle: {}, type: 'scatter' },
      toSeries(s.nsga3_front, '#f59e0b', 'NSGA-III'),
      toSeries(s.alns_front, '#16a34a', 'ALNS'),
    ],
    animationDuration: 700,
  }
})

const tradeoffChart = computed(() => {
  const rows = safeArray(pareto.value.method_summary)
  const colorMap = { exact_epsilon: '#2563eb', nsga3: '#f59e0b', alns: '#16a34a' }
  const series = ['exact_epsilon', 'nsga3', 'alns'].map((m) => ({
    name: m,
    type: 'scatter',
    symbolSize: 16,
    itemStyle: { color: colorMap[m] },
    data: rows.filter((r) => r.method === m).map((r) => [Math.max(r.elapsed_sec_mean, 0.01), r.cost_gap_vs_exact_pct, r.scenario]),
  }))
  return {
    tooltip: { trigger: 'item', formatter: (p) => `${p.seriesName} · ${p.value[2]}<br/>运行时 ${p.value[0].toFixed(2)}s<br/>成本 gap ${p.value[1].toFixed(2)}%` },
    legend: { top: 0 },
    grid: { left: 55, right: 25, top: 36, bottom: 45 },
    xAxis: { type: 'log', name: '运行时 (s)' },
    yAxis: { type: 'value', name: '成本 gap (%)' },
    series,
  }
})

const methodRows = computed(() =>
  safeArray(pareto.value.method_summary).map((r) => ({
    场景: String(r.scenario || '').split('_')[0],
    方法: r.method,
    'gap%': formatPercent(r.cost_gap_vs_exact_pct || 0, 2),
    超体积比: r.hypervolume_ratio_vs_exact == null ? '-' : formatNumber(r.hypervolume_ratio_vs_exact, 3),
    非支配率: formatPercent((r.coverage_not_dominated_by_exact_mean || 0) * 100, 0),
  })),
)

const boundary = computed(() => pareto.value.claim_boundary || '县域案例三目标前沿；超体积为共享蒙特卡洛估计，仅作相对比较。')
</script>

<style scoped>
.pareto-toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; font-size: 13px; color: #475569; }
.pareto-toolbar select { padding: 4px 8px; border-radius: 8px; border: 1px solid #cbd5e1; }
.legend-chip { font-size: 11px; padding: 2px 10px; border-radius: 999px; color: #fff; }
.legend-chip.exact { background: #2563eb; }
.legend-chip.nsga { background: #f59e0b; }
.legend-chip.alns { background: #16a34a; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.5; }
</style>
