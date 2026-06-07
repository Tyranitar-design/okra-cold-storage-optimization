<template>
  <div>
    <!-- KPI 横幅 -->
    <section class="kpi-grid">
      <KpiAnimated label="当前实时温度" :value="currentTemp" suffix="°C" :decimals="0"
                   :delta="currentWeather" :delta-class="currentTemp > 7 ? 'warn' : 'positive'" />
      <KpiAnimated label="当前相对湿度" :value="currentHumidity" suffix="%" :decimals="0"
                   :delta="humidityNote" :delta-class="humidityClass" />
      <KpiAnimated label="未来日间最高温" :value="maxDayTemp" suffix="°C" :decimals="0"
                   :delta="`预冷目标 ≤7°C`" :delta-class="maxDayTemp > 7 ? 'warn' : 'positive'" />
      <KpiAnimated label="覆盖节点" :value="nodeCount" suffix="节点" :decimals="0"
                   delta="县域 adcode 431226" delta-class="neutral" />
    </section>

    <section class="weather-toolbar">
      <div>
        <strong>高德实时气象快照</strong>
        <span>{{ refreshInfo }}</span>
      </div>
      <button type="button" class="refresh-btn" :disabled="refreshing" @click="refreshWeather">
        {{ refreshing ? '刷新中...' : '刷新天气' }}
      </button>
    </section>

    <!-- 4 天预报 -->
    <section class="content-grid single">
      <PanelCard title="县域 4 天天气预报" :subtitle="locationLabel" badge="高德 API" badge-class="ok">
        <div v-if="forecast.length" class="forecast-strip">
          <div v-for="(day, i) in forecast" :key="day.date" class="forecast-card" :class="{ today: i === 0 }">
            <div class="fc-date">{{ day.date }} · {{ weekLabel(day.week) }}</div>
            <div class="fc-weather">{{ day.day_weather }}<span v-if="day.night_weather && day.night_weather !== day.day_weather"> / {{ day.night_weather }}</span></div>
            <div class="fc-temp"><span class="fc-day">{{ day.day_temp_c }}°</span> / <span class="fc-night">{{ day.night_temp_c }}°</span></div>
            <div class="fc-wind">{{ day.day_wind }}风 {{ day.wind_power }}级</div>
          </div>
        </div>
        <p v-else class="boundary-note">暂无气象预报数据。</p>
        <EChart v-if="forecast.length" :option="tempChart" height="260px" />
        <p class="boundary-note">{{ claimBoundary }}</p>
      </PanelCard>
    </section>

    <!-- 冷链温度链联动 -->
    <section class="content-grid stagger">
      <PanelCard title="冷链温度链联动信号" subtitle="气温如何影响冷库选址与损耗" badge="联动" badge-class="ok">
        <StatusList :items="linkageItems" />
      </PanelCard>
      <PanelCard title="冷链温区目标" subtitle="各通道目标温区（项目参数）" badge="温区" badge-class="neutral">
        <SectionTable :headers="['通道', '目标温区(°C)', '说明']" :rows="targetRows" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import SectionTable from '../components/SectionTable.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import EChart from '../components/EChart.vue'
import { apiFetch, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const panelOverride = ref(null)
const refreshing = ref(false)
const refreshError = ref('')
const w = computed(() => panelOverride.value || (b.value || {}).weather_panel || {})

const forecast = computed(() => safeArray(w.value?.forecast))
const forecastDays = computed(() => forecast.value.length)
const nodeCount = computed(() => Number(w.value?.node_count || 0))
const maxDayTemp = computed(() => Number(w.value?.cold_chain_linkage?.max_day_temp_c || 0))
const claimBoundary = computed(() => w.value?.claim_boundary || '高德实时气象快照，仅用于 MIS 展示与冷链温区联动。')

const current = computed(() => w.value?.current || null)
const currentTemp = computed(() => Number(current.value?.temperature_c ?? 0))
const currentHumidity = computed(() => Number(current.value?.humidity_pct ?? 0))
const currentWeather = computed(() => {
  const c = current.value
  if (!c) return '实时数据'
  const wd = c.wind_direction ? `${c.wind_direction}风` : ''
  return [c.weather, wd].filter(Boolean).join(' · ') || '实时数据'
})
const humidityNote = computed(() => {
  const h = currentHumidity.value
  if (!current.value) return ''
  if (h < 60) return '偏干 · 注意失水'
  if (h >= 85) return '高湿 · 防结露'
  return '湿度适中'
})
const humidityClass = computed(() => {
  const h = currentHumidity.value
  if (!current.value) return 'neutral'
  if (h < 60) return 'warn'
  return 'positive'
})

const locationLabel = computed(() => {
  const loc = w.value?.location || {}
  const parts = [loc.province, loc.city].filter(Boolean).join(' · ')
  const rt = current.value?.report_time
  const live = current.value ? (rt ? `实时更新 ${rt}` : '含实时温湿度') : '仅预报'
  return parts ? `${parts} · ${live}` : live
})

const refreshInfo = computed(() => {
  if (refreshError.value) return refreshError.value
  const refresh = w.value?.refresh
  const fetched = w.value?.fetched_at || '未生成'
  const report = current.value?.report_time || '无实时上报时间'
  if (!refresh) return `fetched_at ${fetched} · report_time ${report}`
  return `${refresh.used_cache ? '使用 5 分钟缓存' : '已请求高德刷新'} · fetched_at ${fetched} · report_time ${report}`
})

async function refreshWeather() {
  refreshing.value = true
  refreshError.value = ''
  try {
    panelOverride.value = await apiFetch('/api/v1/weather/refresh')
  } catch (error) {
    refreshError.value = error.message || '天气刷新失败'
  } finally {
    refreshing.value = false
  }
}

const WEEK_LABEL = { '1': '周一', '2': '周二', '3': '周三', '4': '周四', '5': '周五', '6': '周六', '7': '周日' }
function weekLabel(week) { return WEEK_LABEL[String(week)] || `周${week}` }

const tempChart = computed(() => {
  const days = forecast.value
  const dates = days.map((d) => d.date?.slice(5) || d.date)
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(0)}°C` },
    legend: { data: ['日间', '夜间'], top: 0 },
    grid: { left: 45, right: 25, top: 32, bottom: 36 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: '°C' },
    series: [
      {
        name: '日间', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7,
        data: days.map((d) => d.day_temp_c),
        itemStyle: { color: '#ea580c' }, lineStyle: { width: 3, color: '#ea580c' },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: '#16a34a', type: 'dashed', width: 1.5 },
          label: { formatter: '预冷目标 7°C', fontSize: 10, color: '#16a34a' },
          data: [{ yAxis: 7 }],
        },
      },
      {
        name: '夜间', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7,
        data: days.map((d) => d.night_temp_c),
        itemStyle: { color: '#0ea5e9' }, lineStyle: { width: 2, color: '#0ea5e9' },
      },
    ],
  }
})

const linkageItems = computed(() => {
  const signals = safeArray(w.value?.cold_chain_linkage?.signals)
  return signals.map((s) => ({
    label: s.label,
    value: s.value,
    className: s.level === 'warn' ? 'warn' : s.level === 'ok' ? 'ok' : '',
  }))
})

const targetRows = computed(() =>
  safeArray(w.value?.cold_chain_targets).map((t) => ({
    通道: t.label,
    '目标温区(°C)': t.target_c,
    说明: t.note,
  })),
)
</script>

<style scoped>
.weather-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 16px 0 18px; padding: 14px 16px; background: rgba(255,255,255,0.86); border: 1px solid rgba(148,163,184,0.22); border-radius: 12px; }
.weather-toolbar strong { display: block; font-size: 14px; color: #0f172a; }
.weather-toolbar span { display: block; margin-top: 4px; font-size: 12px; color: #64748b; word-break: break-all; }
.refresh-btn { border: 1px solid rgba(14,165,233,0.35); color: #0369a1; background: #f0f9ff; border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.refresh-btn:disabled { opacity: 0.65; cursor: wait; }
.forecast-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
.forecast-card { background: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(241,245,249,0.9)); border: 1px solid rgba(148,163,184,0.25); border-radius: 12px; padding: 12px 14px; }
.forecast-card.today { border-color: #ea580c; box-shadow: 0 0 0 2px rgba(234,88,12,0.12); }
.fc-date { font-size: 12px; color: #64748b; }
.fc-weather { font-size: 14px; font-weight: 600; color: #0f172a; margin: 6px 0; }
.fc-temp { font-size: 18px; font-weight: 700; }
.fc-temp .fc-day { color: #ea580c; }
.fc-temp .fc-night { color: #0ea5e9; }
.fc-wind { font-size: 11px; color: #94a3b8; margin-top: 4px; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.5; }
</style>
