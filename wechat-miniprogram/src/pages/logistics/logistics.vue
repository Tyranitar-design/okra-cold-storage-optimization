<template>
  <view class="logistics-container">
    <view class="hero">
      <text class="hero-title">🚛 物流路线</text>
      <text class="hero-subtitle">产区 → 冷库 · 实时配送追踪</text>
    </view>

    <!-- 路线地图 -->
    <map class="route-map" :latitude="center.lat" :longitude="center.lng"
      :markers="routeMarkers" :polyline="routePolylines" scale="12">
    </map>

    <!-- #ifdef APP-PLUS -->
    <view class="app-route-map">
      <view class="app-route-header">
        <text class="app-route-title">路线清单</text>
        <text class="app-route-subtitle">安卓端保留原生路线地图，也可从路线卡片打开系统地图</text>
      </view>
      <view class="app-route-line">
        <view class="app-route-node" v-for="(r, i) in routes" :key="i">
          <text class="node-index">{{ i + 1 }}</text>
          <text class="node-name">{{ r.from }}</text>
          <text class="node-status" :class="statusClass(r.status)">{{ r.status }}</text>
        </view>
      </view>
    </view>
    <!-- #endif -->

    <!-- 路线列表 -->
    <view class="route-list">
      <view class="route-card" v-for="(r, i) in routes" :key="i"
        :class="{ delivered: r.status === '已送达', in_transit: r.status === '运输中', pending: r.status === '待发车' }">
        <view class="route-dot">
          <text class="dot-icon">{{ r.status === '已送达' ? '✅' : r.status === '运输中' ? '🚚' : '📦' }}</text>
        </view>
        <view class="route-body">
          <view class="route-stops">
            <text class="stop-from">{{ r.from }}</text>
            <text class="stop-arrow"> → </text>
            <text class="stop-to">{{ r.to }}</text>
          </view>
          <view class="route-meta">
            <text>📏 {{ r.dist }} km</text>
            <text class="meta-divider">|</text>
            <text>⏱️ {{ r.eta }} min</text>
            <text class="meta-divider">|</text>
            <text :class="statusClass(r.status)">{{ r.status }}</text>
          </view>
          <text class="route-time">🕐 {{ r.time }}</text>
          <!-- #ifdef APP-PLUS -->
          <button class="route-map-btn" @tap="openRouteMap(r, i)">打开系统地图</button>
          <!-- #endif -->
        </view>
      </view>
    </view>

    <view class="stats-row">
      <view class="stats-item"><text class="stats-num">{{ routes.length }}</text><text class="stats-label">今日运单</text></view>
      <view class="stats-item"><text class="stats-num">{{ routes.filter(r => r.status === '运输中').length }}</text><text class="stats-label">运输中</text></view>
      <view class="stats-item"><text class="stats-num">{{ routes.reduce((s, r) => s + r.dist, 0).toFixed(0) }}</text><text class="stats-label">总里程 km</text></view>
    </view>
  </view>
</template>

<script>
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      center: { lat: 29.280, lng: 111.690 },
      routes: mockData.logistics.routes,
    }
  },
  computed: {
    routeMarkers() {
      const points = []
      this.routes.forEach((r, i) => {
        // approximate lat/lng for demo
        const offset = (i + 1) * 0.03
        points.push({ id: `f${i}`, latitude: 29.30 + offset, longitude: 111.68 + offset * 0.5, title: r.from, iconPath: '/static/marker.png', width: 24, height: 32 })
        points.push({ id: `t${i}`, latitude: 29.25 + offset, longitude: 111.70 - offset * 0.3, title: r.to, iconPath: '/static/marker-key.png', width: 24, height: 32 })
      })
      return points
    },
    routePolylines() {
      return this.routes.map((r, i) => {
        const offset = (i + 1) * 0.03
        return {
          points: [
            { latitude: 29.30 + offset, longitude: 111.68 + offset * 0.5 },
            { latitude: 29.25 + offset, longitude: 111.70 - offset * 0.3 },
          ],
          color: r.status === '已送达' ? '#0F766E' : r.status === '运输中' ? '#F59E0B' : '#94A3B8',
          width: 4,
          dottedLine: r.status === '待发车',
          arrowLine: true,
        }
      })
    }
  },
  methods: {
    statusClass(s) {
      return { '已送达': 'color-green', '运输中': 'color-yellow', '待发车': 'color-gray' }[s] || ''
    },
    routePoint(index, type) {
      const offset = (index + 1) * 0.03
      if (type === 'from') {
        return { latitude: 29.30 + offset, longitude: 111.68 + offset * 0.5 }
      }
      return { latitude: 29.25 + offset, longitude: 111.70 - offset * 0.3 }
    },
    async openRouteMap(route, index) {
      await this.requestLocationPermission()
      const point = this.routePoint(index, 'to')
      uni.openLocation({
        latitude: point.latitude,
        longitude: point.longitude,
        name: route.to,
        address: `${route.from} -> ${route.to}`,
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
    }
  }
}
</script>

<style>
.logistics-container { padding: 0 0 40rpx; background: #F8FAFC; min-height: 100vh; }
.hero { background: linear-gradient(135deg, #0F766E, #14B8A6); padding: 40rpx 30rpx; }
.hero-title { font-size: 38rpx; font-weight: bold; color: #FFF; display: block; }
.hero-subtitle { font-size: 22rpx; color: rgba(255,255,255,0.8); margin-top: 6rpx; display: block; }
.route-map { width: 100%; height: 400rpx; }
.app-route-map { padding: 24rpx; background: linear-gradient(180deg, #ECFDF5 0%, #F8FAFC 100%); }
.app-route-header { margin-bottom: 18rpx; }
.app-route-title { display: block; font-size: 32rpx; font-weight: bold; color: #0F172A; }
.app-route-subtitle { display: block; margin-top: 6rpx; font-size: 22rpx; color: #64748B; }
.app-route-line { display: flex; gap: 14rpx; overflow-x: auto; padding-bottom: 6rpx; }
.app-route-node { min-width: 220rpx; background: #FFF; border-radius: 14rpx; padding: 18rpx; border: 1rpx solid #E2E8F0; box-shadow: 0 2rpx 8rpx rgba(15, 23, 42, 0.06); }
.node-index { display: inline-flex; align-items: center; justify-content: center; width: 36rpx; height: 36rpx; border-radius: 18rpx; background: #0F766E; color: #FFF; font-size: 20rpx; }
.node-name { display: block; margin-top: 12rpx; font-size: 24rpx; font-weight: 600; color: #1E293B; }
.node-status { display: block; margin-top: 8rpx; font-size: 21rpx; }
.route-list { padding: 20rpx 24rpx; }
.route-card { display: flex; background: #FFF; border-radius: 14rpx; padding: 20rpx; margin-bottom: 14rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); border-left: 6rpx solid #E2E8F0; }
.route-card.delivered { border-left-color: #0F766E; }
.route-card.in_transit { border-left-color: #F59E0B; }
.route-card.pending { border-left-color: #94A3B8; }
.route-dot { width: 50rpx; display: flex; align-items: center; }
.dot-icon { font-size: 32rpx; }
.route-body { flex: 1; }
.route-stops { margin-bottom: 8rpx; }
.stop-from { font-size: 26rpx; font-weight: 500; color: #1E293B; }
.stop-arrow { font-size: 24rpx; color: #94A3B8; }
.stop-to { font-size: 26rpx; font-weight: 500; color: #0F766E; }
.route-meta { font-size: 22rpx; color: #64748B; margin-bottom: 4rpx; }
.meta-divider { margin: 0 8rpx; color: #CBD5E1; }
.route-time { font-size: 22rpx; color: #94A3B8; }
.route-map-btn { margin: 14rpx 0 0; padding: 0 18rpx; height: 58rpx; line-height: 58rpx; background: #0F766E; color: #FFF; border-radius: 10rpx; font-size: 24rpx; }
.color-green { color: #166534; } .color-yellow { color: #B45309; } .color-gray { color: #6B7280; }
.stats-row { display: flex; margin: 0 24rpx; background: #FFF; border-radius: 14rpx; padding: 20rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.stats-item { flex: 1; text-align: center; }
.stats-num { font-size: 36rpx; font-weight: bold; color: #0F766E; display: block; }
.stats-label { font-size: 22rpx; color: #64748B; margin-top: 4rpx; display: block; }
</style>
