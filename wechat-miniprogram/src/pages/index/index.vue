<template>
  <view class="app-container">
    <!-- logo 区 -->
    <view class="hero">
      <image class="hero-icon" src="/static/app-icon.png" mode="aspectFit"></image>
      <view class="hero-copy">
        <text class="hero-title">秋葵冷库优化</text>
        <text class="hero-subtitle">AI 增强多目标 MIP · 县域冷链决策助手</text>
      </view>
    </view>

    <!-- KPI 卡片 -->
    <view class="kpi-grid">
      <view class="kpi-card" v-for="kpi in kpis" :key="kpi.label"
        :style="{ borderTop: `4rpx solid ${kpi.color}` }">
        <text class="kpi-value">{{ kpi.value }}</text>
        <text class="kpi-label">{{ kpi.label }}</text>
      </view>
    </view>

    <!-- 状态条 -->
    <view class="status-bar">
      <text class="status-text">📊 {{ kpiData.status }}</text>
      <text class="status-badge">v3.0</text>
    </view>

    <!-- 成本分解概览 -->
    <view class="section">
      <view class="section-header">
        <text class="section-title">💰 成本分解</text>
        <text class="section-more" @tap="navTo('layout')">查看详情 →</text>
      </view>
      <view class="cost-card">
        <view class="cost-bar-track">
          <view class="cost-bar-fill" v-for="c in costData" :key="c.label"
            :style="{ width: c.pct + '%', background: c.color }"></view>
        </view>
        <view class="cost-legend">
          <view class="cost-legend-item" v-for="c in costData" :key="c.label">
            <view class="legend-dot" :style="{ background: c.color }"></view>
            <text class="legend-label">{{ c.label }} {{ c.pct }}%</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 快速入口 -->
    <view class="section">
      <text class="section-title">🚀 快速入口</text>
      <view class="entry-grid">
        <view class="entry-card" @tap="navTo('layout')">
          <text class="entry-icon">🗺️</text>
          <text class="entry-text">冷库布局</text>
          <text class="entry-desc">选址 · 容量 · 分配</text>
        </view>
        <view class="entry-card" @tap="navTo('recommend')">
          <text class="entry-icon">⭐</text>
          <text class="entry-text">选址推荐</text>
          <text class="entry-desc">AI 智能方案</text>
        </view>
        <view class="entry-card" @tap="navTo('weather')">
          <text class="entry-icon">🌤️</text>
          <text class="entry-text">气象预警</text>
          <text class="entry-desc">冷库运行建议</text>
        </view>
        <view class="entry-card" @tap="navTo('agent')">
          <text class="entry-icon">🤖</text>
          <text class="entry-text">AI助手</text>
          <text class="entry-desc">证据 · 口径 · 建议</text>
        </view>
        <view class="entry-card" @tap="navTo('my-storage')">
          <text class="entry-icon">🏭</text>
          <text class="entry-text">我的冷库</text>
          <text class="entry-desc">库存 · 温度 · 能耗</text>
        </view>
        <view class="entry-card" @tap="navTo('logistics')">
          <text class="entry-icon">🚛</text>
          <text class="entry-text">物流路线</text>
          <text class="entry-desc">配送 · ETA</text>
        </view>
        <view class="entry-card" @tap="navTo('scan')">
          <text class="entry-icon">📷</text>
          <text class="entry-text">扫码入库</text>
          <text class="entry-desc">批次登记</text>
        </view>
      </view>
    </view>

    <!-- 加速比亮点 -->
    <view class="highlight-card">
      <view class="highlight-left">
        <text class="highlight-num">7.18×</text>
        <text class="highlight-unit">AI 加速比</text>
      </view>
      <view class="highlight-divider"></view>
      <view class="highlight-right">
        <text class="highlight-meta">Cold: 175.54s → AI: 24.44s</text>
        <text class="highlight-meta">XGBoost 80 trees · 12 维特征</text>
        <text class="highlight-meta">Same incumbent objective</text>
      </view>
    </view>
  </view>
</template>

<script>
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      kpiData: mockData.kpi,
      costData: mockData.costBreakdown,
    }
  },
  computed: {
    kpis() {
      const d = this.kpiData
      return [
        { value: d.optimalCost, label: '最优成本(元)', color: '#0F766E' },
        { value: d.speedup,     label: 'AI 加速比',    color: '#14B8A6' },
        { value: d.facilityCount, label: '开放设施',   color: '#F59E0B' },
        { value: d.mipGap,     label: 'MIP Gap',       color: '#EF4444' },
      ]
    }
  },
  onPullDownRefresh() {
    setTimeout(() => uni.stopPullDownRefresh(), 800)
  },
  methods: {
    navTo(page) {
      const tabs = ['index','layout','recommend','weather']
      const url = `/pages/${page}/${page}`
      if (tabs.includes(page)) uni.switchTab({ url })
      else uni.navigateTo({ url })
    }
  }
}
</script>

<style>
.app-container { padding: 0 24rpx 40rpx; background: #F8FAFC; min-height: 100vh; }
.hero { display: flex; align-items: center; gap: 22rpx; background: linear-gradient(135deg, #0F766E 0%, #2563EB 100%); margin: 0 -24rpx 30rpx; padding: 58rpx 40rpx 40rpx; }
.hero-icon { width: 108rpx; height: 108rpx; border-radius: 24rpx; box-shadow: 0 10rpx 24rpx rgba(15,23,42,0.18); background: #FFF; }
.hero-copy { flex: 1; min-width: 0; }
.hero-title { font-size: 40rpx; font-weight: bold; color: #FFF; display: block; }
.hero-subtitle { font-size: 24rpx; color: rgba(255,255,255,0.8); margin-top: 8rpx; display: block; }
.kpi-grid { display: flex; flex-wrap: wrap; gap: 16rpx; margin-bottom: 24rpx; }
.kpi-card { flex: 1; min-width: 40%; background: #FFF; border-radius: 16rpx; padding: 24rpx; text-align: center; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.kpi-value { font-size: 40rpx; font-weight: bold; color: #0F766E; display: block; }
.kpi-label { font-size: 22rpx; color: #64748B; margin-top: 6rpx; display: block; }
.status-bar { display: flex; align-items: center; justify-content: space-between; background: #F0FDF4; border-radius: 12rpx; padding: 16rpx 20rpx; margin-bottom: 24rpx; }
.status-text { font-size: 24rpx; color: #166534; }
.status-badge { background: #0F766E; color: #FFF; font-size: 20rpx; padding: 4rpx 16rpx; border-radius: 20rpx; }
.section { margin-bottom: 24rpx; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.section-title { font-size: 30rpx; font-weight: bold; color: #1E293B; }
.section-more { font-size: 24rpx; color: #0F766E; }
.cost-card { background: #FFF; border-radius: 16rpx; padding: 24rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.cost-bar-track { display: flex; height: 24rpx; border-radius: 12rpx; overflow: hidden; margin-bottom: 16rpx; }
.cost-bar-fill { height: 100%; }
.cost-legend { display: flex; flex-wrap: wrap; gap: 12rpx; }
.cost-legend-item { display: flex; align-items: center; }
.legend-dot { width: 16rpx; height: 16rpx; border-radius: 8rpx; margin-right: 6rpx; }
.legend-label { font-size: 22rpx; color: #64748B; }
.entry-grid { display: flex; flex-wrap: wrap; gap: 16rpx; }
.entry-card { width: 28%; flex: 1; min-width: 140rpx; background: #FFF; border-radius: 16rpx; padding: 24rpx 16rpx; text-align: center; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.entry-icon { font-size: 48rpx; display: block; margin-bottom: 8rpx; }
.entry-text { font-size: 26rpx; font-weight: 500; color: #1E293B; display: block; }
.entry-desc { font-size: 20rpx; color: #94A3B8; margin-top: 4rpx; display: block; }
.highlight-card { display: flex; background: linear-gradient(135deg, #FFF7ED, #FFFBEB); border-radius: 16rpx; padding: 30rpx; margin-top: 8rpx; border: 1rpx solid #FDE68A; }
.highlight-left { flex: 1; text-align: center; }
.highlight-num { font-size: 64rpx; font-weight: bold; color: #F97316; display: block; }
.highlight-unit { font-size: 24rpx; color: #D97706; display: block; }
.highlight-divider { width: 2rpx; background: #FDE68A; margin: 0 24rpx; }
.highlight-right { flex: 2; display: flex; flex-direction: column; justify-content: center; }
.highlight-meta { font-size: 22rpx; color: #92400E; line-height: 1.6; }
</style>
