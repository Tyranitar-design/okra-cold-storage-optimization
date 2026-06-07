<template>
  <view class="agent-container">
    <view class="hero">
      <text class="hero-title">🤖 AI 决策助手</text>
      <text class="hero-subtitle">证据驱动 · 只读解释 · 可控跳转</text>
    </view>

    <view class="api-config">
      <input class="api-input" v-model="apiBaseUrl" placeholder="http://电脑局域网IP:8000/api/v1" />
      <button class="api-save" size="mini" @tap="saveBaseUrl">保存</button>
    </view>

    <view class="ai-check-card">
      <view class="ai-check-head">
        <view>
          <text class="ai-check-title">AI 功能验收</text>
          <text class="ai-check-subtitle">{{ aiProbeStatus }}</text>
        </view>
        <button class="probe-btn" size="mini" :loading="aiProbeLoading" @tap="loadAiProbe">检测</button>
      </view>
      <view class="probe-grid">
        <view class="probe-item" v-for="item in aiProbeCards" :key="item.label">
          <text class="probe-value" :class="item.level">{{ item.value }}</text>
          <text class="probe-label">{{ item.label }}</text>
        </view>
      </view>
      <view class="probe-bars">
        <view class="probe-bar-row" v-for="bar in aiProbeBars" :key="bar.label">
          <view class="probe-bar-meta">
            <text class="probe-bar-label">{{ bar.label }}</text>
            <text class="probe-bar-value">{{ bar.text }}</text>
          </view>
          <view class="probe-bar-track">
            <view class="probe-bar-fill" :class="bar.className" :style="{ width: bar.width }"></view>
          </view>
        </view>
      </view>
    </view>

    <scroll-view class="message-list" scroll-y>
      <view v-for="(msg, idx) in messages" :key="idx" class="message" :class="msg.role">
        <view class="bubble">
          <text class="msg-text">{{ msg.content }}</text>

          <view v-if="msg.cards && msg.cards.length" class="cards">
            <view class="status-card" v-for="card in msg.cards" :key="card.title">
              <view class="card-head">
                <text class="card-title">{{ card.title }}</text>
                <text class="card-tag" :class="card.level">{{ card.value }}</text>
              </view>
              <text class="card-detail">{{ card.detail }}</text>
            </view>
          </view>

          <view v-if="msg.evidence_refs && msg.evidence_refs.length" class="evidence">
            <text class="evidence-title">证据引用</text>
            <view class="evidence-item" v-for="ref in msg.evidence_refs" :key="`${ref.source}-${ref.title}`">
              <view class="evidence-main">
                <text class="evidence-name">{{ ref.title }}</text>
                <text class="evidence-detail">{{ ref.value }} · {{ ref.detail }}</text>
                <text class="evidence-source">{{ ref.source }}</text>
              </view>
              <text v-if="ref.route" class="evidence-link" @tap="openRoute(ref.route)">查看</text>
            </view>
          </view>

          <view v-if="msg.claim_boundary" class="boundary">
            <text>{{ msg.claim_boundary }}</text>
          </view>

          <view v-if="msg.actions && msg.actions.length" class="actions">
            <button
              v-for="action in msg.actions"
              :key="`${action.type}-${action.route}`"
              class="action-btn"
              @tap="runAction(action)"
            >
              {{ action.label }}
            </button>
          </view>
        </view>
      </view>
    </scroll-view>

    <view class="suggestions">
      <text
        v-for="item in suggestions"
        :key="item"
        class="suggestion"
        @tap="ask(item)"
      >
        {{ item }}
      </text>
    </view>

    <view class="input-row">
      <input class="input" v-model="draft" confirm-type="send" placeholder="问我 Optuna、AI-Benders、论文口径..." @confirm="send" />
      <button class="send-btn" :loading="loading" @tap="send">发送</button>
    </view>
  </view>
</template>

<script>
import api, { getBaseUrl, setBaseUrl } from '@/api/index.js'

const ROUTE_MAP = {
  '/ai': '/pages/recommend/recommend',
  '/aisolve': '/pages/recommend/recommend',
  '/solve': '/pages/recommend/recommend',
  '/weather': '/pages/weather/weather',
  '/export': '/pages/recommend/recommend',
  '/overview': '/pages/index/index',
  '/pareto': '/pages/recommend/recommend',
  '/whatif': '/pages/recommend/recommend',
}

function fallbackAgentResponse(text) {
  const normalized = text.toLowerCase()
  const commonBoundary = '移动端离线证据兜底仅用于展示；最终可行性、gap 与目标值仍以 FastAPI 报告和 Gurobi 认证结果为准。'
  const base = {
    evidence_refs: [
      {
        source: 'mobile-local-evidence',
        title: '移动端本地证据兜底',
        value: '离线可展示',
        detail: '后端不可用时保留核心汇报口径',
        route: '/aisolve',
      },
    ],
    suggestions: ['解释 Optuna AI warm start', 'AI-Benders 能不能写加速', '检查论文能怎么写', '下一步建议'],
    actions: [{ type: 'navigate', label: '查看 AI 选址推荐', route: '/aisolve' }],
  }
  if (normalized.includes('benders') || normalized.includes('加速')) {
    return {
      ...base,
      reply: 'AI-Benders 当前应作为 AI 融合机制创新展示：它负责 cut ranking、优先级管理和鲁棒性说明，不能写成已证明显著加速。主加速证据仍是 Optuna + AI warm start。',
      claim_boundary: 'AI-Benders/cut ranking 只能写“鲁棒性与优先级管理增强”；除非后续更大实验支持，否则不能声称通用显著加速。',
      cards: [
        { title: 'AI-Benders', value: '机制创新', level: 'ok', detail: '学习 cut 优先级，辅助分解求解过程解释。' },
        { title: '声明边界', value: '保守', level: 'warn', detail: '不把 cut ranking 夸大为显著加速。' },
      ],
    }
  }
  if (normalized.includes('论文') || normalized.includes('怎么写')) {
    return {
      ...base,
      reply: '论文可以写：Optuna 自动搜索 XGBoost、warm start 与 Gurobi 参数，得到 5.6498x 正式加速证据；固定配置复核为 4.8364x；历史最高 7.18x 仅作参考。不能写 AI 替代 Gurobi，也不能写本轮刷新历史最高。',
      claim_boundary: commonBoundary,
      cards: [
        { title: '可写', value: '5.6498x', level: 'ok', detail: 'Optuna 正式 study 的 clean speedup evidence。' },
        { title: '不可写', value: '替代Gurobi', level: 'warn', detail: '最终解仍由 Gurobi 认证。' },
      ],
    }
  }
  if (normalized.includes('下一步')) {
    return {
      ...base,
      reply: '下一步建议先完成手机真机验收：Agent 问答、Optuna 证据卡、AI-Benders 机制卡、天气刷新、扫码、定位和地图。若后端仍连不上，可先用离线证据展示，随后换到手机热点或放行同网段再复测。',
      claim_boundary: commonBoundary,
      cards: [
        { title: '真机验收', value: '优先', level: 'ok', detail: '先把 App 展示链路跑通并截图固化。' },
        { title: '网络排查', value: '并行', level: 'warn', detail: '100.77.* 网络可能存在终端隔离。' },
      ],
    }
  }
  return {
    ...base,
    reply: 'Optuna + AI warm start 是当前主加速证据：正式 24-trial study 的 best trial #21 达到 5.6498x，固定 best 配置复核为 4.8364x；历史最高 7.18x 没有被本轮刷新。AI 只增强初始解和配置搜索，最终仍由 Gurobi 认证。',
    claim_boundary: commonBoundary,
    cards: [
      { title: 'Optuna 正式实验', value: '5.6498x', level: 'ok', detail: 'best trial #21，gap=0.0%，目标值不劣化。' },
      { title: '固定配置复核', value: '4.8364x', level: 'ok', detail: '说明 best 配置存在正常求解时间波动但仍 clean acceleration。' },
      { title: '历史参考', value: '7.18x', level: 'warn', detail: '本轮未刷新历史最高，汇报口径要诚实。' },
    ],
  }
}

export default {
  data() {
    return {
      draft: '',
      apiBaseUrl: '',
      loading: false,
      aiProbe: null,
      aiProbeOnline: false,
      aiProbeLoading: false,
      suggestions: ['解释 Optuna AI warm start', '检查论文能怎么写', 'AI-Benders 能不能写加速', '下一步建议'],
      messages: [
        {
          role: 'assistant',
          content: '您好，我是秋葵冷库优化 AI 决策助手。移动端只做证据解释和可控跳转，不会直接运行 Gurobi/Optuna。',
        },
      ],
    }
  },
  computed: {
    aiProbeStatus() {
      if (this.aiProbeLoading) return '正在连接后端 AI 证据接口'
      if (this.aiProbeOnline) return '后端在线 · AI warm start 报告已返回'
      return '后端暂不可用 · 使用移动端本地证据兜底'
    },
    aiProbeCards() {
      const report = this.aiProbe || {}
      return [
        { label: '接口状态', value: this.aiProbeOnline ? 'Online' : 'Fallback', level: this.aiProbeOnline ? 'ok' : 'warn' },
        { label: 'best trial', value: `#${report.optuna_best_trial?.number ?? 21}`, level: 'ok' },
        { label: '正式加速', value: this.formatSpeedup(report.optuna_best_speedup, '5.6498x'), level: 'ok' },
        { label: '固定复核', value: this.formatSpeedup(report.optuna_recheck_stats?.speedup_vs_cold_mean, '4.8364x'), level: 'ok' },
      ]
    },
    aiProbeBars() {
      const report = this.aiProbe || {}
      const formal = this.numericSpeedup(report.optuna_best_speedup, 5.6498)
      const recheck = this.numericSpeedup(report.optuna_recheck_stats?.speedup_vs_cold_mean, 4.8364)
      const historical = this.numericSpeedup(report.optuna_historical_best_speedup, 7.18)
      const max = Math.max(formal, recheck, historical, 1)
      return [
        { label: 'Optuna 正式 study', text: `${formal.toFixed(2)}x`, width: `${Math.max(10, formal / max * 100).toFixed(1)}%`, className: 'formal' },
        { label: '固定配置复核', text: `${recheck.toFixed(2)}x`, width: `${Math.max(10, recheck / max * 100).toFixed(1)}%`, className: 'recheck' },
        { label: '历史参考', text: `${historical.toFixed(2)}x`, width: `${Math.max(10, historical / max * 100).toFixed(1)}%`, className: 'history' },
      ]
    },
  },
  onLoad() {
    this.apiBaseUrl = getBaseUrl()
    this.loadAiProbe()
  },
  methods: {
    formatSpeedup(value, fallback) {
      const n = Number(value)
      if (!Number.isFinite(n) || n <= 0) return fallback
      return `${n.toFixed(4)}x`
    },
    numericSpeedup(value, fallback) {
      const n = Number(value)
      return Number.isFinite(n) && n > 0 ? n : fallback
    },
    async loadAiProbe() {
      this.aiProbeLoading = true
      const report = await api.getAiWarmstartReport()
      this.aiProbeLoading = false
      if (report?.optuna_available || report?.available) {
        this.aiProbe = report
        this.aiProbeOnline = true
        return
      }
      this.aiProbe = null
      this.aiProbeOnline = false
    },
    saveBaseUrl() {
      const url = this.apiBaseUrl.trim()
      if (!url) {
        uni.showToast({ title: '请输入后端地址', icon: 'none' })
        return
      }
      setBaseUrl(url)
      this.apiBaseUrl = getBaseUrl()
      uni.showToast({ title: '后端地址已保存', icon: 'success' })
      this.loadAiProbe()
    },
    ask(text) {
      this.draft = text
      this.send()
    },
    async send() {
      const text = this.draft.trim()
      if (!text || this.loading) return
      this.messages.push({ role: 'user', content: text })
      this.draft = ''
      this.loading = true
      const data = await api.chatAgent(text, { platform: 'uni-app', page: 'agent' })
      this.loading = false
      if (!data) {
        const fallback = fallbackAgentResponse(text)
        this.messages.push({
          role: 'assistant',
          content: `${fallback.reply}\n\n当前为本地证据兜底：如果要读取实时后端，请确认手机和电脑在可互访网络，并放行 8014 端口。`,
          cards: fallback.cards || [],
          evidence_refs: fallback.evidence_refs || [],
          claim_boundary: fallback.claim_boundary || '',
          actions: fallback.actions || [],
        })
        this.suggestions = fallback.suggestions
        return
      }
      this.messages.push({
        role: 'assistant',
        content: data.reply || '我已处理这条请求。',
        cards: data.cards || [],
        evidence_refs: data.evidence_refs || [],
        claim_boundary: data.claim_boundary || '',
        actions: data.actions || [],
      })
      if (data.suggestions && data.suggestions.length) this.suggestions = data.suggestions
    },
    runAction(action) {
      if (action.type === 'refresh') {
        uni.showToast({ title: '请返回首页下拉刷新', icon: 'none' })
        return
      }
      if (action.type && action.type.indexOf('confirm') === 0) {
        uni.showModal({
          title: '请确认',
          content: action.detail || '该动作需要确认后跳转。',
          success: (res) => {
            if (res.confirm) this.openRoute(action.route)
          },
        })
        return
      }
      this.openRoute(action.route)
    },
    openRoute(route) {
      const url = ROUTE_MAP[route] || route
      if (!url || url.indexOf('/pages/') !== 0) return
      const tabs = ['/pages/index/index', '/pages/layout/layout', '/pages/recommend/recommend', '/pages/weather/weather']
      if (tabs.includes(url)) uni.switchTab({ url })
      else uni.navigateTo({ url })
    },
  },
}
</script>

<style>
.agent-container { min-height: 100vh; background: #F8FAFC; padding: 0 24rpx 32rpx; }
.hero { margin: 0 -24rpx 22rpx; padding: 48rpx 36rpx 32rpx; background: linear-gradient(135deg, #0F766E, #2563EB); }
.hero-title { display: block; color: #FFF; font-size: 38rpx; font-weight: 800; }
.hero-subtitle { display: block; margin-top: 8rpx; color: rgba(255,255,255,0.82); font-size: 23rpx; }
.api-config { display: flex; align-items: center; gap: 12rpx; background: #FFF; border: 1rpx solid #E2E8F0; border-radius: 14rpx; padding: 12rpx; margin-bottom: 14rpx; }
.api-input { flex: 1; font-size: 22rpx; color: #334155; padding: 8rpx 10rpx; }
.api-save { margin: 0; min-width: 96rpx; height: 52rpx; line-height: 52rpx; background: #EFF6FF; color: #2563EB; border-radius: 10rpx; font-size: 21rpx; }
.ai-check-card { background: #FFF; border: 1rpx solid #CCFBF1; border-radius: 16rpx; padding: 22rpx; margin-bottom: 14rpx; box-shadow: 0 2rpx 8rpx rgba(15,23,42,0.06); }
.ai-check-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14rpx; margin-bottom: 16rpx; }
.ai-check-title { display: block; color: #1E293B; font-size: 28rpx; font-weight: 800; }
.ai-check-subtitle { display: block; margin-top: 4rpx; color: #64748B; font-size: 21rpx; line-height: 1.35; }
.probe-btn { margin: 0; min-width: 96rpx; height: 52rpx; line-height: 52rpx; color: #0F766E; background: #ECFDF5; border-radius: 10rpx; font-size: 21rpx; }
.probe-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10rpx; margin-bottom: 16rpx; }
.probe-item { background: #F8FAFC; border: 1rpx solid #E2E8F0; border-radius: 12rpx; padding: 14rpx 6rpx; text-align: center; min-width: 0; }
.probe-value { display: block; color: #0F766E; font-size: 24rpx; font-weight: 900; line-height: 1.2; word-break: break-word; }
.probe-value.warn { color: #D97706; }
.probe-value.ok { color: #0F766E; }
.probe-label { display: block; margin-top: 4rpx; color: #64748B; font-size: 18rpx; line-height: 1.25; }
.probe-bars { display: flex; flex-direction: column; gap: 10rpx; }
.probe-bar-row { display: flex; flex-direction: column; gap: 6rpx; }
.probe-bar-meta { display: flex; justify-content: space-between; align-items: center; gap: 12rpx; }
.probe-bar-label { color: #334155; font-size: 21rpx; font-weight: 700; }
.probe-bar-value { color: #0F766E; font-size: 21rpx; font-weight: 800; }
.probe-bar-track { height: 14rpx; background: #E2E8F0; border-radius: 999rpx; overflow: hidden; }
.probe-bar-fill { height: 100%; border-radius: 999rpx; }
.probe-bar-fill.formal { background: linear-gradient(90deg, #0F766E, #14B8A6); }
.probe-bar-fill.recheck { background: linear-gradient(90deg, #2563EB, #60A5FA); }
.probe-bar-fill.history { background: linear-gradient(90deg, #F97316, #FBBF24); }
.message-list { height: calc(100vh - 650rpx); }
.message { display: flex; margin-bottom: 18rpx; }
.message.user { justify-content: flex-end; }
.bubble { max-width: 88%; background: #FFF; border-radius: 18rpx; padding: 20rpx; box-shadow: 0 2rpx 8rpx rgba(15,23,42,0.06); }
.message.user .bubble { background: #0F766E; color: #FFF; }
.msg-text { font-size: 25rpx; line-height: 1.6; color: inherit; }
.cards, .evidence, .actions { margin-top: 16rpx; }
.status-card, .evidence-item { background: #F8FAFC; border: 1rpx solid #E2E8F0; border-radius: 14rpx; padding: 16rpx; margin-top: 10rpx; }
.card-head, .evidence-item { display: flex; justify-content: space-between; gap: 12rpx; }
.card-title, .evidence-name { font-size: 24rpx; font-weight: 700; color: #1E293B; }
.card-tag { font-size: 20rpx; color: #475569; background: #E2E8F0; border-radius: 20rpx; padding: 4rpx 12rpx; }
.card-tag.ok { color: #166534; background: #DCFCE7; }
.card-tag.warn { color: #92400E; background: #FEF3C7; }
.card-detail, .evidence-detail, .evidence-source { display: block; margin-top: 6rpx; color: #64748B; font-size: 21rpx; line-height: 1.45; }
.evidence-title { color: #0F766E; font-size: 22rpx; font-weight: 800; }
.evidence-main { flex: 1; }
.evidence-link { color: #2563EB; font-size: 22rpx; white-space: nowrap; }
.evidence-source { font-family: monospace; }
.boundary { margin-top: 14rpx; background: #FFF7ED; border-left: 6rpx solid #F59E0B; border-radius: 10rpx; padding: 14rpx; color: #92400E; font-size: 21rpx; line-height: 1.5; }
.action-btn { display: inline-block; margin: 10rpx 10rpx 0 0; padding: 0 20rpx; height: 58rpx; line-height: 58rpx; border-radius: 12rpx; background: #0F766E; color: #FFF; font-size: 23rpx; }
.suggestions { display: flex; gap: 10rpx; flex-wrap: wrap; margin: 14rpx 0; }
.suggestion { background: #FFF; border: 1rpx solid #CBD5E1; border-radius: 28rpx; padding: 10rpx 18rpx; color: #475569; font-size: 22rpx; }
.input-row { display: flex; gap: 12rpx; align-items: center; }
.input { flex: 1; background: #FFF; border: 1rpx solid #E2E8F0; border-radius: 14rpx; padding: 18rpx; font-size: 25rpx; }
.send-btn { width: 140rpx; height: 72rpx; line-height: 72rpx; border-radius: 14rpx; background: #0F766E; color: #FFF; font-size: 25rpx; }
</style>
