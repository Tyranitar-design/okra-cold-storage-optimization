<template>
  <view class="storage-container">
    <!-- 冷库概览 -->
    <view class="hero" :style="{ background: heroGradient }">
      <view class="hero-top">
        <text class="hero-title">{{ storage.name }}</text>
        <text class="hero-badge">{{ storage.type }}</text>
      </view>
      <view class="hero-metrics">
        <view class="hm-item">
          <text class="hm-value">{{ storage.capacity.used }}<text class="hm-unit">/{{ storage.capacity.total }}{{ storage.capacity.unit }}</text></text>
          <text class="hm-label">库存容量</text>
        </view>
        <view class="hm-divider"></view>
        <view class="hm-item">
          <text class="hm-value">{{ storage.temp.current }}<text class="hm-unit">°C</text></text>
          <text class="hm-label">当前温度</text>
        </view>
        <view class="hm-divider"></view>
        <view class="hm-item">
          <text class="hm-value">{{ energyCost }}<text class="hm-unit">元/月</text></text>
          <text class="hm-label">能耗成本</text>
        </view>
      </view>
      <!-- 容量条 -->
      <view class="capacity-track">
        <view class="capacity-fill" :style="{ width: fillPct + '%' }"></view>
      </view>
      <text class="capacity-label">容量利用率 {{ fillPct }}%（目标 &lt; 85%）</text>
    </view>

    <!-- 温度曲线 (替代chart) -->
    <view class="section">
      <view class="section-header">
        <text class="section-title">🌡️ 温度趋势</text>
        <text class="section-more" @tap="showAllTemp = !showAllTemp">{{ showAllTemp ? '收起' : '查看全部' }}</text>
      </view>
      <view class="temp-chart">
        <view class="temp-bar" v-for="(h, i) in tempHistory" :key="i">
          <view class="temp-bar-fill" :style="{ height: ((h.temp - 6) / 6 * 100) + '%', background: tempColor(h.temp) }"></view>
          <text class="temp-bar-label">{{ h.date }}</text>
        </view>
        <view class="temp-target-line" :style="{ bottom: '40%' }"></view>
      </view>
      <view class="temp-legend">
        <view class="tl-item"><view class="tl-dot" style="background:#0F766E"></view>目标 7-10°C</view>
      </view>
    </view>

    <!-- 库存列表 -->
    <view class="section">
      <view class="section-header">
        <text class="section-title">📦 库存批次</text>
        <text class="section-more">共 {{ storage.inventory.length }} 批</text>
      </view>
      <view class="inv-card" v-for="(item, i) in storage.inventory" :key="i">
        <view class="inv-header">
          <text class="inv-batch">{{ item.batch }}</text>
          <text class="inv-status" :class="{ warn: item.loss > 1 }">{{ item.loss }}% 损耗</text>
        </view>
        <view class="inv-meta">
          <text>🌾 {{ item.product }} · {{ item.qty }}吨</text>
          <text>入库 {{ item.date }}</text>
        </view>
        <view class="inv-footer">
          <text>预计出库 {{ item.eta }}</text>
          <view class="inv-progress">
            <view class="inv-progress-fill" :style="{ width: lossBarWidth(item) + '%' }"></view>
          </view>
        </view>
      </view>
    </view>

    <!-- 能耗统计 -->
    <view class="section">
      <text class="section-title">⚡ 能耗</text>
      <view class="energy-card">
        <view class="energy-row">
          <text class="energy-label">月用电量</text>
          <text class="energy-value">{{ storage.energy.monthly }} kWh</text>
        </view>
        <view class="energy-row">
          <text class="energy-label">月电费</text>
          <text class="energy-value">{{ storage.energy.cost }} 元</text>
        </view>
        <view class="energy-row">
          <text class="energy-label">碳排因子</text>
          <text class="energy-value">0.6 kgCO₂/kWh</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      storage: mockData.storage,
      showAllTemp: false,
    }
  },
  computed: {
    fillPct() {
      return Math.round(this.storage.capacity.used / this.storage.capacity.total * 100)
    },
    energyCost() {
      return this.storage.energy.cost.toLocaleString()
    },
    heroGradient() {
      const pct = this.fillPct
      if (pct > 85) return 'linear-gradient(135deg, #DC2626, #F97316)'
      if (pct > 70) return 'linear-gradient(135deg, #0F766E, #14B8A6)'
      return 'linear-gradient(135deg, #0F766E, #14B8A6)'
    },
    tempHistory() {
      return this.showAllTemp ? this.storage.history : this.storage.history.slice(-3)
    }
  },
  methods: {
    tempColor(t) {
      if (t > 10) return '#EF4444'
      if (t < 7) return '#3B82F6'
      return '#0F766E'
    },
    lossBarWidth(item) {
      return Math.min(item.loss * 20, 100)
    }
  }
}
</script>

<style>
.storage-container { padding: 0 0 40rpx; background: #F8FAFC; min-height: 100vh; }
.hero { padding: 40rpx 30rpx 30rpx; color: #FFF; }
.hero-top { display: flex; align-items: center; gap: 12rpx; margin-bottom: 24rpx; }
.hero-title { font-size: 36rpx; font-weight: bold; }
.hero-badge { font-size: 20rpx; background: rgba(255,255,255,0.2); padding: 4rpx 16rpx; border-radius: 12rpx; }
.hero-metrics { display: flex; align-items: center; margin-bottom: 20rpx; }
.hm-item { flex: 1; text-align: center; }
.hm-value { font-size: 40rpx; font-weight: bold; display: block; }
.hm-unit { font-size: 22rpx; font-weight: 400; opacity: 0.8; }
.hm-label { font-size: 22rpx; opacity: 0.8; margin-top: 4rpx; display: block; }
.hm-divider { width: 2rpx; height: 40rpx; background: rgba(255,255,255,0.3); }
.capacity-track { height: 12rpx; background: rgba(255,255,255,0.25); border-radius: 6rpx; overflow: hidden; margin-bottom: 6rpx; }
.capacity-fill { height: 100%; background: #FFF; border-radius: 6rpx; transition: width 0.5s; }
.capacity-label { font-size: 20rpx; opacity: 0.7; }
.section { padding: 0 24rpx; margin-bottom: 28rpx; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14rpx; }
.section-title { font-size: 30rpx; font-weight: bold; color: #1E293B; }
.section-more { font-size: 24rpx; color: #0F766E; }
.temp-chart { display: flex; align-items: flex-end; gap: 12rpx; height: 200rpx; background: #FFF; border-radius: 16rpx; padding: 24rpx 20rpx 40rpx; position: relative; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.temp-bar { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
.temp-bar-fill { width: 40rpx; border-radius: 6rpx 6rpx 0 0; min-height: 10rpx; transition: height 0.5s; }
.temp-bar-label { font-size: 20rpx; color: #94A3B8; margin-top: 8rpx; }
.temp-target-line { position: absolute; left: 20rpx; right: 20rpx; border-top: 2rpx dashed #0F766E; opacity: 0.5; }
.temp-legend { margin-top: 8rpx; }
.tl-item { display: flex; align-items: center; gap: 6rpx; font-size: 22rpx; color: #64748B; }
.tl-dot { width: 12rpx; height: 12rpx; border-radius: 6rpx; }
.inv-card { background: #FFF; border-radius: 14rpx; padding: 20rpx; margin-bottom: 12rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.inv-header { display: flex; justify-content: space-between; margin-bottom: 8rpx; }
.inv-batch { font-size: 26rpx; font-weight: 600; color: #1E293B; }
.inv-status { font-size: 22rpx; color: #166534; background: #F0FDF4; padding: 2rpx 12rpx; border-radius: 10rpx; }
.inv-status.warn { color: #B45309; background: #FFFBEB; }
.inv-meta { font-size: 22rpx; color: #64748B; display: flex; justify-content: space-between; margin-bottom: 8rpx; }
.inv-footer { display: flex; justify-content: space-between; align-items: center; }
.inv-progress { width: 80rpx; height: 8rpx; background: #F1F5F9; border-radius: 4rpx; overflow: hidden; }
.inv-progress-fill { height: 100%; background: #EF4444; border-radius: 4rpx; }
.energy-card { background: #FFF; border-radius: 14rpx; padding: 20rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.energy-row { display: flex; justify-content: space-between; padding: 14rpx 0; border-bottom: 1rpx solid #F1F5F9; }
.energy-row:last-child { border-bottom: none; }
.energy-label { font-size: 26rpx; color: #64748B; }
.energy-value { font-size: 26rpx; font-weight: 500; color: #1E293B; }
</style>
