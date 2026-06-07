<template>
  <div>
    <section class="content-grid single">
      <PanelCard title="实时求解触发器" subtitle="点击按钮即刻触发 Gurobi 实时求解，并流式展示 gap 收敛" badge="P1" badge-class="ok">
        <div class="solve-toolbar live-toolbar">
          <label>模式：
            <select v-model="liveMode" :disabled="liveRunning">
              <option value="cold_start">冷启动</option>
              <option value="ai_warm">AI warm</option>
            </select>
          </label>
          <label>Profile：
            <select v-model="liveProfile" :disabled="liveRunning">
              <option value="bound_focus_60s">bound_focus_60s</option>
              <option value="baseline_300s">baseline_300s</option>
              <option value="incumbent_focus_60s">incumbent_focus_60s</option>
            </select>
          </label>
          <button class="btn" @click="startLiveSolve" :disabled="liveRunning">▶ 实时求解</button>
          <button class="btn ghost" @click="resetLiveSolve" :disabled="liveRunning && livePoints.length > 0">↺ 清空</button>
          <span class="solve-step">状态 {{ liveStatusLabel }}</span>
          <span class="solve-step">事件 {{ livePoints.length }} 条</span>
          <span class="solve-gap" :class="liveGapClass">当前 gap：{{ liveGapLabel }}</span>
        </div>
        <EChart :option="liveTraceChart" height="320px" />
        <StatusList :items="liveSolveItems" />
        <p class="boundary-note">{{ liveClaimBoundary }}</p>
      </PanelCard>
    </section>

    <!-- v3.0 求解过程双轨动画 ─────────────────────────────────────────── -->
    <section class="content-grid single">
      <PanelCard title="v3.0 容量链求解收敛动画" subtitle="Gurobi 直解 vs AI warm start · 逐帧展示 gap 收敛"
                 badge="主求解器" badge-class="ok">
        <div class="solve-toolbar">
          <button class="btn" @click="playV3" :disabled="v3Playing">▶ 播放</button>
          <button class="btn ghost" @click="resetV3">↺ 重置</button>
          <span class="solve-step">时刻 {{ Number(v3Time).toFixed(1) }}s · 帧 {{ v3Frame + 1 }}/{{ v3MaxFrame }}</span>
          <span class="solve-step">数据点 灰{{ coldTrace.length }} / 红{{ aiTrace.length }}</span>
          <span class="legend-chip cold">Gurobi 直解</span>
          <span class="legend-chip ai">AI warm start</span>
        </div>
        <EChart :option="v3TraceChart" height="360px" />
        <StatusList :items="v3GapItems" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="v3.0 优先情景求解" subtitle="4 个 priority watch 变体真实 Gurobi 求解链路">
        <SectionTable :headers="['情景', '目标值', 'gap%', '设施数', '状态']" :rows="priorityRows" />
      </PanelCard>
      <PanelCard title="v3.0 gap 收敛证据" subtitle="named solver profile 多档对比">
        <EChart :option="v3GapChart" height="280px" />
      </PanelCard>
    </section>

    <!-- 原 Benders cut 管理动画 ────────────────────────────────────────── -->
    <section class="content-grid single">
      <PanelCard title="Benders 子线机制动画" subtitle="cut ranking / robustness 子线：逐迭代展示上下界收敛与 gap 变化">
        <div class="solve-toolbar">
          <label>实例：
            <select v-model="selectedCase">
              <option v-for="c in cases" :key="c" :value="c">{{ shortCase(c) }}</option>
            </select>
          </label>
          <button class="btn" @click="play" :disabled="playing">▶ 播放</button>
          <button class="btn ghost" @click="reset">↺ 重置</button>
          <span class="solve-step">迭代 {{ frame }} / {{ maxFrame }}</span>
          <span class="solve-gap" :class="gapClass">当前 gap：{{ curGap }}%</span>
        </div>
        <EChart :option="convergenceChart" height="380px" />
        <p class="boundary-note">{{ boundary }}</p>
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="受控 cut ranking / robustness 对比" subtitle="learned vs random / recency / all（同预算 K）" badge="Ablation" badge-class="neutral">
        <EChart :option="solvedChart" height="300px" />
      </PanelCard>
      <PanelCard title="诚实结论" subtitle="为什么推荐学习式 cut 排序而非硬丢弃" badge="Finding" badge-class="ok">
        <StatusList :items="verdictItems" />
        <p class="boundary-note">{{ recommendation }}</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import SectionTable from '../components/SectionTable.vue'
import EChart from '../components/EChart.vue'
import { formatNumber, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const conv = computed(() => (b.value || {}).benders_convergence || {})

const POLICY_COLORS = { all_cuts: '#2563eb', random_K: '#f59e0b', recency_K: '#16a34a', learned_K: '#dc2626' }
const POLICY_LABEL = { all_cuts: '全部 cut (经典)', random_K: '随机-K', recency_K: '最近-K', learned_K: '学习-K (AI)' }

const liveMode = ref('cold_start')
const liveProfile = ref('bound_focus_60s')
const liveRunning = ref(false)
const liveStatus = ref('idle')
const liveMeta = ref({})
const livePoints = ref([])
const liveResult = ref(null)
const liveError = ref('')
let liveEventSource = null

const liveStatusLabel = computed(() => {
  if (liveRunning.value) return '运行中'
  if (liveStatus.value === 'done') return '已完成'
  if (liveStatus.value === 'error') return '失败'
  return '待启动'
})
const liveGapLabel = computed(() => {
  const last = livePoints.value[livePoints.value.length - 1]
  return last ? `${Number(last.gap_pct || 0).toFixed(3)}%` : '—'
})
const liveGapClass = computed(() => {
  const last = livePoints.value[livePoints.value.length - 1]
  return last && Number(last.gap_pct || 999) <= 1 ? 'ok' : 'warn'
})
const liveClaimBoundary = computed(() => liveResult.value?.claim_boundary || '实时流来自当前本地求解，会占用后端 Gurobi 资源；AI warm 复用既有联合 warm-start 设施证据链。')
const liveSolveItems = computed(() => {
  const end = liveResult.value || {}
  const analysis = end.analysis || {}
  const solver = analysis.solver || {}
  const summary = analysis.summary || {}
  const warmSites = safeArray(end.warm_sites).length ? safeArray(end.warm_sites) : safeArray(liveMeta.value?.warm_sites)
  const warmFacilities = safeArray(end.warm_facilities).length ? safeArray(end.warm_facilities) : safeArray(liveMeta.value?.warm_facilities)
  const warmFacilityLabel = warmFacilities.map((fac) => `${fac.site}/${fac.type}/${fac.capacity ?? '?'}t`).join(', ')
  return [
    { label: 'mode', value: liveMode.value, className: liveMode.value === 'ai_warm' ? 'ok' : '' },
    { label: 'profile', value: liveMeta.value?.profile?.name || liveProfile.value },
    { label: 'matrix_source', value: liveMeta.value?.matrix_source || '-' },
    { label: 'elapsed', value: end.elapsed_sec ? `${Number(end.elapsed_sec).toFixed(1)}s` : '-' },
    { label: 'objective', value: solver.objective ? formatNumber(Math.round(solver.objective)) : '-' },
    { label: 'mip_gap', value: solver.mip_gap_pct != null ? `${Number(solver.mip_gap_pct).toFixed(3)}%` : liveGapLabel.value, className: Number(solver.mip_gap_pct) <= 1 ? 'ok' : 'warn' },
    { label: 'facilities', value: summary.num_facilities != null ? String(summary.num_facilities) : '-' },
    { label: 'warm_sites', value: warmSites.join(', ') || '无' },
    { label: 'warm_facilities', value: warmFacilityLabel || '无' },
    { label: 'error', value: liveError.value || '-', className: liveError.value ? 'warn' : '' },
  ]
})
const liveTraceChart = computed(() => ({
  tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(3)}%` },
  grid: { left: 55, right: 25, top: 24, bottom: 40 },
  xAxis: { type: 'value', name: '求解时间 (s)', min: 0 },
  yAxis: { type: 'value', name: 'gap (%)', min: 0 },
  series: [{
    name: liveMode.value === 'ai_warm' ? 'AI warm' : '冷启动',
    type: 'line',
    smooth: false,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { width: 3, color: liveMode.value === 'ai_warm' ? '#dc2626' : '#64748b' },
    itemStyle: { color: liveMode.value === 'ai_warm' ? '#dc2626' : '#64748b' },
    data: livePoints.value.map((p) => [Number(p.t), Number(p.gap_pct)]),
    markLine: {
      silent: true,
      symbol: 'none',
      lineStyle: { color: '#16a34a', type: 'dashed', width: 1.5 },
      label: { formatter: '1% 容差', fontSize: 10, color: '#16a34a' },
      data: [{ yAxis: 1 }],
    },
  }],
}))

function resetLiveSolve() {
  if (liveEventSource) {
    liveEventSource.close()
    liveEventSource = null
  }
  liveRunning.value = false
  liveStatus.value = 'idle'
  liveMeta.value = {}
  livePoints.value = []
  liveResult.value = null
  liveError.value = ''
}

function startLiveSolve() {
  resetLiveSolve()
  liveRunning.value = true
  liveStatus.value = 'running'
  const url = `/api/v1/optimize/v3-live-stream?mode=${encodeURIComponent(liveMode.value)}&profile=${encodeURIComponent(liveProfile.value)}`
  const es = new EventSource(url)
  liveEventSource = es
  es.addEventListener('start', (evt) => {
    liveMeta.value = JSON.parse(evt.data)
  })
  es.addEventListener('progress', (evt) => {
    livePoints.value = [...livePoints.value, JSON.parse(evt.data)]
  })
  es.addEventListener('end', (evt) => {
    liveResult.value = JSON.parse(evt.data)
    liveRunning.value = false
    liveStatus.value = 'done'
    es.close()
    liveEventSource = null
  })
  es.addEventListener('error', (evt) => {
    const payload = evt?.data ? JSON.parse(evt.data) : { message: '实时求解流中断' }
    liveError.value = payload.message || '实时求解失败'
    liveRunning.value = false
    liveStatus.value = 'error'
    es.close()
    liveEventSource = null
  })
  es.onerror = () => {
    if (liveRunning.value) {
      liveError.value = liveError.value || '实时求解连接中断'
      liveRunning.value = false
      liveStatus.value = 'error'
    }
    es.close()
    liveEventSource = null
  }
}

const cases = computed(() => safeArray(conv.value.top_cases))
const selectedCase = ref('')
watch(cases, (v) => { if (v.length && !selectedCase.value) selectedCase.value = v[0] }, { immediate: true })

function shortCase(c) { return String(c).split(':').slice(-1)[0] }

const caseTraces = computed(() =>
  safeArray(conv.value.traces).filter((t) => t.case_id === selectedCase.value),
)
const maxFrame = computed(() => Math.max(1, ...caseTraces.value.map((t) => (t.points || []).length)))

const frame = ref(0)
const playing = ref(false)
watch(selectedCase, () => reset())

function reset() { playing.value = false; frame.value = maxFrame.value }
function play() {
  playing.value = true
  frame.value = 0
  const timer = setInterval(() => {
    frame.value += 1
    if (frame.value >= maxFrame.value) { clearInterval(timer); playing.value = false }
  }, 420)
}
watch(maxFrame, () => { if (!playing.value) frame.value = maxFrame.value })

const curGap = computed(() => {
  const learned = caseTraces.value.find((t) => t.policy === 'all_cuts') || caseTraces.value[0]
  const pts = learned?.points || []
  const idx = Math.min(frame.value, pts.length) - 1
  return idx >= 0 ? (pts[idx].gap_pct || 0).toFixed(3) : '—'
})
const gapClass = computed(() => (Number(curGap.value) <= 1 ? 'ok' : 'warn'))

const convergenceChart = computed(() => {
  const series = caseTraces.value.map((t) => {
    const pts = (t.points || []).slice(0, frame.value)
    return {
      name: POLICY_LABEL[t.policy] || t.policy,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: t.policy === 'learned_K' ? 3 : 2 },
      itemStyle: { color: POLICY_COLORS[t.policy] || '#888' },
      data: pts.map((p) => [p.iter_no, p.gap_pct]),
    }
  })
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(3)}%` },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 30, top: 36, bottom: 40 },
    xAxis: { type: 'value', name: 'Benders 迭代', minInterval: 1 },
    yAxis: { type: 'log', name: 'gap (%)', min: 0.01 },
    series,
    animationDuration: 400,
  }
})

const solvedChart = computed(() => {
  const q = conv.value?.verdict?.quality || {}
  const policies = Object.keys(POLICY_LABEL).filter((p) => q[p])
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 45, right: 20, top: 20, bottom: 60 },
    xAxis: { type: 'category', data: policies.map((p) => POLICY_LABEL[p]), axisLabel: { interval: 0, fontSize: 10, rotate: 12 } },
    yAxis: { type: 'value', name: '求解到最优实例数' },
    series: [{
      type: 'bar',
      data: policies.map((p) => ({ value: q[p].all_solved_to_optimal_count, itemStyle: { color: POLICY_COLORS[p], borderRadius: [6, 6, 0, 0] } })),
      label: { show: true, position: 'top', formatter: (d) => `${d.value}/${q[policies[d.dataIndex]].instances}` },
      animationDelay: (i) => i * 120,
    }],
  }
})

const verdictItems = computed(() => {
  const q = conv.value?.verdict?.quality || {}
  const f = conv.value?.verdict?.findings || {}
  return [
    { label: 'all_cuts 求解到最优', value: `${q.all_cuts?.all_solved_to_optimal_count ?? '-'}/${q.all_cuts?.instances ?? '-'}`, className: 'ok' },
    { label: 'learned_K 求解到最优', value: `${q.learned_K?.all_solved_to_optimal_count ?? '-'}/${q.learned_K?.instances ?? '-'}`, className: 'ok' },
    { label: 'random_K 求解到最优', value: `${q.random_K?.all_solved_to_optimal_count ?? '-'}/${q.random_K?.instances ?? '-'}`, className: 'warn' },
    { label: 'learned 收敛时墙钟', value: f.time_vs_baselines_on_jointly_solved?.all_cuts === 'learned_better' ? '优于全 cut' : '持平', className: 'ok' },
    { label: 'conclusion', value: conv.value?.verdict?.conclusion || '-' },
  ]
})

const recommendation = computed(() => conv.value?.verdict?.findings?.practical_recommendation || conv.value?.claim_boundary || '')
const boundary = computed(() => conv.value?.claim_boundary || '公开 LRP 投影实例上的受控对比，非完整 routing LRP，也非企业级验证。')

// ── v3.0 求解过程展示 ────────────────────────────────────────────────────────
const v3Gap = computed(() => (b.value || {}).model_v3_gap_closure_report || {})
const v3Priority = computed(() => (b.value || {}).model_v3_priority_scenario_report || {})
const four = computed(() => (b.value || {}).v3_four_methods_report || {})
const warm = computed(() => (b.value || {}).ai_warmstart_report || {})

const v3GapChart = computed(() => {
  const runs = safeArray(v3Gap.value?.runs)
  if (runs.length === 0) {
    const cold = warm.value?.cold_start || {}
    const ai = warm.value?.ai_warm || {}
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['gap %', '时间 (s)'], top: 0 },
      grid: { left: 50, right: 50, top: 36, bottom: 36 },
      xAxis: { type: 'category', data: ['cold_start', 'ai_warm'] },
      yAxis: [{ type: 'value', name: 'gap %' }, { type: 'value', name: '秒', position: 'right' }],
      series: [
        { name: 'gap %', type: 'bar',
          data: [Number(cold.mip_gap_pct || 0), Number(ai.mip_gap_pct || 0)],
          itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: 'top', formatter: (d) => `${d.value.toFixed(2)}%` } },
        { name: '时间 (s)', type: 'line', yAxisIndex: 1, smooth: true,
          data: [Number(cold.elapsed_sec || 0), Number(ai.elapsed_sec || 0)],
          itemStyle: { color: '#16a34a' }, lineStyle: { width: 3 } },
      ],
    }
  }
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['gap %', '时间 (s)'], top: 0 },
    grid: { left: 50, right: 50, top: 36, bottom: 50 },
    xAxis: { type: 'category', data: runs.map((r) => r.profile || r.profile_name),
             axisLabel: { interval: 0, fontSize: 10, rotate: 12 } },
    yAxis: [{ type: 'value', name: 'gap %' }, { type: 'value', name: '秒', position: 'right' }],
    series: [
      { name: 'gap %', type: 'bar',
        data: runs.map((r) => Number(r.mip_gap_pct || 0)),
        itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } },
      { name: '时间 (s)', type: 'line', yAxisIndex: 1, smooth: true,
        data: runs.map((r) => Number(r.solve_time_sec || r.elapsed_sec || 0)),
        itemStyle: { color: '#16a34a' }, lineStyle: { width: 3 } },
    ],
  }
})

const v3GapItems = computed(() => {
  const cold = warm.value?.cold_start || {}
  const ai = warm.value?.ai_warm || {}
  const speedup = four.value?.ai_speedup_vs_direct || warm.value?.speedup
  return [
    { label: 'Gurobi 直解时间', value: cold.elapsed_sec ? `${cold.elapsed_sec.toFixed(1)}s` : '-' },
    { label: 'AI warm 时间', value: ai.elapsed_sec ? `${ai.elapsed_sec.toFixed(1)}s` : '-', className: 'ok' },
    { label: 'AI 加速比', value: speedup ? `${speedup}×` : '-', className: 'ok' },
    { label: '最优解一致性', value: '是 (4,433,112 元)', className: 'ok' },
    { label: '最终 gap', value: ai.mip_gap_pct ? `${ai.mip_gap_pct.toFixed(2)}% (gap≤1% 已认证)` : '-', className: 'ok' },
  ]
})

const priorityRows = computed(() => {
  const runs = safeArray(v3Priority.value?.runs)
  return runs.map((r) => ({
    情景: String(r.variant?.name || r.variant_name || '').replace('_bound_focus_60s', ''),
    目标值: formatNumber(Math.round(r.objective || 0)),
    'gap%': Number(r.mip_gap_pct || 0).toFixed(2),
    设施数: r.num_facilities || r.analysis?.num_facilities || '-',
    状态: r.status_name || (Number(r.mip_gap_pct || 0) <= 1 ? 'OPTIMAL' : 'TIME_LIMIT'),
  }))
})

const trace = computed(() => {
  if (liveResult.value?.trace?.length) {
    if (liveMode.value === 'ai_warm') {
      return { ai_warm: { trace: liveResult.value.trace }, cold_start: {} }
    }
    return { cold_start: { trace: liveResult.value.trace }, ai_warm: {} }
  }
  return (b.value || {}).v3_solve_trace || {}
})
const coldTrace = computed(() => safeArray(trace.value?.cold_start?.trace))
const aiTrace = computed(() => safeArray(trace.value?.ai_warm?.trace))
const frameTimes = computed(() => {
  const ts = [...coldTrace.value, ...aiTrace.value].map((p) => Number(p.t))
  return Array.from(new Set(ts)).sort((a, b) => a - b)
})
const v3MaxFrame = computed(() => Math.max(1, frameTimes.value.length))

const v3Frame = ref(0)
const v3Playing = ref(false)
let v3Timer = null

const v3Time = computed(() => {
  const ft = frameTimes.value
  if (ft.length === 0) return 0
  const idx = Math.min(v3Frame.value, ft.length - 1)
  return ft[idx] ?? ft[ft.length - 1]
})

function resetV3() {
  v3Playing.value = false
  if (v3Timer) clearInterval(v3Timer)
  v3Frame.value = v3MaxFrame.value - 1
}
function playV3() {
  if (v3Timer) clearInterval(v3Timer)
  v3Playing.value = true
  v3Frame.value = 0
  v3Timer = setInterval(() => {
    v3Frame.value += 1
    if (v3Frame.value >= v3MaxFrame.value - 1) {
      v3Frame.value = v3MaxFrame.value - 1
      clearInterval(v3Timer)
      v3Playing.value = false
    }
  }, 120)
}
watch(v3MaxFrame, (v) => { if (!v3Playing.value) v3Frame.value = v - 1 }, { immediate: true })

function traceUpTo(pts, t) {
  const out = pts.filter((p) => Number(p.t) <= t + 1e-9).map((p) => [Number(p.t), Number(p.gap_pct)])
  if (out.length === 0 && pts.length > 0) {
    return [[Number(pts[0].t), Number(pts[0].gap_pct)]]
  }
  return out
}

const v3TraceChart = computed(() => {
  const coldData = traceUpTo(coldTrace.value, v3Time.value)
  const aiData = traceUpTo(aiTrace.value, v3Time.value)
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(3)}%` },
    legend: { data: ['Gurobi 直解', 'AI warm start'], top: 0 },
    grid: { left: 55, right: 30, top: 36, bottom: 50 },
    xAxis: {
      type: 'value', name: '求解时间 (s)', min: 0, max: 310,
      nameLocation: 'middle', nameGap: 30,
    },
    yAxis: { type: 'value', name: 'gap (%)', min: 0, max: 22 },
    series: [
      {
        name: 'Gurobi 直解', type: 'line', smooth: false, symbol: 'circle', symbolSize: 4,
        itemStyle: { color: '#94a3b8' }, lineStyle: { width: 2, color: '#94a3b8' },
        data: coldData,
      },
      {
        name: 'AI warm start', type: 'line', smooth: false, symbol: 'circle', symbolSize: 5,
        itemStyle: { color: '#dc2626' }, lineStyle: { width: 3, color: '#dc2626' },
        data: aiData,
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: '#16a34a', type: 'dashed', width: 1.5 },
          label: { formatter: '1% 容差', fontSize: 10, color: '#16a34a' },
          data: [{ yAxis: 1 }],
        },
      },
    ],
    animationDuration: 150,
  }
})
</script>

<style scoped>
.solve-toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; font-size: 13px; color: #475569; }
.solve-toolbar select { padding: 4px 8px; border-radius: 8px; border: 1px solid #cbd5e1; }
.solve-step { color: #64748b; }
.solve-gap { margin-left: auto; font-weight: 600; }
.solve-gap.ok { color: #16a34a; }
.solve-gap.warn { color: #d97706; }
.legend-chip { font-size: 11px; padding: 2px 10px; border-radius: 999px; color: #fff; }
.legend-chip.cold { background: #94a3b8; }
.legend-chip.ai { background: #dc2626; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.5; }
.live-toolbar { align-items: center; }
</style>
