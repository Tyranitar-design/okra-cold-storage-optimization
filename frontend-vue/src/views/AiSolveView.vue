<template>
  <div>
    <!-- KPI 横幅：今日核心成果 -->
    <section class="kpi-grid">
      <KpiAnimated label="AI 加速比" :value="speedup" suffix="×" :decimals="2"
                   delta="vs Gurobi 直解" delta-class="positive" />
      <KpiAnimated label="AI warm 求解" :value="aiTime" suffix="s" :decimals="1"
                   :delta="`冷启动 ${coldTime}s`" delta-class="positive" />
      <KpiAnimated label="最优成本" :value="exactObj" suffix="元" :decimals="0"
                   delta="gap≤1% 已认证" delta-class="neutral" />
      <KpiAnimated label="OSM 路网" :value="osmEdges" :suffix="'条边'"
                   :delta="`${osmKm} km`" delta-class="positive" />
    </section>

    <!-- 四方法对比 -->
    <section class="content-grid single">
      <PanelCard title="v3.0 + OSM 四方法对比" subtitle="主线同标尺：direct MIP / AI warm start / NSGA-III / ALNS"
                 badge="核心创新" badge-class="ok">
        <EChart :option="methodCompareChart" height="340px" />
        <SectionTable :headers="['方法', '最优成本', 'gap%', '求解时间(s)', '前沿规模', '类型']" :rows="methodRows" />
        <p class="boundary-note">{{ fourMethodsBoundary }}</p>
      </PanelCard>
    </section>

    <!-- AI 加速对比 + 特征重要性 -->
    <section class="content-grid stagger">
      <PanelCard title="AI guided warm start 加速" subtitle="两阶段主线：site ranking → site + type + capacity 联合 MIP Start"
                 badge="7.3× 加速" badge-class="ok">
        <EChart :option="speedupChart" height="300px" />
        <StatusList :items="warmstartItems" />
      </PanelCard>
      <PanelCard title="AI 学到的节点重要性" subtitle="XGBoost 特征重要性（什么决定冷库选址）"
                 badge="可解释" badge-class="neutral">
        <EChart :option="featureChart" height="300px" />
      </PanelCard>
    </section>

    <section class="content-grid single">
      <PanelCard title="Optuna 调参增强" subtitle="自动搜索 XGBoost / warm start / Gurobi 参数"
                 badge="HPO" badge-class="ok">
        <StatusList :items="optunaItems" />
        <p class="boundary-note">{{ optunaBoundary }}</p>
      </PanelCard>
    </section>

    <!-- AI 推荐候选点 + OSM 路网对比 -->
    <section class="content-grid stagger">
      <PanelCard title="AI 推荐站点候选 top-8" subtitle="site ranking 第一阶段：模型预测最可能进入 warm start 的候选点">
        <EChart :option="candidateScoreChart" height="300px" />
      </PanelCard>
      <PanelCard title="OSM 真实路网 vs Haversine" subtitle="真实道路距离揭示的成本误差"
                 badge="真实数据" badge-class="ok">
        <StatusList :items="osmItems" />
        <p class="boundary-note">{{ osmBoundary }}</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import SectionTable from '../components/SectionTable.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import EChart from '../components/EChart.vue'
import { formatNumber, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const warm = computed(() => (b.value || {}).ai_warmstart_report || {})
const four = computed(() => (b.value || {}).v3_four_methods_report || {})
const osm = computed(() => (b.value || {}).osm_distance_report || {})

// ── KPI ──────────────────────────────────────────────────────────────────────
const speedup = computed(() => Number(four.value?.ai_speedup_vs_direct || warm.value?.speedup || 0))
const aiTime = computed(() => Number(warm.value?.ai_warm?.elapsed_sec || 0))
const coldTime = computed(() => Number(warm.value?.cold_start?.elapsed_sec || 0).toFixed(1))
const exactObj = computed(() => Number(four.value?.exact_reference_obj || warm.value?.ai_warm?.objective || 0))
const osmEdges = computed(() => Number(osm.value?.osm_matrix?.graph_edges_main_wcc || 0))
const osmKm = computed(() => {
  const mean = osm.value?.osm_vs_haversine?.osm_mean_km
  return mean ? `均距 ${mean} km` : '真实道路'
})
const optunaBest = computed(() => warm.value?.optuna_best_trial || {})
const optunaBoundary = computed(() =>
  warm.value?.optuna_claim_boundary || 'Optuna 优化的是求解配置与初始解质量；最终解仍由 Gurobi 认证。',
)

// ── 四方法对比图 ───────────────────────────────────────────────────────────────
const KIND_COLOR = { exact: '#2563eb', exact_ai: '#dc2626', heuristic: '#f59e0b' }

const methodCompareChart = computed(() => {
  const methods = safeArray(four.value?.methods)
  const labels = methods.map((m) => m.label)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['成本 gap (%)', '求解时间 (s)'], top: 0 },
    grid: { left: 55, right: 60, top: 40, bottom: 50 },
    xAxis: { type: 'category', data: labels, axisLabel: { interval: 0, fontSize: 11, rotate: 10 } },
    yAxis: [
      { type: 'value', name: 'gap (%)', position: 'left' },
      { type: 'value', name: '时间 (s)', position: 'right' },
    ],
    series: [
      {
        name: '成本 gap (%)', type: 'bar',
        data: methods.map((m) => ({
          value: Number(m.gap_pct || 0),
          itemStyle: { color: KIND_COLOR[m.kind] || '#888', borderRadius: [6, 6, 0, 0] },
        })),
        label: { show: true, position: 'top', formatter: (d) => `${d.value.toFixed(2)}%`, fontSize: 10 },
        animationDelay: (i) => i * 120,
      },
      {
        name: '求解时间 (s)', type: 'line', yAxisIndex: 1, smooth: true,
        data: methods.map((m) => Number(m.elapsed_sec || 0)),
        itemStyle: { color: '#16a34a' }, lineStyle: { width: 3 },
        symbol: 'circle', symbolSize: 8,
      },
    ],
  }
})

const methodRows = computed(() =>
  safeArray(four.value?.methods).map((m) => ({
    方法: m.label,
    最优成本: formatNumber(Math.round(m.best_cost || 0)),
    'gap%': Number(m.gap_pct || 0).toFixed(2),
    '求解时间(s)': Number(m.elapsed_sec || 0).toFixed(1),
    前沿规模: Number(m.front_size || 0).toFixed(m.front_size > 1.5 ? 1 : 0),
    类型: m.kind === 'exact' ? '精确' : m.kind === 'exact_ai' ? '精确+AI' : '启发式',
  })),
)

const fourMethodsBoundary = computed(() =>
  four.value?.claim_boundary || '四方法同 v3.0 容量链模型 + OSM 路网矩阵；县域 39 节点案例。',
)

// ── AI 加速对比图 ─────────────────────────────────────────────────────────────
const speedupChart = computed(() => {
  const cold = Number(warm.value?.cold_start?.elapsed_sec || 0)
  const ai = Number(warm.value?.ai_warm?.elapsed_sec || 0)
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(1)} s` },
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: ['冷启动', 'AI warm start'] },
    yAxis: { type: 'value', name: '求解时间 (s)' },
    series: [{
      type: 'bar', barWidth: '50%',
      data: [
        { value: cold, itemStyle: { color: '#94a3b8', borderRadius: [6, 6, 0, 0] } },
        { value: ai, itemStyle: { color: '#dc2626', borderRadius: [6, 6, 0, 0] } },
      ],
      label: { show: true, position: 'top', formatter: (d) => `${d.value.toFixed(1)}s`, fontWeight: 600 },
      animationDelay: (i) => i * 200,
    }],
  }
})

const warmstartItems = computed(() => {
  const t = warm.value?.training || {}
  const recommendedVersion = warm.value?.recommended_label || warm.value?.recommended_version || 'V3'
  const recommendedMeta = warm.value?.warm_versions?.[warm.value?.recommended_version] || {}
  const sources = recommendedMeta.assignment_source_breakdown || {}
  const sourceText = Object.entries(sources).map(([k, v]) => `${k}:${v}`).join(' / ') || '未提供'
  return [
    { label: '加速比', value: `${speedup.value.toFixed(2)}×`, className: 'ok' },
    { label: '最优解一致', value: '是（warm 不改最优性）', className: 'ok' },
    { label: '当前采用版本', value: `${recommendedVersion}`, className: 'ok' },
    { label: '训练样本', value: `${t.n_runs_used || 0} 个 priority 场景` },
    { label: '特征维度', value: `${t.n_features || 0} 维结构特征` },
    { label: '联合策略', value: warm.value?.joint_strategy || 'site ranking + facility template' },
    { label: '联合设施数', value: `${warm.value?.ai_warm?.warm_facilities_injected || safeArray(warm.value?.ai_warm_facilities).length || 0}` },
    { label: '回填来源', value: sourceText },
    { label: '模型', value: 'XGBoost 二分类' },
  ]
})

const optunaItems = computed(() => {
  const best = optunaBest.value || {}
  const params = best.params || {}
  const recheck = warm.value?.optuna_recheck_stats || {}
  const singleDone = warm.value?.optuna_single_trial_complete_count || warm.value?.optuna_trial_count || 0
  const singleRequested = warm.value?.optuna_n_trials_requested || warm.value?.optuna_trial_count || 0
  const multiDone = warm.value?.optuna_multi_trial_complete_count || 0
  const multiRequested = warm.value?.optuna_multi_trials_requested || warm.value?.optuna_multi_trial_count || 0
  return [
    { label: '状态', value: warm.value?.optuna_available ? '已生成 Optuna study' : '等待调参结果', className: warm.value?.optuna_available ? 'ok' : 'warn' },
    { label: '单目标 trial', value: `${singleDone}/${singleRequested}` },
    { label: '多目标 trial', value: `${multiDone}/${multiRequested}` },
    { label: 'Pareto front', value: `${warm.value?.optuna_pareto_front_size || 0}` },
    { label: 'best trial', value: best.number != null ? `#${best.number}` : '-' },
    { label: 'best speedup', value: best.speedup_vs_cold ? `${Number(best.speedup_vs_cold).toFixed(2)}×` : '-', className: best.speedup_vs_cold ? 'ok' : 'neutral' },
    { label: 'best elapsed', value: best.elapsed_sec ? `${best.elapsed_sec}s` : '-' },
    { label: 'best gap', value: best.gap_pct != null ? `${Number(best.gap_pct).toFixed(4)}%` : '-' },
    { label: '复核均值', value: recheck.elapsed_sec_mean ? `${recheck.elapsed_sec_mean}s / ${Number(recheck.speedup_vs_cold_mean || 0).toFixed(2)}×` : '-' },
    { label: '历史最高', value: warm.value?.optuna_historical_best_speedup ? `${warm.value.optuna_historical_best_speedup}×` : '-' },
    { label: 'warm strategy', value: best.warm_strategy_label || params.warm_strategy || '-' },
    { label: 'top_k', value: params.top_k != null ? `${params.top_k}` : '-' },
  ]
})

// ── 特征重要性图 ───────────────────────────────────────────────────────────────
const FEATURE_LABEL = {
  production_ton: '秋葵产量', max_dist: '最大距离', dist_to_C1: '到县城距离',
  lat: '纬度', lon: '经度', weighted_dist: '产量加权距离',
  population: '人口', precool_cover_2h: '预冷2h覆盖', cover_4h: '4h覆盖',
  min_dist: '最近距离', level: '行政级别', is_county: '是否县级', is_town: '是否乡镇',
}

const featureChart = computed(() => {
  const imps = safeArray(warm.value?.feature_importances)
    .filter((f) => f.importance > 0.001)
    .slice(0, 8)
    .reverse()
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
               valueFormatter: (v) => `${(Number(v) * 100).toFixed(1)}%` },
    grid: { left: 90, right: 30, top: 10, bottom: 30 },
    xAxis: { type: 'value', name: '重要性', axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` } },
    yAxis: { type: 'category', data: imps.map((f) => FEATURE_LABEL[f.feature] || f.feature),
             axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: imps.map((f) => ({
        value: f.importance,
        itemStyle: { color: '#6366f1', borderRadius: [0, 6, 6, 0] },
      })),
      label: { show: true, position: 'right', formatter: (d) => `${(d.value * 100).toFixed(1)}%`, fontSize: 10 },
    }],
  }
})

// ── AI 候选点打分图 ───────────────────────────────────────────────────────────
const candidateScoreChart = computed(() => {
  const scored = safeArray(warm.value?.scored_candidates).slice(0, 12)
  const topK = new Set(safeArray(warm.value?.ai_top_k))
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
               valueFormatter: (v) => Number(v).toFixed(3) },
    grid: { left: 45, right: 20, top: 10, bottom: 40 },
    xAxis: { type: 'category', data: scored.map((s) => s.node_id),
             axisLabel: { interval: 0, fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', name: '开放概率', max: 1 },
    series: [{
      type: 'bar',
      data: scored.map((s) => ({
        value: Number(s.score || 0),
        itemStyle: {
          color: topK.has(s.node_id) ? '#dc2626' : '#cbd5e1',
          borderRadius: [4, 4, 0, 0],
        },
      })),
      label: { show: false },
    }],
  }
})

// ── OSM 路网对比 ──────────────────────────────────────────────────────────────
const osmItems = computed(() => {
  const v = osm.value?.osm_vs_haversine || {}
  const m = osm.value?.osm_matrix || {}
  return [
    { label: 'OSM 平均距离', value: `${v.osm_mean_km || '-'} km`, className: 'ok' },
    { label: 'Haversine 平均', value: `${v.haversine_mean_km || '-'} km` },
    { label: '距离比 (OSM/Hav)', value: `${v.ratio_mean || '-'}×`, className: 'warn' },
    { label: '成本误差', value: v.obj_diff_pct != null ? `+${Number(v.obj_diff_pct).toFixed(1)}%` : '-', className: 'warn' },
    { label: '路网最短路覆盖', value: `${(100 - (m.fallback_pct || 0)).toFixed(0)}% (fallback ${m.fallback_pct || 0}%)`, className: 'ok' },
  ]
})

const osmBoundary = computed(() =>
  osm.value?.claim_boundary || 'OSM 路网为 Overpass 下载快照；揭示 Haversine 低估真实运输成本。',
)
</script>
