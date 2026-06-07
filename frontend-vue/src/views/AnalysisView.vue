<template>
  <div>
    <section class="content-grid stagger">
      <PanelCard title="v3.0 成本结构 (容量链 + OSM)" subtitle="当前主模型成本构成（饼图）" badge="v3.0" badge-class="ok">
        <EChart :option="costPieChartV3" height="320px" />
      </PanelCard>
      <PanelCard title="v2.1 成本结构 (历史基线)" subtitle="Baseline v2.1 成本构成（参考）" badge="v2.1" badge-class="neutral">
        <EChart :option="costPieChart" height="320px" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="场景成本与耗时" subtitle="候选点规模 S1→S4 扩展对比 (v2.1)" badge="v2.1" badge-class="neutral">
        <EChart :option="scenarioChart" height="320px" />
      </PanelCard>
      <PanelCard title="灵敏度稳定性" subtitle="单因素扰动下布局是否稳定 (v2.1)" badge="v2.1" badge-class="neutral">
        <EChart :option="sensitivityChart" height="300px" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="分析摘要" subtitle="场景、灵敏度、方法与图像资产">
        <StatusList :items="summaryItems" />
      </PanelCard>
      <PanelCard title="v3.0 成本明细" subtitle="容量链模型各成本分项（OSM 路网）" badge="v3.0" badge-class="ok">
        <StatusList :items="v3CostItems" />
      </PanelCard>
    </section>

    <!-- v3.0 模型报告绑定区 ──────────────────────────────────── -->
    <section class="content-grid stagger">
      <PanelCard title="v3.0 容量链基线" subtitle="峰值库存/周转容量链语义修正 MIP" badge="v3.0" badge-class="ok">
        <StatusList :items="baselineV3Report" />
      </PanelCard>
      <PanelCard title="v3.0 求解前预检" subtitle="solver-free 容量压力静态闸门" badge="Pre-check" badge-class="neutral">
        <StatusList :items="baselineV3Presolve" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="v3.0 Gap 收敛证据" subtitle="named solver profile：bound_focus / extended_900s" badge="Gap" badge-class="ok">
        <StatusList :items="modelV3GapClosure" />
      </PanelCard>
      <PanelCard title="v3.0 稳健性筛选" subtitle="9 个变体 solver-free 容量压力排序" badge="Screen" badge-class="neutral">
        <StatusList :items="modelV3RobustnessScreen" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="v3.0 优先情景求解" subtitle="4 个 watch 变体真实 Gurobi 求解链路" badge="Priority" badge-class="ok">
        <StatusList :items="modelV3PriorityScenario" />
      </PanelCard>
      <PanelCard title="模型现实性审计" subtitle="进入论文强结论前的风险闸门" badge="Risk Gate" badge-class="warn">
        <StatusList :items="modelRealismAudit" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import EChart from '../components/EChart.vue'
import { formatNumber, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const av = computed(() => (b.value || {}).analysis_visualization_report || {})

// v3.0 成本结构（来自 baseline_v3_capacity_chain_report）
const v3Summary = computed(() => b.value?.baseline_v3_capacity_chain_report?.summary || {})

const costPieChartV3 = computed(() => {
  const s = v3Summary.value
  const items = [
    { name: '建设成本', value: Number(s.fixed_cost || 0) },
    { name: '运营成本', value: Number(s.operate_cost || 0) },
    { name: '运输成本', value: Number(s.transport_cost || 0) },
    { name: '损耗成本', value: Number(s.loss_cost || 0) },
    { name: '碳成本', value: Number(s.carbon_cost || 0) },
  ].filter((it) => it.value > 0)
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 元 ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      data: items,
      animationType: 'scale',
    }],
    color: ['#dc2626', '#f59e0b', '#16a34a', '#0ea5e9', '#6366f1'],
  }
})

const v3CostItems = computed(() => {
  const s = v3Summary.value
  return [
    { label: '总成本', value: `${formatNumber(Math.round(s.total_cost || 0))} 元`, className: 'ok' },
    { label: '建设+运营', value: `${formatNumber(Math.round((s.fixed_cost || 0) + (s.operate_cost || 0)))} 元` },
    { label: '运输成本', value: `${formatNumber(Math.round(s.transport_cost || 0))} 元` },
    { label: '损耗成本', value: `${formatNumber(Math.round(s.loss_cost || 0))} 元` },
    { label: '设施数', value: `${s.num_facilities || '-'} 个` },
    { label: '容量语义', value: s.capacity_semantics === 'peak_inventory_from_annual_flow' ? '峰值库存' : (s.capacity_semantics || '-'), className: 'ok' },
  ]
})

// ── 原有图表 ──────────────────────────────────────────────────

const costPieChart = computed(() => {
  const items = safeArray(av.value.baseline_cost_breakdown)
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 元 ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      data: items.map((it) => ({ name: it.label || it.component, value: Number(it.value || 0) })),
      animationType: 'scale',
    }],
    color: ['#6366f1', '#0ea5e9', '#16a34a', '#f59e0b', '#ec4899'],
  }
})

const scenarioChart = computed(() => {
  const items = safeArray(av.value.scenario?.items)
  const names = items.map((it) => it.scenario)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['总成本(百万)', '耗时(s)'], top: 0 },
    grid: { left: 55, right: 55, top: 36, bottom: 36 },
    xAxis: { type: 'category', data: names },
    yAxis: [{ type: 'value', name: '百万元' }, { type: 'value', name: '秒' }],
    series: [
      { name: '总成本(百万)', type: 'bar', data: items.map((it) => Number(it.total_cost || 0) / 1e6), itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } },
      { name: '耗时(s)', type: 'line', yAxisIndex: 1, smooth: true, data: items.map((it) => Number(it.solve_time_sec || 0)), itemStyle: { color: '#f59e0b' } },
    ],
  }
})

const sensitivityChart = computed(() => {
  const groups = safeArray(av.value.sensitivity?.groups)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 50, right: 20, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: groups.map((g) => g.sweep_variable), axisLabel: { interval: 0, rotate: 14, fontSize: 10 } },
    yAxis: { type: 'value', name: '成本波动 (%)' },
    series: [{
      type: 'bar',
      data: groups.map((g) => ({
        value: Number(g.cost_spread_pct || 0),
        itemStyle: { color: g.stable_open_sites ? '#16a34a' : '#f59e0b', borderRadius: [4, 4, 0, 0] },
      })),
      label: { show: true, position: 'top', formatter: (d) => groups[d.dataIndex]?.stable_open_sites ? '稳定' : '变化', fontSize: 10 },
    }],
  }
})

const summaryItems = computed(() => {
  const s = av.value.summary || {}
  return [
    { label: '场景数', value: formatNumber(s.scenario_count || 0) },
    { label: '灵敏度分组', value: formatNumber(s.sensitivity_group_count || 0) },
    { label: '方法 smoke', value: formatNumber(s.method_count || 0) },
    { label: '图像资产', value: formatNumber(s.figure_count || 0) },
    { label: '场景布局稳定', value: s.scenario_stable_open_sites ? 'yes' : 'no', className: s.scenario_stable_open_sites ? 'ok' : 'warn' },
    { label: '灵敏度全稳定', value: s.sensitivity_all_groups_stable_open_sites ? 'yes' : 'no', className: s.sensitivity_all_groups_stable_open_sites ? 'ok' : 'warn' },
  ]
})

// ── v3.0 模型报告绑定 ─────────────────────────────────────────

const baselineV3Report = computed(() => {
  const r = b.value?.baseline_v3_capacity_chain_report || {}
  const s = r.summary || {}
  return [
    { label: 'solver_claim_state', value: r.claim_boundary?.solver_claim_state || '-' },
    { label: 'objective', value: s.objective_value ? formatNumber(s.objective_value) + ' 元' : '-' },
    { label: 'mip_gap', value: s.mip_gap_pct != null ? s.mip_gap_pct.toFixed(4) + '%' : '-' },
    { label: 'capacity_semantics', value: s.capacity_semantics || '-', className: s.capacity_semantics === 'peak_inventory_from_annual_flow' ? 'ok' : 'warn' },
    { label: 'facilities', value: s.open_facility_count || '-' },
  ]
})

const baselineV3Presolve = computed(() => {
  const r = b.value?.baseline_v3_presolve_report || {}
  const s = r.summary || {}
  return [
    { label: 'solver_readiness', value: s.solver_readiness_state || '-', className: s.solver_readiness_state?.startsWith('solver_result') ? 'ok' : 'neutral' },
    { label: 'precool_uncovered', value: s.precool_uncovered_count != null ? s.precool_uncovered_count : '-', className: s.precool_uncovered_count === 0 ? 'ok' : 'warn' },
    { label: 'lower_bound_facilities', value: s.lower_bound_facilities || '-' },
    { label: 'downstream_share_sum', value: s.downstream_share_sum != null ? s.downstream_share_sum.toFixed(2) : '-' },
  ]
})

const modelV3GapClosure = computed(() => {
  const r = b.value?.model_v3_gap_closure_report || {}
  const s = r.summary || {}
  const runs = safeArray(r.runs)
  const extended = runs.find((r) => r.profile === 'extended_bound_900s') || {}
  return [
    { label: 'profile_count', value: s.profile_count || '-' },
    { label: 'extended_status', value: extended.solver_status || '-', className: extended.solver_status === 'OPTIMAL' ? 'ok' : 'warn' },
    { label: 'extended_gap', value: extended.mip_gap_pct != null ? extended.mip_gap_pct.toFixed(4) + '%' : '-', className: Number(extended.mip_gap_pct) < 1 ? 'ok' : 'warn' },
    { label: 'extended_time', value: extended.solve_time_sec ? extended.solve_time_sec.toFixed(1) + 's' : '-' },
  ]
})

const modelV3RobustnessScreen = computed(() => {
  const r = b.value?.model_v3_robustness_screen_report || {}
  const s = r.summary || {}
  return [
    { label: 'variant_count', value: s.variant_count || '-' },
    { label: 'pass_count', value: s.pass_count || '-', className: 'ok' },
    { label: 'watch_count', value: s.watch_count || '-', className: 'warn' },
    { label: 'fail_count', value: s.fail_count || 0, className: s.fail_count === 0 ? 'ok' : 'error' },
    { label: 'recommended_solver_runs', value: s.recommended_solver_run_count || '-' },
  ]
})

const modelV3PriorityScenario = computed(() => {
  const r = b.value?.model_v3_priority_scenario_report || {}
  const s = r.summary || {}
  return [
    { label: 'queued_variants', value: s.queued_variant_count || '-' },
    { label: 'run_count', value: s.run_count || '-' },
    { label: 'gap_satisfied', value: s.gap_satisfied_count || '-', className: 'ok' },
    { label: 'open_gap', value: s.open_gap_count || '-', className: s.open_gap_count > 0 ? 'warn' : 'ok' },
  ]
})

const modelRealismAudit = computed(() => {
  const s = b.value?.model_realism_audit?.summary || {}
  return [
    { label: 'readiness_state', value: s.readiness_state || '-', className: s.readiness_state?.includes('needs') ? 'warn' : 'ok' },
    { label: 'high_risk_count', value: s.high_risk_count ?? '-', className: s.high_risk_count > 0 ? 'warn' : 'ok' },
    { label: 'capacity_ratio', value: s.capacity_to_annual_production_ratio != null ? s.capacity_to_annual_production_ratio.toFixed(3) : '-' },
    { label: 'real_data_ready', value: s.real_data_ready_for_apply_count || 0, className: s.real_data_ready_for_apply_count > 0 ? 'ok' : 'warn' },
  ]
})
</script>
