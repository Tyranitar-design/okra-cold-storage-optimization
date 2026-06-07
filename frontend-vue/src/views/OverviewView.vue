<template>
  <div>
    <section class="kpi-grid">
      <KpiAnimated label="v3.0 最优成本" :value="kpi.exactCost" :suffix="'元'" :decimals="0"
                   delta="OSM 路网 · gap≤1% 已认证" delta-class="positive" />
      <KpiAnimated label="AI 加速比" :value="kpi.aiSpeedup" suffix="×" :decimals="2"
                   :delta="`AI warm ${kpi.aiTime}s vs 直解 ${kpi.coldTime}s`" delta-class="positive" />
      <KpiAnimated label="地图点位" :value="kpi.mapPoints" :suffix="'个'"
                   :delta="kpi.mapBackend" :delta-class="kpi.mapClass" />
      <KpiAnimated label="论文证据层" :value="kpi.paperLayer" :suffix="'层'"
                   :delta="kpi.paperState" :delta-class="kpi.paperClass" />
    </section>

    <section class="content-grid stagger">
      <PanelCard title="系统状态" subtitle="数据库 / 地图 / 求解器" badge="Live" badge-class="ok">
        <StatusList :items="systemItems" />
      </PanelCard>
      <PanelCard title="MIS 就绪度" subtitle="文件 / helper / runtime 审计" badge="Audit" badge-class="neutral">
        <StatusList :items="misReadinessItems" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="v3.0 + OSM 四方法对比" subtitle="精确 / AI增强 / NSGA-III / ALNS 同标尺"
                 badge="核心创新" badge-class="ok">
        <EChart :option="methodChart" height="320px" />
      </PanelCard>
      <PanelCard title="模型现实性审计" subtitle="进入论文强结论前的风险闸门" badge="Risk Gate" badge-class="warn">
        <StatusList :items="modelRealismItems" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import EChart from '../components/EChart.vue'
import { formatNumber, formatPercent, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()

const kpi = computed(() => {
  const paper = b.value?.paper_evidence_pack?.summary || {}
  const mapReady = b.value?.map_readiness_report?.summary || {}
  const four = b.value?.v3_four_methods_report || {}
  const warm = b.value?.ai_warmstart_report || {}
  return {
    exactCost: Number(four.exact_reference_obj || warm.ai_warm?.objective || 0),
    aiSpeedup: Number(four.ai_speedup_vs_direct || warm.speedup || 0),
    aiTime: Number(warm.ai_warm?.elapsed_sec || 0).toFixed(1),
    coldTime: Number(warm.cold_start?.elapsed_sec || 0).toFixed(0),
    mapPoints: mapReady.map_feature_count || 0,
    mapBackend: mapReady.source_backend === 'database' ? '来源 database' : '文件兜底',
    mapClass: mapReady.source_backend === 'database' ? 'positive' : 'warn',
    paperLayer: paper.paper_layer_count || 0,
    paperState: paper.paper_ready ? '已就绪' : '待补齐',
    paperClass: paper.paper_ready ? 'positive' : 'warn',
  }
})

const systemItems = computed(() => {
  const probe = b.value?.db_probe || {}
  const mp = b.value?.map_provider_status?.summary || {}
  const four = b.value?.v3_four_methods_report || {}
  return [
    { label: 'PostgreSQL 连通', value: probe.query_ready ? '已连通' : '文件兜底', className: probe.query_ready ? 'ok' : 'warn' },
    { label: '当前数据库', value: probe.probe_current_database || '-' },
    { label: '高德底图', value: mp.browser_provider_ready ? '已启用 (amap)' : '未启用', className: mp.browser_provider_ready ? 'ok' : 'warn' },
    { label: 'OSM 路网', value: `${b.value?.osm_distance_report?.osm_matrix?.graph_edges_main_wcc || 0} 条边`, className: 'ok' },
    { label: 'Gurobi 许可', value: 'NODE (无变量上限)', className: 'ok' },
    { label: 'AI 加速', value: four.ai_speedup_vs_direct ? `${four.ai_speedup_vs_direct}× (XGBoost warm)` : '-', className: 'ok' },
  ]
})

const misReadinessItems = computed(() => {
  const s = b.value?.mis_readiness_report?.summary || {}
  return [
    { label: 'check_count', value: formatNumber(s.check_count || 0) },
    { label: 'ready_count', value: formatNumber(s.ready_count || 0), className: 'ok' },
    { label: 'runtime_verified', value: formatNumber(s.runtime_verified_count || 0) },
    { label: 'paper_layer_count', value: formatNumber(s.paper_layer_count || 0) },
    { label: 'database_probe_ok', value: s.database_probe_ok ? 'yes' : 'no', className: s.database_probe_ok ? 'ok' : 'warn' },
  ]
})

const modelRealismItems = computed(() => {
  const s = b.value?.model_realism_audit?.summary || {}
  return [
    { label: 'readiness_state', value: s.readiness_state || '-' },
    { label: 'high_risk_count', value: formatNumber(s.high_risk_count || 0), className: s.high_risk_count ? 'warn' : 'ok' },
    { label: '容量/年产量比', value: formatNumber(s.capacity_to_annual_production_ratio || 0, 3) },
    { label: '固定+运营成本占比', value: formatPercent(s.fixed_operating_cost_share_pct || 0, 1) },
    { label: '真实外部数据就绪', value: formatNumber(s.real_external_ready_for_apply_count || 0), className: s.real_external_ready_for_apply_count ? 'ok' : 'warn' },
  ]
})

// v3.0 + OSM 四方法对比图（替换原方法链路图，显示新数据）
const KIND_COLOR = { exact: '#2563eb', exact_ai: '#dc2626', heuristic: '#f59e0b' }
const methodChart = computed(() => {
  const methods = safeArray(b.value?.v3_four_methods_report?.methods)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['成本 gap (%)', '运行时 (s)'], top: 0 },
    grid: { left: 50, right: 50, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: methods.map((m) => m.label), axisLabel: { fontSize: 10, interval: 0, rotate: 8 } },
    yAxis: [
      { type: 'value', name: 'gap %', position: 'left' },
      { type: 'value', name: '秒', position: 'right' },
    ],
    series: [
      { name: '成本 gap (%)', type: 'bar',
        data: methods.map((m) => ({
          value: Number(m.gap_pct || 0),
          itemStyle: { color: KIND_COLOR[m.kind] || '#888', borderRadius: [4, 4, 0, 0] },
        })),
        animationDelay: (i) => i * 100 },
      { name: '运行时 (s)', type: 'line', yAxisIndex: 1,
        data: methods.map((m) => Number(m.elapsed_sec || 0)),
        smooth: true, itemStyle: { color: '#16a34a' }, lineStyle: { width: 3 } },
    ],
    animationEasing: 'cubicOut',
  }
})
</script>
