<template>
  <view class="layout-container">
    <!-- 地图区域 -->
    <map class="map" :latitude="center.lat" :longitude="center.lng"
      :markers="allMarkers" scale="11" @markertap="onMarkerTap"
      :style="{ height: mapHeight }">
    </map>

    <!-- #ifdef APP-PLUS -->
    <view class="app-map-summary" :style="{ minHeight: mapHeight }">
      <view class="app-map-header">
        <text class="app-map-title">冷库设施清单</text>
        <text class="app-map-subtitle">安卓端保留原生地图展示，也可打开系统地图查看坐标</text>
      </view>
      <view class="app-map-grid">
        <view
          class="app-map-point"
          v-for="f in facilities"
          :key="f.id"
          :class="{ active: selected && selected.id === f.id, ai: aiLabels[f.id] }"
          @tap="selectFacility(f)"
        >
          <text class="point-name">{{ f.name }}</text>
          <text class="point-meta">{{ f.type }} · {{ f.status }}</text>
          <text class="point-coord">{{ f.lat.toFixed(3) }}, {{ f.lng.toFixed(3) }}</text>
        </view>
      </view>
    </view>
    <!-- #endif -->

    <!-- 筛选栏 -->
    <scroll-view class="filter-bar" scroll-x show-scrollbar="false">
      <view class="filter-chip" :class="{ active: filter === 'all' }" @tap="filter = 'all'">全部</view>
      <view class="filter-chip" :class="{ active: filter === 'precool' }" @tap="filter = 'precool'">预冷库</view>
      <view class="filter-chip" :class="{ active: filter === 'cold' }" @tap="filter = 'cold'">冷藏库</view>
      <view class="filter-chip" :class="{ active: filter === 'ca' }" @tap="filter = 'ca'">气调库</view>
      <view class="filter-chip" :class="{ active: filter === 'frozen' }" @tap="filter = 'frozen'">冷冻库</view>
      <view class="filter-chip ai-chip" :class="{ active: filter === 'ai' }" @tap="filter = 'ai'">⭐ AI推荐</view>
    </scroll-view>

    <!-- 设施详情面板 -->
    <view class="detail-panel" v-if="selected" :class="{ collapsed: panelCollapsed }">
      <view class="panel-handle" @tap="panelCollapsed = !panelCollapsed">
        <text class="panel-handle-bar"></text>
      </view>

      <view class="panel-header">
        <view class="panel-title-row">
          <text class="panel-title">{{ selected.name }}</text>
          <text class="panel-badge" :style="{ background: typeColor(selected.type) }">{{ selected.type }}</text>
        </view>
        <text class="panel-status" v-if="aiLabels[selected.id]">⭐ AI 推荐 · 置信度 {{ aiLabels[selected.id] }}%</text>
      </view>

      <view class="panel-metrics">
        <view class="metric-box">
          <text class="metric-value">{{ selected.capacity }}<text class="metric-unit">吨</text></text>
          <text class="metric-label">装机容量</text>
        </view>
        <view class="metric-box">
          <text class="metric-value">{{ selected.loadPct }}<text class="metric-unit">%</text></text>
          <text class="metric-label">容量利用率</text>
        </view>
        <view class="metric-box">
          <text class="metric-value">{{ selected.cost }}<text class="metric-unit">万/年</text></text>
          <text class="metric-label">运营成本</text>
        </view>
      </view>

      <view class="panel-detail">
        <view class="detail-row"><text class="dl">状态</text><text class="dd" :class="{ green: selected.status === '运营中', yellow: selected.status === '建设中', gray: selected.status === '规划中' }">{{ selected.status }}</text></view>
        <view class="detail-row"><text class="dl">坐标</text><text class="dd">{{ selected.lat.toFixed(3) }}, {{ selected.lng.toFixed(3) }}</text></view>
        <view class="detail-row"><text class="dl">温度范围</text><text class="dd">{{ tempRange(selected.type) }}</text></view>
      </view>

      <!-- 容量条 -->
      <view class="capacity-track">
        <view class="capacity-fill" :style="{ width: selected.loadPct + '%' }"></view>
      </view>

      <!-- #ifdef APP-PLUS -->
      <button class="open-map-btn" @tap="openFacilityMap(selected)">打开系统地图</button>
      <!-- #endif -->
    </view>
  </view>
</template>

<script>
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      center: { lat: 29.280, lng: 111.690 },
      selected: null,
      panelCollapsed: false,
      filter: 'all',
      mapHeight: '75vh',
      aiLabels: { f5: 92, f6: 87, f1: 78, f3: 71 },
    }
  },
  computed: {
    facilities() {
      let list = [...mockData.facilities]
      if (this.filter === 'all') return list
      if (this.filter === 'ai') return list.filter(f => this.aiLabels[f.id])
      const typeMap = { precool: '预冷库', cold: '冷藏库', ca: '气调库', frozen: '冷冻库' }
      return list.filter(f => f.type === typeMap[this.filter])
    },
    allMarkers() {
      const markers = this.facilities.map(f => ({
        id: f.id, latitude: f.lat, longitude: f.lng,
        title: f.name,
        iconPath: this.aiLabels[f.id] ? '/static/marker-ai.png' : '/static/marker.png',
        width: 28, height: 36,
        callout: {
          content: `${f.name}·${f.type}`,
          fontSize: 11, borderRadius: 6,
          bgColor: this.aiLabels[f.id] ? '#FEF3C7' : '#FFFFFF',
          padding: 6, display: 'ALWAYS',
        }
      }))
      // 候选点灰色标记
      const ghostMarkers = [
        { id: 'g1', latitude: 29.350, longitude: 111.740, iconPath: '/static/marker-ghost.png', width: 20, height: 26 },
        { id: 'g2', latitude: 29.240, longitude: 111.780, iconPath: '/static/marker-ghost.png', width: 20, height: 26 },
        { id: 'g3', latitude: 29.300, longitude: 111.600, iconPath: '/static/marker-ghost.png', width: 20, height: 26 },
        { id: 'g4', latitude: 29.200, longitude: 111.640, iconPath: '/static/marker-ghost.png', width: 20, height: 26 },
      ]
      return this.filter === 'ai' ? markers : [...markers, ...ghostMarkers]
    }
  },
  methods: {
    onMarkerTap(e) {
      const id = typeof e.detail?.markerId === 'string' ? e.detail.markerId : e.target?.id
      if (!id || id.startsWith('g')) return
      this.selectFacility(this.facilities.find(f => f.id === id))
    },
    selectFacility(facility) {
      if (!facility) return
      this.selected = facility
      this.panelCollapsed = false
      this.mapHeight = '55vh'
    },
    async openFacilityMap(facility) {
      if (!facility) return
      await this.requestLocationPermission()
      uni.openLocation({
        latitude: facility.lat,
        longitude: facility.lng,
        name: facility.name,
        address: `${facility.type} · ${facility.status}`,
        scale: 14,
        fail: () => {
          uni.showToast({ title: '系统地图不可用，请检查地图权限', icon: 'none' })
        },
      })
    },
    requestLocationPermission() {
      return new Promise((resolve) => {
        try {
          if (typeof plus === 'undefined' || !plus.android?.requestPermissions) {
            resolve()
            return
          }
          plus.android.requestPermissions(
            [
              'android.permission.ACCESS_FINE_LOCATION',
              'android.permission.ACCESS_COARSE_LOCATION',
            ],
            () => resolve(),
            () => resolve()
          )
        } catch (e) {
          resolve()
        }
      })
    },
    typeColor(type) {
      return { '预冷库': '#0EA5E9', '冷藏库': '#0F766E', '气调库': '#8B5CF6', '冷冻库': '#6366F1' }[type] || '#64748B'
    },
    tempRange(type) {
      return { '预冷库': '0-5°C', '冷藏库': '2-8°C', '气调库': '2-5°C+MAP', '冷冻库': '-25~-18°C' }[type] || '—'
    }
  }
}
</script>

<style>
.layout-container { position: relative; background: #F8FAFC; }
.map { width: 100%; height: 75vh; transition: height 0.3s; }
.app-map-summary { padding: 28rpx 24rpx; background: linear-gradient(180deg, #E0F2FE 0%, #F8FAFC 100%); box-sizing: border-box; }
.app-map-header { margin-bottom: 22rpx; }
.app-map-title { display: block; font-size: 34rpx; font-weight: bold; color: #0F172A; }
.app-map-subtitle { display: block; margin-top: 6rpx; font-size: 23rpx; color: #64748B; }
.app-map-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14rpx; }
.app-map-point { background: #FFF; border: 2rpx solid #E2E8F0; border-radius: 14rpx; padding: 18rpx; box-shadow: 0 2rpx 8rpx rgba(15, 23, 42, 0.06); }
.app-map-point.active { border-color: #0F766E; box-shadow: 0 4rpx 14rpx rgba(15, 118, 110, 0.16); }
.app-map-point.ai { border-color: #FBBF24; }
.point-name { display: block; font-size: 25rpx; font-weight: 600; color: #1E293B; }
.point-meta { display: block; margin-top: 8rpx; font-size: 21rpx; color: #0F766E; }
.point-coord { display: block; margin-top: 6rpx; font-size: 20rpx; color: #94A3B8; }
.filter-bar { display: flex; padding: 16rpx 24rpx; background: #FFF; white-space: nowrap; border-bottom: 1rpx solid #F1F5F9; }
.filter-chip { display: inline-block; padding: 8rpx 24rpx; margin-right: 12rpx; border-radius: 20rpx; font-size: 24rpx; color: #64748B; background: #F1F5F9; }
.filter-chip.active { background: #0F766E; color: #FFF; }
.ai-chip.active { background: #F59E0B; color: #FFF; }
.detail-panel { position: fixed; bottom: 0; left: 0; right: 0; background: #FFF; border-radius: 32rpx 32rpx 0 0; padding: 0 30rpx 40rpx; box-shadow: 0 -4rpx 20rpx rgba(0,0,0,0.1); max-height: 60vh; overflow-y: auto; transition: transform 0.3s; }
.detail-panel.collapsed .panel-metrics,
.detail-panel.collapsed .panel-detail,
.detail-panel.collapsed .capacity-track { display: none; }
.panel-handle { text-align: center; padding: 16rpx 0; }
.panel-handle-bar { display: inline-block; width: 60rpx; height: 6rpx; background: #CBD5E1; border-radius: 3rpx; }
.panel-header { margin-bottom: 20rpx; }
.panel-title-row { display: flex; align-items: center; gap: 12rpx; }
.panel-title { font-size: 34rpx; font-weight: bold; color: #1E293B; }
.panel-badge { font-size: 20rpx; color: #FFF; padding: 4rpx 16rpx; border-radius: 12rpx; }
.panel-status { font-size: 22rpx; color: #D97706; margin-top: 6rpx; display: block; }
.panel-metrics { display: flex; gap: 16rpx; margin-bottom: 20rpx; }
.metric-box { flex: 1; background: #F8FAFC; border-radius: 12rpx; padding: 16rpx; text-align: center; }
.metric-value { font-size: 36rpx; font-weight: bold; color: #0F766E; display: block; }
.metric-unit { font-size: 22rpx; color: #94A3B8; }
.metric-label { font-size: 22rpx; color: #64748B; margin-top: 4rpx; display: block; }
.panel-detail { margin-bottom: 20rpx; }
.detail-row { display: flex; justify-content: space-between; padding: 12rpx 0; border-bottom: 1rpx solid #F1F5F9; }
.dl { font-size: 26rpx; color: #64748B; }
.dd { font-size: 26rpx; color: #1E293B; font-weight: 500; }
.green { color: #166534; } .yellow { color: #B45309; } .gray { color: #6B7280; }
.capacity-track { height: 16rpx; background: #F1F5F9; border-radius: 8rpx; overflow: hidden; }
.capacity-fill { height: 100%; background: linear-gradient(90deg, #0F766E, #14B8A6); border-radius: 8rpx; transition: width 0.5s; }
.open-map-btn { margin-top: 22rpx; background: #0F766E; color: #FFF; border-radius: 12rpx; font-size: 27rpx; }
</style>
