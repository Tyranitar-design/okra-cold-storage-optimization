<template>
  <div>
    <!-- v3.0 AI warm start 核心成果横幅 ───────────────────────────────── -->
    <section class="kpi-grid">
      <KpiAnimated label="v3.0 AI 加速比" :value="speedup" suffix="×" :decimals="2"
                   delta="XGBoost guided MIP Start" delta-class="positive" />
      <KpiAnimated label="求解时间缩减" :value="timeReduce" suffix="s" :decimals="0"
                   :delta="`${coldT}s → ${aiT}s`" delta-class="positive" />
      <KpiAnimated label="最优解一致" :value="exactObj" :suffix="'元'" :decimals="0"
                   delta="warm start 不影响最优性" delta-class="neutral" />
      <KpiAnimated label="训练样本" :value="nTrainRuns" suffix="个" delta="priority scenarios" delta-class="neutral" />
    </section>

    <!-- AI 增强求解架构 -->
    <section class="content-grid single">
      <PanelCard title="AI 融合增强架构" subtitle="AI 不替代优化，而是在各环节增强运筹优化 (AI4OPT)" badge="AI4OPT" badge-class="ok">
        <p class="thesis">{{ ai.thesis }}</p>
        <div class="pipeline">
          <div class="stage" v-for="(stage, i) in stages" :key="i">
            <div class="stage-dot" :style="{ background: stage.color }">{{ stage.icon }}</div>
            <div class="stage-name">{{ stage.name }}</div>
          </div>
        </div>
      </PanelCard>
    </section>

    <!-- v3.0 AI warm start 实施细节 ───────────────────────────────────── -->
    <section class="content-grid stagger">
      <PanelCard title="AI warm start (XGBoost)" subtitle="今日核心创新：v3.0 主求解器 7.3× 加速"
                 badge="Core Innovation" badge-class="ok">
        <StatusList :items="warmstartItems" />
      </PanelCard>
      <PanelCard title="AI 联合 warm start 设施" subtitle="site + type + capacity 联合 MIP Start 组合">
        <div class="topk-list">
          <span v-for="fac in warmFacilities" :key="`${fac.site}-${fac.type}-${fac.capacity_idx}`" class="topk-chip">
            {{ fac.site }}/{{ fac.type }}/{{ fac.capacity }}t
          </span>
        </div>
        <p class="boundary-note">联合 warm start 会为每个候选站点补齐 type 与 capacity，再作为 z 变量的 MIP Start 注入 Gurobi。</p>
      </PanelCard>
    </section>

    <section class="content-grid single">
      <PanelCard title="Optuna 自动调参" subtitle="搜索 XGBoost / warm start / Gurobi 参数以强化加速证据"
                 badge="HPO" badge-class="ok">
        <StatusList :items="optunaItems" />
        <p class="boundary-note">{{ optunaBoundary }}</p>
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard
        v-for="(layer, i) in ai.layers"
        :key="i"
        :title="layer.tech"
        :subtitle="layer.model"
        :badge="layer.stage"
        :badge-class="badgeClass(i)"
      >
        <div class="ai-what">{{ layer.what }}</div>
        <div class="ai-file">📄 {{ layer.file }}</div>
        <div class="ai-boundary">⚠ {{ layer.boundary }}</div>
      </PanelCard>
    </section>

    <section class="content-grid single">
      <PanelCard title="受控 cut ranking / robustness 结论" subtitle="Benders 子线：学习式策略 vs 朴素对照（同实例校准）" badge="Honest" badge-class="warn">
        <StatusList :items="experimentItems" />
        <p class="boundary-note">{{ ai.claim_boundary }}</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import { safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const ai = computed(() => (b.value || {}).ai_fusion || { layers: [], thesis: '', claim_boundary: '' })
const warm = computed(() => (b.value || {}).ai_warmstart_report || {})
const four = computed(() => (b.value || {}).v3_four_methods_report || {})

// ── KPI ─────────────────────────────────────────────────────────────────────
const speedup = computed(() => Number(four.value?.ai_speedup_vs_direct || warm.value?.speedup || 0))
const coldT = computed(() => Number(warm.value?.cold_start?.elapsed_sec || 0).toFixed(1))
const aiT = computed(() => Number(warm.value?.ai_warm?.elapsed_sec || 0).toFixed(1))
const timeReduce = computed(() => {
  const c = Number(warm.value?.cold_start?.elapsed_sec || 0)
  const a = Number(warm.value?.ai_warm?.elapsed_sec || 0)
  return Math.round(c - a)
})
const exactObj = computed(() => Number(warm.value?.ai_warm?.objective || 0))
const nTrainRuns = computed(() => Number(warm.value?.training?.n_runs_used || 0))
const topK = computed(() => safeArray(warm.value?.ai_top_k))
const warmFacilities = computed(() => safeArray(warm.value?.ai_warm_facilities || warm.value?.ai_warm?.warm_facilities))
const optunaBest = computed(() => warm.value?.optuna_best_trial || {})
const optunaBoundary = computed(() =>
  warm.value?.optuna_claim_boundary || 'Optuna 结果未生成时保持空状态；最终可行性和 gap 仍由 Gurobi 认证。',
)

// ── warm start 实施细节 ─────────────────────────────────────────────────────
const warmstartItems = computed(() => {
  const t = warm.value?.training || {}
  const cold = warm.value?.cold_start || {}
  const ai = warm.value?.ai_warm || {}
  return [
    { label: '模型', value: 'XGBoost binary classifier (80 trees)' },
    { label: '特征', value: `${t.n_features || 12} 维结构特征（产量/距离/坐标等）` },
    { label: '训练数据', value: `${t.n_runs_used || 0} 个 priority scenario runs` },
    { label: '联合策略', value: warm.value?.joint_strategy || 'site ranking + facility template' },
    { label: '联合设施数', value: `${ai.warm_facilities_injected || safeArray(warm.value?.ai_warm_facilities).length || 0}` },
    { label: '冷启动求解', value: `${cold.elapsed_sec || '-'}s, gap ${(cold.mip_gap_pct || 0).toFixed(2)}%` },
    { label: 'AI warm 求解', value: `${ai.elapsed_sec || '-'}s, gap ${(ai.mip_gap_pct || 0).toFixed(2)}%`, className: 'ok' },
    { label: '加速比', value: `${speedup.value.toFixed(2)}× (vs Gurobi 直解)`, className: 'ok' },
  ]
})

const stages = [
  { name: '参数生成 (ML)', icon: '🤖', color: '#6366f1' },
  { name: '模型构建 (DL/GNN)', icon: '🧠', color: '#0ea5e9' },
  { name: '求解加速 (XGBoost)', icon: '⚡', color: '#dc2626' },
  { name: '自动调参 (Optuna)', icon: '◎', color: '#7c3aed' },
  { name: '精确求解 (Gurobi)', icon: '🎯', color: '#16a34a' },
]

function badgeClass(i) { return ['neutral', 'ok', 'warn'][i % 3] }

const experimentItems = computed(() => {
  const v = ai.value?.controlled_experiment || {}
  const q = v.quality || {}
  const items = [
    { label: 'conclusion', value: v.conclusion || '-' },
  ]
  for (const p of ['all_cuts', 'learned_K', 'recency_K', 'random_K']) {
    if (q[p]) {
      items.push({
        label: `${p} 求解到最优`,
        value: `${q[p].all_solved_to_optimal_count}/${q[p].instances}`,
        className: p === 'all_cuts' || p === 'learned_K' ? 'ok' : 'warn',
      })
    }
  }
  return items
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
    { label: '状态', value: warm.value?.optuna_available ? '已生成 Optuna study' : '等待运行 experiments/ai_warmstart_optuna.py', className: warm.value?.optuna_available ? 'ok' : 'warn' },
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
</script>

<style scoped>
.thesis { font-size: 14px; color: #1e293b; line-height: 1.7; background: rgba(99,102,241,0.07); border-radius: 10px; padding: 14px 16px; }
.pipeline { display: flex; align-items: center; justify-content: space-around; margin-top: 20px; flex-wrap: wrap; gap: 10px; }
.stage { display: flex; flex-direction: column; align-items: center; gap: 8px; position: relative; }
.stage-dot { width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; box-shadow: 0 6px 16px rgba(0,0,0,0.15); animation: pulse 2.4s ease-in-out infinite; }
.stage-name { font-size: 12px; color: #475569; font-weight: 600; }
.ai-what { font-size: 13px; color: #334155; line-height: 1.6; }
.ai-file { font-size: 11px; color: #6366f1; margin-top: 10px; font-family: monospace; }
.ai-boundary { font-size: 11px; color: #d97706; margin-top: 8px; line-height: 1.5; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; }
.topk-list { display: flex; gap: 8px; flex-wrap: wrap; padding: 10px 0; }
.topk-chip { background: linear-gradient(135deg, #dc2626, #f59e0b); color: white; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 13px; box-shadow: 0 2px 8px rgba(220,38,38,0.3); }
@keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.08); } }
</style>
