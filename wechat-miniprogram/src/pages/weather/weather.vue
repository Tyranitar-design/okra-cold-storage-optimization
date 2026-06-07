<template>
  <view class="weather-container">
    <!-- 当前天气 -->
    <view class="current-weather">
      <text class="temp-text">{{ w.temp }}<text class="temp-unit">°C</text></text>
      <view class="weather-info">
        <text class="weather-desc">{{ w.desc }}</text>
        <text class="weather-meta">💧 {{ w.humidity }}% · 🌬️ {{ w.wind }}</text>
      </view>
      <view class="weather-location">📍 {{ w.location }} · {{ w.time }}</view>
      <view class="weather-source">{{ sourceMeta }}</view>
      <button class="weather-refresh" size="mini" @tap="loadWeather({ refresh: true })" :loading="loading">刷新天气</button>
    </view>

    <!-- 预警卡 -->
    <view class="alert-card" v-if="alert">
      <text class="alert-icon">{{ alert.icon }}</text>
      <view class="alert-body">
        <text class="alert-title">{{ alert.title }}</text>
        <text class="alert-desc">{{ alert.desc }}</text>
      </view>
    </view>

    <!-- 冷库运行建议 -->
    <view class="section">
      <view class="section-header">
        <text class="section-title">🧊 冷库运行建议</text>
        <text class="section-count">{{ advice.length }} 条</text>
      </view>
      <view class="advice-card" v-for="(a, i) in advice" :key="i"
        :class="{ warning: a.icon === '⚠️', info: a.icon === 'ℹ️' }">
        <text class="advice-icon">{{ a.icon }}</text>
        <view class="advice-content">
          <text class="advice-title">{{ a.title }}</text>
          <text class="advice-desc">{{ a.desc }}</text>
        </view>
      </view>
    </view>

    <!-- 4天预报 -->
    <view class="section">
      <text class="section-title">📅 4 天预报</text>
      <scroll-view class="forecast-scroll" scroll-x show-scrollbar="false">
        <view class="forecast-day" v-for="(d, i) in forecast" :key="i"
          :class="{ today: i === 0 }">
          <text class="forecast-date">{{ d.date }}</text>
          <text class="forecast-icon">{{ d.icon }}</text>
          <text class="forecast-temp">{{ d.temp }}°C</text>
          <text class="forecast-desc">{{ d.desc }}</text>
        </view>
      </scroll-view>
    </view>

    <!-- 秋葵特殊提醒 -->
    <view class="tip-card">
      <text class="tip-title">🌿 秋葵采后提醒</text>
      <text class="tip-text">当前天气适合采收。建议采收后 2h 内完成预冷入库（预冷库 0-5°C），冷藏环节温度维持在 2-8°C，可储藏 7-14 天。</text>
    </view>
  </view>
</template>

<script>
import api from '@/api/index.js'
import { mockData } from '@/utils/mockData'

export default {
  data() {
    return {
      w: { ...mockData.weather.current },
      forecast: [...mockData.weather.forecast],
      advice: [...mockData.weather.advice],
      alert: null,
      loading: false,
      sourceMeta: '本地兜底快照',
    }
  },
  onLoad() {
    this.loadWeather()
  },
  onPullDownRefresh() {
    this.loadWeather({ refresh: true, stopPull: true })
  },
  methods: {
    weatherIcon(desc = '') {
      if (desc.includes('雨')) return '🌧️'
      if (desc.includes('晴')) return '☀️'
      if (desc.includes('阴')) return '☁️'
      if (desc.includes('雪')) return '❄️'
      return '⛅'
    },
    roundText(value, fallback = '--') {
      const n = Number(value)
      if (!Number.isFinite(n)) return fallback
      return String(Math.round(n))
    },
    signalIcon(level) {
      if (level === 'warn') return '⚠️'
      if (level === 'ok') return '✅'
      return 'ℹ️'
    },
    normalizeWeatherPanel(panel) {
      const current = panel?.current || {}
      const location = panel?.location || {}
      const temp = this.roundText(current.temperature_c, this.w.temp)
      const humidity = this.roundText(current.humidity_pct, this.w.humidity)
      const wind = [current.wind_direction ? `${current.wind_direction}风` : '', current.wind_power ? `${current.wind_power}级` : '']
        .filter(Boolean)
        .join(' ')
      this.w = {
        temp,
        desc: current.weather || this.w.desc || '实时快照',
        humidity,
        wind: wind || this.w.wind || '实时风况',
        location: [location.province, location.city].filter(Boolean).join(' · ') || this.w.location,
        time: current.report_time || location.reporttime || panel?.fetched_at || this.w.time,
      }

      const forecast = Array.isArray(panel?.forecast) ? panel.forecast : []
      if (forecast.length) {
        this.forecast = forecast.map((d) => {
          const dayTemp = this.roundText(d.day_temp_c)
          const nightTemp = this.roundText(d.night_temp_c)
          return {
            date: d.date ? d.date.slice(5).replace('-', '/') : '未来',
            icon: this.weatherIcon(d.day_weather || d.night_weather || ''),
            temp: nightTemp === '--' ? dayTemp : `${dayTemp} / ${nightTemp}`,
            desc: d.day_weather || d.night_weather || '预报',
          }
        })
      }

      const signals = panel?.cold_chain_linkage?.signals || []
      if (signals.length) {
        this.advice = signals.map((s) => ({
          icon: this.signalIcon(s.level),
          title: s.label,
          desc: [s.value, s.detail].filter(Boolean).join(' · '),
        }))
      }

      const warn = signals.find((s) => s.level === 'warn')
      const currentTemp = Number(current.temperature_c)
      this.alert = warn
        ? { icon: '🔴', title: warn.label, desc: [warn.value, warn.detail].filter(Boolean).join(' · ') }
        : (Number.isFinite(currentTemp) && currentTemp >= 30
          ? { icon: '🔴', title: '高温预警', desc: '当前气温较高，建议提前采收并增加预冷产能储备' }
          : null)

      const refresh = panel?.refresh
      const cacheLabel = refresh ? (refresh.used_cache ? '缓存' : '已刷新') : '快照'
      this.sourceMeta = `${cacheLabel} · fetched_at ${panel?.fetched_at || '--'} · report_time ${current.report_time || '--'}`
    },
    async loadWeather(options = {}) {
      this.loading = true
      try {
        const panel = options.refresh
          ? await api.refreshWeather({ force: false, maxAgeSeconds: 300 })
          : await api.getWeatherPanel()
        if (panel?.available || panel?.current || panel?.forecast?.length) {
          this.normalizeWeatherPanel(panel)
        } else if (this.w.temp >= 30) {
          this.alert = { icon: '🔴', title: '高温预警', desc: '未来 24h 最高温 31°C，建议提前采收并增加预冷产能' }
        }
      } catch (e) {
        if (this.w.temp >= 30) {
          this.alert = { icon: '🔴', title: '高温预警', desc: '未来 24h 最高温 31°C，建议提前采收并增加预冷产能' }
        }
      } finally {
        this.loading = false
        if (options.stopPull) uni.stopPullDownRefresh()
      }
    },
  }
}
</script>

<style>
.weather-container { padding: 0 24rpx 40rpx; background: linear-gradient(180deg, #0EA5E9 0%, #F0F9FF 300rpx, #F8FAFC 100%); min-height: 100vh; }
.current-weather { text-align: center; padding: 50rpx 0 40rpx; color: #FFF; }
.temp-text { font-size: 100rpx; font-weight: 200; display: block; line-height: 1; }
.temp-unit { font-size: 48rpx; font-weight: 300; }
.weather-info { margin-top: 12rpx; }
.weather-desc { font-size: 36rpx; display: block; }
.weather-meta { font-size: 26rpx; opacity: 0.8; margin-top: 6rpx; display: block; }
.weather-location { font-size: 22rpx; opacity: 0.6; margin-top: 16rpx; display: block; }
.weather-source { font-size: 20rpx; opacity: 0.62; margin-top: 8rpx; display: block; word-break: break-all; padding: 0 24rpx; }
.weather-refresh { margin-top: 18rpx; color: #0369A1; background: rgba(255,255,255,0.92); border-radius: 12rpx; font-size: 22rpx; }
.alert-card { display: flex; background: #FEF2F2; border-radius: 16rpx; padding: 24rpx; margin-bottom: 24rpx; border: 1rpx solid #FECACA; }
.alert-icon { font-size: 40rpx; margin-right: 16rpx; }
.alert-body { flex: 1; }
.alert-title { font-size: 28rpx; font-weight: bold; color: #991B1B; display: block; }
.alert-desc { font-size: 24rpx; color: #B91C1C; margin-top: 4rpx; display: block; }
.section { margin-bottom: 28rpx; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14rpx; }
.section-title { font-size: 30rpx; font-weight: bold; color: #1E293B; }
.section-count { font-size: 22rpx; color: #64748B; background: #F1F5F9; padding: 4rpx 16rpx; border-radius: 20rpx; }
.advice-card { display: flex; background: #FFF; border-radius: 16rpx; padding: 24rpx; margin-bottom: 12rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.advice-card.warning { border-left: 6rpx solid #F59E0B; }
.advice-card.info { border-left: 6rpx solid #3B82F6; }
.advice-icon { font-size: 36rpx; margin-right: 16rpx; }
.advice-content { flex: 1; }
.advice-title { font-size: 26rpx; font-weight: 500; color: #1E293B; display: block; }
.advice-desc { font-size: 24rpx; color: #64748B; margin-top: 4rpx; display: block; line-height: 1.5; }
.forecast-scroll { white-space: nowrap; padding-bottom: 8rpx; }
.forecast-day { display: inline-flex; flex-direction: column; align-items: center; background: rgba(255,255,255,0.95); border-radius: 16rpx; padding: 24rpx 36rpx; margin-right: 16rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.04); }
.forecast-day.today { background: #FFF; border: 2rpx solid #0EA5E9; }
.forecast-date { font-size: 24rpx; color: #64748B; }
.forecast-icon { font-size: 48rpx; margin: 12rpx 0; }
.forecast-temp { font-size: 32rpx; font-weight: 600; color: #1E293B; }
.forecast-desc { font-size: 22rpx; color: #94A3B8; margin-top: 4rpx; }
.tip-card { background: linear-gradient(135deg, #F0FDF4, #ECFDF5); border-radius: 16rpx; padding: 24rpx; border: 1rpx solid #BBF7D0; }
.tip-title { font-size: 26rpx; font-weight: bold; color: #166534; display: block; margin-bottom: 8rpx; }
.tip-text { font-size: 24rpx; color: #15803D; line-height: 1.6; display: block; }
</style>
