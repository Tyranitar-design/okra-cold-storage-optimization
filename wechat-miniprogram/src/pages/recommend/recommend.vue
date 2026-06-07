<template>
  <view class="recommend-container">
    <!-- 头部 -->
    <view class="hero">
      <text class="hero-title">⭐ AI 选址推荐</text>
      <text class="hero-subtitle">Optuna 加速证据 · AI-Benders 融合机制</text>
    </view>

    <!-- 方法切换 -->
    <view class="method-card">
      <text class="method-title">AI 选址方法</text>
      <view class="method-tabs">
        <view class="method-tab" :class="{ active: selectedMethod === 'optuna' }" @tap="selectedMethod = 'optuna'">
          <text class="method-tab-name">Optuna Warm Start</text>
          <text class="method-tab-desc">主加速证据</text>
        </view>
        <view class="method-tab" :class="{ active: selectedMethod === 'benders' }" @tap="selectedMethod = 'benders'">
          <text class="method-tab-name">AI 融合增强 Benders</text>
          <text class="method-tab-desc">cut ranking / robustness</text>
        </view>
      </view>
    </view>

    <!-- Optuna 证据卡 -->
    <view class="evidence-card" v-if="selectedMethod === 'optuna'">
      <view class="evidence-head">
        <view>
          <text class="evidence-title">Optuna AI warm start 证据</text>
          <text class="evidence-subtitle">{{ evidenceStatus }}</text>
        </view>
        <button class="refresh-btn" size="mini" @tap="loadEvidence" :loading="evidenceLoading">刷新</button>
      </view>
      <view class="evidence-grid">
        <view class="evidence-item">
          <text class="evidence-value">#{{ bestTrialNumber }}</text>
          <text class="evidence-label">best trial</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">{{ bestSpeedup }}</text>
          <text class="evidence-label">正式加速</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">{{ recheckSpeedup }}</text>
          <text class="evidence-label">固定复核</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">{{ historicalSpeedup }}</text>
          <text class="evidence-label">历史参考</text>
        </view>
      </view>
      <text class="evidence-boundary">{{ optunaBoundary }}</text>
    </view>

    <!-- AI 可视化 -->
    <view class="visual-card" v-if="selectedMethod === 'optuna'">
      <view class="visual-head">
        <text class="visual-title">AI 加速证据可视化</text>
        <text class="visual-subtitle">Optuna study · fixed recheck · historical reference</text>
      </view>
      <view class="bar-list">
        <view class="bar-row" v-for="bar in speedupBars" :key="bar.label">
          <view class="bar-meta">
            <text class="bar-label">{{ bar.label }}</text>
            <text class="bar-value">{{ bar.text }}</text>
          </view>
          <view class="bar-track">
            <view class="bar-fill" :class="bar.className" :style="{ width: bar.width }"></view>
          </view>
        </view>
      </view>
      <view class="trial-grid">
        <view class="trial-item">
          <text class="trial-value">{{ trialStats.single }}</text>
          <text class="trial-label">单目标 trials</text>
        </view>
        <view class="trial-item">
          <text class="trial-value">{{ trialStats.multi }}</text>
          <text class="trial-label">多目标 trials</text>
        </view>
        <view class="trial-item">
          <text class="trial-value">{{ trialStats.pareto }}</text>
          <text class="trial-label">Pareto 前沿</text>
        </view>
      </view>
      <view class="pipeline">
        <view class="pipeline-step" v-for="(step, idx) in optunaPipeline" :key="step.title">
          <text class="pipeline-num">{{ idx + 1 }}</text>
          <view class="pipeline-body">
            <text class="pipeline-title">{{ step.title }}</text>
            <text class="pipeline-desc">{{ step.desc }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="visual-card benders-visual" v-else>
      <view class="visual-head">
        <text class="visual-title">AI-Benders 机制图</text>
        <text class="visual-subtitle">解释 cut ranking 如何辅助分解求解</text>
      </view>
      <view class="benders-flow">
        <view class="flow-node" v-for="step in bendersFlow" :key="step.title">
          <text class="flow-icon">{{ step.icon }}</text>
          <text class="flow-title">{{ step.title }}</text>
          <text class="flow-desc">{{ step.desc }}</text>
        </view>
      </view>
      <view class="claim-strip">
        <text class="claim-good">可展示：cut 优先级 / 鲁棒管理</text>
        <text class="claim-warn">不写成：通用显著加速</text>
      </view>
    </view>

    <!-- AI-Benders 证据卡 -->
    <view class="evidence-card benders-card" v-if="selectedMethod === 'benders'">
      <view class="evidence-head">
        <view>
          <text class="evidence-title">AI 融合增强 Benders</text>
          <text class="evidence-subtitle">机制创新 · cut ranking · 鲁棒优先级管理</text>
        </view>
        <text class="method-badge">保守口径</text>
      </view>
      <view class="evidence-grid benders-grid">
        <view class="evidence-item">
          <text class="evidence-value">Cut</text>
          <text class="evidence-label">排序管理</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">Residual</text>
          <text class="evidence-label">神经评分器</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">Robust</text>
          <text class="evidence-label">鲁棒解释</text>
        </view>
        <view class="evidence-item">
          <text class="evidence-value">No Claim</text>
          <text class="evidence-label">不夸大加速</text>
        </view>
      </view>
      <text class="evidence-boundary">{{ bendersBoundary }}</text>
    </view>

    <!-- 输入表单 -->
    <view class="form-card">
      <view class="form-section">
        <text class="form-label">🌾 年产量（吨）</text>
        <input class="form-input" v-model="production" type="digit" placeholder="例如 588" />
      </view>
      <view class="form-section">
        <text class="form-label">📍 所在区域</text>
        <picker class="form-picker" :range="regions" @change="e => region = regions[e.detail.value]">
          <view class="picker-text">{{ region || '请选择区域（体验用）' }}</view>
        </picker>
      </view>
      <view class="form-section">
        <text class="form-label">🎯 优化目标</text>
        <view class="radio-group">
          <view class="radio-chip" :class="{ active: objective === 'cost' }" @tap="objective = 'cost'">最低成本</view>
          <view class="radio-chip" :class="{ active: objective === 'balanced' }" @tap="objective = 'balanced'">均衡优化</view>
          <view class="radio-chip" :class="{ active: objective === 'speed' }" @tap="objective = 'speed'">最快求解</view>
        </view>
      </view>
      <button class="submit-btn" @tap="onRecommend" :loading="loading">
        {{ loading ? '⏳ 正在读取证据...' : submitLabel }}
      </button>
    </view>

    <!-- 结果区 -->
    <view class="result-section" v-if="result">
      <view class="result-hero">
        <text class="result-hero-num">{{ result.speedup }}</text>
        <text class="result-hero-label">{{ result.speedupLabel || 'AI 加速比 · same objective/gap' }}</text>
      </view>

      <view class="result-summary">
        <view class="rs-item">
          <text class="rs-value">{{ result.totalCost }}</text>
          <text class="rs-label">预估最优总成本（元）</text>
        </view>
        <view class="rs-item">
          <text class="rs-value">{{ result.sites.length }}</text>
          <text class="rs-label">推荐设施数</text>
        </view>
      </view>

      <text class="result-subtitle">📋 推荐设施方案</text>
      <view class="site-card" v-for="(site, i) in result.sites" :key="i">
        <view class="site-left">
          <text class="site-rank">{{ i + 1 }}</text>
        </view>
        <view class="site-body">
          <view class="site-header">
            <text class="site-name">{{ site.name }}</text>
            <text class="site-type" :style="{ background: typeColor(site.type) }">{{ site.type }}</text>
          </view>
          <view class="site-meta">
            <text>容量 <text class="meta-val">{{ site.capacity }}吨</text></text>
            <text class="meta-divider">|</text>
            <text>年成本 <text class="meta-val">{{ site.cost }}万</text></text>
          </view>
          <text class="site-reason">{{ site.reason }}</text>
        </view>
      </view>

      <view class="note-box">
        <text class="note-text">* 移动端展示正式证据与推荐方案，不直接运行 Gurobi/Optuna</text>
        <text class="note-text">{{ result.boundary || optunaBoundary }}</text>
      </view>
    </view>
  </view>
</template>

<script>
import api from '@/api/index.js'
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      production: '',
      region: '',
      regions: ['湖南 J 县（主案例）', '芦溪县（跨区域验证·2.70×加速）'],
      objective: 'balanced',
      selectedMethod: 'optuna',
      loading: false,
      evidenceLoading: false,
      evidenceReport: null,
      result: null,
    }
  },
  computed: {
    evidenceStatus() {
      if (this.evidenceReport?.optuna_available) return '正式 study 已读取 · same objective/gap'
      if (this.evidenceLoading) return '正在读取后端证据'
      return '后端暂不可用，显示本地证据兜底'
    },
    bestTrialNumber() {
      return this.evidenceReport?.optuna_best_trial?.number ?? 21
    },
    bestSpeedup() {
      return this.formatSpeedup(this.evidenceReport?.optuna_best_speedup, '5.6498×')
    },
    recheckSpeedup() {
      const stats = this.evidenceReport?.optuna_recheck_stats || {}
      const reps = this.evidenceReport?.optuna_recheck_replications || []
      return this.formatSpeedup(stats.speedup_vs_cold_mean || reps[0]?.speedup_vs_cold, '4.8364×')
    },
    historicalSpeedup() {
      return this.formatSpeedup(this.evidenceReport?.optuna_historical_best_speedup, '7.18×')
    },
    optunaBoundary() {
      return this.evidenceReport?.optuna_claim_boundary
        || this.evidenceReport?.claim_boundary
        || 'Optuna 优化求解配置与初始解质量；最终解、gap 与可行性仍由 Gurobi 认证。'
    },
    bendersBoundary() {
      return 'AI 融合增强 Benders 当前作为 cut ranking / robustness 机制创新展示，不声称已获得通用显著加速；最终可行性与 gap 仍由 Gurobi/精确求解链认证。'
    },
    submitLabel() {
      return this.selectedMethod === 'optuna' ? '🚀 生成 Optuna 展示方案' : '🧠 生成 AI-Benders 机制方案'
    },
    speedupBars() {
      const formal = this.numericSpeedup(this.evidenceReport?.optuna_best_speedup, 5.6498)
      const recheck = this.numericSpeedup(this.evidenceReport?.optuna_recheck_stats?.speedup_vs_cold_mean, 4.8364)
      const historical = this.numericSpeedup(this.evidenceReport?.optuna_historical_best_speedup, 7.18)
      const max = Math.max(formal, recheck, historical, 1)
      return [
        { label: '正式 best trial', text: `${formal.toFixed(2)}×`, width: `${Math.max(10, formal / max * 100).toFixed(1)}%`, className: 'formal' },
        { label: '固定配置复核', text: `${recheck.toFixed(2)}×`, width: `${Math.max(10, recheck / max * 100).toFixed(1)}%`, className: 'recheck' },
        { label: '历史最高参考', text: `${historical.toFixed(2)}×`, width: `${Math.max(10, historical / max * 100).toFixed(1)}%`, className: 'history' },
      ]
    },
    trialStats() {
      const r = this.evidenceReport || {}
      return {
        single: `${r.optuna_single_trial_complete_count ?? 24}/${r.optuna_n_trials_requested ?? 24}`,
        multi: `${r.optuna_multi_trial_complete_count ?? 6}/${r.optuna_multi_trials_requested ?? 6}`,
        pareto: String(r.optuna_pareto_front_size ?? 1),
      }
    },
    optunaPipeline() {
      return [
        { title: 'XGBoost 排序', desc: '根据产量、距离和覆盖特征预测候选点优先级' },
        { title: 'Optuna 搜索', desc: '自动调 XGBoost、top_k、warm strategy 与 Gurobi 参数' },
        { title: 'MIP Warm Start', desc: '把 AI 推荐站点注入精确求解器作为初始解' },
        { title: 'Gurobi 认证', desc: '最终可行性、目标值和 gap 仍由精确求解器确认' },
      ]
    },
    bendersFlow() {
      return [
        { icon: '①', title: '主问题', desc: '生成候选布局与分解结构' },
        { icon: '②', title: '子问题', desc: '检查分配/容量并产生 cuts' },
        { icon: '③', title: 'AI 评分', desc: 'Residual scorer 学习 cut 优先级' },
        { icon: '④', title: '鲁棒管理', desc: '保留关键 cuts，避免硬丢弃破坏收敛' },
      ]
    },
  },
  onLoad() {
    this.loadEvidence()
  },
  methods: {
    formatSpeedup(value, fallback) {
      const n = Number(value)
      if (!Number.isFinite(n) || n <= 0) return fallback
      return `${n.toFixed(4)}×`
    },
    numericSpeedup(value, fallback) {
      const n = Number(value)
      return Number.isFinite(n) && n > 0 ? n : fallback
    },
    typeColor(type) {
      return { '预冷库': '#0EA5E9', '冷藏库': '#0F766E', '气调库': '#8B5CF6', '冷冻库': '#6366F1' }[type] || '#64748B'
    },
    async loadEvidence() {
      this.evidenceLoading = true
      try {
        const report = await api.getAiWarmstartReport()
        if (report?.optuna_available || report?.available) this.evidenceReport = report
      } catch (e) {
        // keep local fallback
      } finally {
        this.evidenceLoading = false
      }
    },
    buildEvidenceResult(source = null) {
      const fallback = source?.sites?.length ? source : mockData.recommendFallback
      if (this.selectedMethod === 'benders') {
        return {
          ...fallback,
          sites: fallback.sites.map((site, idx) => ({
            ...site,
            reason: idx < 3
              ? `AI-Benders cut ranking 关注的关键设施：${site.reason}`
              : `鲁棒优先级管理保留候选：${site.reason}`,
          })),
          speedup: 'Cut Ranking',
          speedupLabel: 'AI 融合增强 Benders · robustness / priority management',
          boundary: this.bendersBoundary,
        }
      }
      const result = {
        ...fallback,
        sites: [...fallback.sites],
        speedup: source?.speedup || this.bestSpeedup,
        speedupLabel: 'Optuna best trial · same objective/gap',
        boundary: this.optunaBoundary,
      }
      if (this.region.includes('芦溪') && !source?.speedup) {
        result.speedup = '2.70×'
        result.speedupLabel = '跨区域验证参考 · same objective/gap'
      }
      if (this.evidenceReport?.optuna_best_trial?.objective) {
        result.totalCost = Number(this.evidenceReport.optuna_best_trial.objective).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
      }
      return result
    },
    async onRecommend() {
      if (!this.production) { uni.showToast({ title: '请输入年产量', icon: 'none' }); return }
      this.loading = true
      try {
        if (!this.evidenceReport) await this.loadEvidence()
        const data = await api.getRecommend({
          production_ton: parseFloat(this.production),
          region: this.region,
          objective: this.objective,
        })
        if (data?.sites?.length) {
          this.result = this.buildEvidenceResult(data)
          this.loading = false
          return
        }
      } catch (e) { /* fallback */ }
      setTimeout(() => {
        this.result = this.buildEvidenceResult()
        this.loading = false
      }, 1500)
    }
  }
}
</script>

<style>
.recommend-container { padding: 0 24rpx 40rpx; background: #F8FAFC; min-height: 100vh; }
.hero { background: linear-gradient(135deg, #D97706, #F59E0B); margin: 0 -24rpx 30rpx; padding: 50rpx 40rpx 40rpx; }
.hero-title { font-size: 40rpx; font-weight: bold; color: #FFF; display: block; }
.hero-subtitle { font-size: 22rpx; color: rgba(255,255,255,0.8); margin-top: 8rpx; display: block; }
.method-card { background: #FFF; border-radius: 16rpx; padding: 24rpx; margin-bottom: 24rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.method-title { font-size: 28rpx; font-weight: 800; color: #1E293B; display: block; margin-bottom: 16rpx; }
.method-tabs { display: flex; gap: 14rpx; }
.method-tab { flex: 1; border: 1rpx solid #CBD5E1; border-radius: 14rpx; padding: 18rpx 14rpx; background: #F8FAFC; }
.method-tab.active { border-color: #0F766E; background: #ECFDF5; box-shadow: 0 0 0 2rpx rgba(15,118,110,0.08); }
.method-tab-name { font-size: 24rpx; font-weight: 700; color: #1E293B; display: block; line-height: 1.35; }
.method-tab.active .method-tab-name { color: #0F766E; }
.method-tab-desc { font-size: 20rpx; color: #64748B; margin-top: 6rpx; display: block; line-height: 1.35; }
.evidence-card { background: #FFF; border-radius: 16rpx; padding: 28rpx; margin-bottom: 24rpx; border: 1rpx solid #FED7AA; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.benders-card { border-color: #BFDBFE; }
.evidence-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16rpx; margin-bottom: 20rpx; }
.evidence-title { font-size: 30rpx; font-weight: 700; color: #1E293B; display: block; }
.evidence-subtitle { font-size: 22rpx; color: #64748B; margin-top: 4rpx; display: block; }
.refresh-btn { margin: 0; padding: 0 18rpx; height: 56rpx; line-height: 56rpx; font-size: 22rpx; color: #D97706; background: #FFF7ED; border-radius: 10rpx; }
.method-badge { font-size: 21rpx; color: #1D4ED8; background: #DBEAFE; border-radius: 999rpx; padding: 8rpx 16rpx; white-space: nowrap; }
.evidence-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12rpx; margin-bottom: 16rpx; }
.evidence-item { background: #FFFBEB; border-radius: 12rpx; padding: 18rpx 8rpx; text-align: center; }
.benders-grid .evidence-item { background: #EFF6FF; }
.evidence-value { font-size: 28rpx; font-weight: 800; color: #F97316; display: block; }
.benders-grid .evidence-value { color: #2563EB; }
.evidence-label { font-size: 20rpx; color: #92400E; margin-top: 4rpx; display: block; }
.benders-grid .evidence-label { color: #1E40AF; }
.evidence-boundary { font-size: 21rpx; color: #64748B; line-height: 1.6; display: block; }
.visual-card { background: #FFF; border-radius: 16rpx; padding: 28rpx; margin-bottom: 24rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); border: 1rpx solid #E2E8F0; }
.visual-head { margin-bottom: 20rpx; }
.visual-title { display: block; color: #1E293B; font-size: 30rpx; font-weight: 800; }
.visual-subtitle { display: block; margin-top: 4rpx; color: #64748B; font-size: 21rpx; }
.bar-list { display: flex; flex-direction: column; gap: 16rpx; }
.bar-row { display: flex; flex-direction: column; gap: 8rpx; }
.bar-meta { display: flex; justify-content: space-between; align-items: center; gap: 16rpx; }
.bar-label { color: #334155; font-size: 23rpx; font-weight: 700; }
.bar-value { color: #0F766E; font-size: 24rpx; font-weight: 800; }
.bar-track { height: 18rpx; background: #E2E8F0; border-radius: 999rpx; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999rpx; }
.bar-fill.formal { background: linear-gradient(90deg, #0F766E, #14B8A6); }
.bar-fill.recheck { background: linear-gradient(90deg, #2563EB, #60A5FA); }
.bar-fill.history { background: linear-gradient(90deg, #F97316, #FBBF24); }
.trial-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12rpx; margin: 24rpx 0; }
.trial-item { background: #F8FAFC; border-radius: 12rpx; padding: 18rpx 8rpx; text-align: center; border: 1rpx solid #E2E8F0; }
.trial-value { display: block; color: #1E293B; font-size: 30rpx; font-weight: 800; }
.trial-label { display: block; margin-top: 4rpx; color: #64748B; font-size: 20rpx; }
.pipeline { border-left: 4rpx solid #CCFBF1; padding-left: 18rpx; }
.pipeline-step { display: flex; gap: 14rpx; margin-bottom: 18rpx; }
.pipeline-step:last-child { margin-bottom: 0; }
.pipeline-num { width: 38rpx; height: 38rpx; line-height: 38rpx; text-align: center; border-radius: 50%; background: #0F766E; color: #FFF; font-size: 22rpx; font-weight: 800; flex-shrink: 0; }
.pipeline-body { flex: 1; }
.pipeline-title { display: block; color: #1E293B; font-size: 24rpx; font-weight: 800; }
.pipeline-desc { display: block; margin-top: 4rpx; color: #64748B; font-size: 21rpx; line-height: 1.45; }
.benders-visual { border-color: #BFDBFE; }
.benders-flow { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14rpx; }
.flow-node { background: #EFF6FF; border: 1rpx solid #BFDBFE; border-radius: 14rpx; padding: 18rpx; }
.flow-icon { display: block; color: #2563EB; font-size: 30rpx; font-weight: 900; }
.flow-title { display: block; margin-top: 8rpx; color: #1E293B; font-size: 24rpx; font-weight: 800; }
.flow-desc { display: block; margin-top: 6rpx; color: #475569; font-size: 20rpx; line-height: 1.45; }
.claim-strip { display: flex; flex-direction: column; gap: 8rpx; margin-top: 18rpx; padding: 16rpx; border-radius: 12rpx; background: #F8FAFC; }
.claim-good { color: #166534; font-size: 22rpx; font-weight: 700; }
.claim-warn { color: #92400E; font-size: 22rpx; font-weight: 700; }
.form-card { background: #FFF; border-radius: 16rpx; padding: 30rpx; margin-bottom: 24rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.form-section { margin-bottom: 24rpx; }
.form-label { font-size: 26rpx; font-weight: 500; color: #1E293B; margin-bottom: 8rpx; display: block; }
.form-input { background: #F8FAFC; border-radius: 12rpx; padding: 20rpx; font-size: 28rpx; border: 1rpx solid #E2E8F0; }
.form-picker { background: #F8FAFC; border-radius: 12rpx; padding: 20rpx; border: 1rpx solid #E2E8F0; }
.picker-text { font-size: 28rpx; color: #1E293B; }
.radio-group { display: flex; gap: 12rpx; }
.radio-chip { padding: 12rpx 24rpx; border-radius: 12rpx; font-size: 24rpx; color: #64748B; background: #F1F5F9; }
.radio-chip.active { background: #0F766E; color: #FFF; }
.submit-btn { background: linear-gradient(135deg, #0F766E, #14B8A6); color: #FFF; border-radius: 12rpx; padding: 24rpx; text-align: center; font-size: 30rpx; font-weight: 500; width: 100%; margin-top: 8rpx; }
.result-hero { text-align: center; background: linear-gradient(135deg, #FFF7ED, #FFFBEB); border-radius: 16rpx; padding: 30rpx; margin-bottom: 20rpx; border: 1rpx solid #FDE68A; }
.result-hero-num { font-size: 72rpx; font-weight: bold; color: #F97316; display: block; }
.result-hero-label { font-size: 24rpx; color: #D97706; margin-top: 4rpx; display: block; }
.result-summary { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.rs-item { flex: 1; background: #FFF; border-radius: 12rpx; padding: 20rpx; text-align: center; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.rs-value { font-size: 36rpx; font-weight: bold; color: #0F766E; display: block; }
.rs-label { font-size: 22rpx; color: #64748B; margin-top: 4rpx; display: block; }
.result-subtitle { font-size: 28rpx; font-weight: bold; color: #1E293B; margin-bottom: 16rpx; display: block; }
.site-card { display: flex; background: #FFF; border-radius: 14rpx; padding: 20rpx; margin-bottom: 14rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.site-left { width: 60rpx; display: flex; align-items: center; justify-content: center; }
.site-rank { font-size: 32rpx; font-weight: bold; color: #0F766E; }
.site-body { flex: 1; }
.site-header { display: flex; align-items: center; gap: 10rpx; margin-bottom: 8rpx; }
.site-name { font-size: 28rpx; font-weight: 600; color: #1E293B; }
.site-type { font-size: 20rpx; color: #FFF; padding: 2rpx 14rpx; border-radius: 10rpx; }
.site-meta { font-size: 22rpx; color: #64748B; margin-bottom: 6rpx; }
.meta-val { color: #1E293B; font-weight: 500; }
.meta-divider { margin: 0 8rpx; color: #CBD5E1; }
.site-reason { font-size: 22rpx; color: #94A3B8; }
.note-box { background: #F8FAFC; border-radius: 12rpx; padding: 20rpx; margin-top: 20rpx; }
.note-text { font-size: 20rpx; color: #94A3B8; display: block; line-height: 1.6; }
</style>
