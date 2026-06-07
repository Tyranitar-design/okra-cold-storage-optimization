<template>
  <div class="amap-wrap">
    <div class="amap-toolbar">
      <span class="amap-badge" :class="statusClass">{{ statusLabel }}</span>
      <span class="amap-legend"><i class="dot ai"></i>AI top-8 推荐选址</span>
      <span class="amap-legend"><i class="dot cand"></i>候选冷库</span>
      <span class="amap-legend"><i class="dot demand"></i>需求点（按产量）</span>
      <span class="amap-legend"><i class="line road"></i>OSM 路网</span>
      <span class="amap-meta">点位 {{ features.length }} · 路网 {{ roadEdgeCount }} 段 / {{ roadKm }} km · 来源 {{ sourceBackend }}</span>
    </div>

    <div v-show="mapReady" class="amap-controls">
      <label class="ctrl"><input type="checkbox" v-model="showRoads" :disabled="!mapReady || !roadsAvailable" @change="syncRoadLayer" /> 显示路网</label>
      <label class="ctrl">路网密度：
        <select v-model="roadLevel" :disabled="!mapReady || !showRoads" @change="reloadRoads">
          <option value="major">主干道</option>
          <option value="mid">主干+次干</option>
          <option value="all">全部（较慢）</option>
        </select>
      </label>
      <label class="ctrl"><input type="checkbox" v-model="showAiSites" :disabled="!mapReady || !aiSitesAvailable" @change="syncAiLayer" /> 高亮 AI 选址</label>
      <span v-if="roadLoading" class="ctrl loading">路网加载中…</span>
    </div>

    <!-- Real AMap basemap container -->
    <div v-show="mapReady" ref="mapEl" class="amap-canvas"></div>

    <!-- Graceful fallback: file-based CSS scatter when no browser key -->
    <div v-if="!mapReady" class="map-box fallback">
      <svg v-if="fallbackRoadSegments.length" class="fallback-roads" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polyline
          v-for="road in fallbackRoadSegments"
          :key="road.id"
          :points="road.points"
          class="fallback-road"
          :class="road.className"
        />
      </svg>
      <div
        v-for="point in fallbackPoints"
        :key="point.id"
        class="map-point"
        :class="{ hot: point.candidate, ai: point.ai }"
        :style="{ left: point.left, top: point.top }"
        :title="point.label"
      />
      <div class="fallback-note">{{ fallbackNote }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const mapEl = ref(null)
const mapReady = ref(false)
const features = ref([])
const sourceBackend = ref('-')
const provider = ref('file')
const keyAvailable = ref(false)
const loadError = ref('')

const showRoads = ref(true)
const showAiSites = ref(true)
const roadLevel = ref('major')
const roadLoading = ref(false)
const roadEdgeCount = ref(0)
const roadKm = ref(0)
const roadsAvailable = ref(false)
const roadFeatures = ref([])
const aiSitesAvailable = ref(false)
const aiTopIds = ref([])

// AMap object handles kept module-scoped (not reactive) to avoid proxy overhead.
let amapRef = null
let mapRef = null
let roadPolylines = []
let aiMarkers = []

const statusLabel = computed(() => {
  if (mapReady.value) return `高德底图已加载 (${provider.value})`
  if (loadError.value) return `底图降级：${loadError.value}`
  return '文件点位兜底（未启用浏览器底图）'
})
const statusClass = computed(() => (mapReady.value ? 'ok' : 'warn'))
const fallbackNote = computed(() =>
  keyAvailable.value
    ? '高德 JS API 加载失败，已回退到文件点位视图'
    : '未启用浏览器地图 Key（OKRA_MAP_PUBLIC_KEY_ALLOWED 未开启），展示文件点位',
)

// CSS-scatter fallback positions (same projection as the old view).
const fallbackPoints = computed(() => {
  const fs = features.value
  if (!fs.length) return []
  const aiSet = new Set(aiTopIds.value)
  const xs = fs.map((f) => Number(f?.geometry?.coordinates?.[0] ?? 0))
  const ys = fs.map((f) => Number(f?.geometry?.coordinates?.[1] ?? 0))
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  return fs.slice(0, 60).map((f) => {
    const [lon, lat] = f.geometry.coordinates
    const nodeId = f.properties?.node_id || f.id
    return {
      id: nodeId,
      label: f.properties?.name || '点位',
      candidate: Boolean(f.properties?.candidate),
      ai: aiSet.has(nodeId),
      left: `${(((lon - minX) / spanX) * 88 + 6).toFixed(2)}%`,
      top: `${(100 - (((lat - minY) / spanY) * 88 + 6)).toFixed(2)}%`,
    }
  })
})

const fallbackBounds = computed(() => {
  const pointCoords = features.value
    .map((f) => f?.geometry?.coordinates)
    .filter((c) => Array.isArray(c) && c.length >= 2)
  const xs = pointCoords.map((c) => Number(c[0]))
  const ys = pointCoords.map((c) => Number(c[1]))
  if (!xs.length || !ys.length) return null
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  return { minX, maxX, minY, maxY, spanX: maxX - minX || 1, spanY: maxY - minY || 1 }
})

const fallbackRoadSegments = computed(() => {
  const bounds = fallbackBounds.value
  if (!bounds || !showRoads.value || !roadFeatures.value.length) return []
  return roadFeatures.value.slice(0, 900).map((edge, idx) => {
    const points = (edge.coordinates || [])
      .map((c) => {
        const lon = Number(c[0])
        const lat = Number(c[1])
        const x = ((lon - bounds.minX) / bounds.spanX) * 88 + 6
        const y = 100 - (((lat - bounds.minY) / bounds.spanY) * 88 + 6)
        return `${x.toFixed(2)},${y.toFixed(2)}`
      })
      .join(' ')
    const highway = String(edge.highway || '')
    return {
      id: `${highway || 'road'}-${idx}`,
      points,
      className: highway.includes('trunk') || highway.includes('primary') ? 'major' : 'minor',
    }
  }).filter((road) => road.points.includes(' '))
})

function loadAmapScript(key, securityCode) {
  return new Promise((resolve, reject) => {
    if (window.AMap) return resolve(window.AMap)
    if (securityCode) {
      window._AMapSecurityConfig = { securityJsCode: securityCode }
    }
    const s = document.createElement('script')
    s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`
    s.async = true
    s.onload = () => (window.AMap ? resolve(window.AMap) : reject(new Error('AMap 未注入')))
    s.onerror = () => reject(new Error('AMap 脚本加载失败'))
    document.head.appendChild(s)
  })
}

async function fetchJson(url) {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

const ROAD_COLOR = {
  motorway: '#dc2626', trunk: '#ea580c', primary: '#f59e0b', secondary: '#0ea5e9',
  motorway_link: '#dc2626', trunk_link: '#ea580c', primary_link: '#f59e0b', secondary_link: '#0ea5e9',
  tertiary: '#94a3b8', unclassified: '#cbd5e1',
}
function roadColor(h) { return ROAD_COLOR[h] || '#94a3b8' }
function roadWeight(h) {
  if (h === 'motorway' || h === 'trunk') return 3
  if (h === 'primary' || h === 'secondary') return 2
  return 1
}

function clearRoadLayer() {
  if (mapRef && roadPolylines.length) mapRef.remove(roadPolylines)
  roadPolylines = []
}

function renderRoadLayer(edges) {
  if (!amapRef || !mapRef) return
  clearRoadLayer()
  const lines = []
  edges.forEach((e) => {
    const path = (e.coordinates || []).map((c) => [Number(c[0]), Number(c[1])])
    if (path.length < 2) return
    lines.push(new amapRef.Polyline({
      path,
      strokeColor: roadColor(e.highway),
      strokeWeight: roadWeight(e.highway),
      strokeOpacity: 0.55,
      lineJoin: 'round',
      zIndex: 20,
      bubble: true,
    }))
  })
  roadPolylines = lines
  if (lines.length) mapRef.add(lines)
}

async function fetchRoadData() {
  roadLoading.value = true
  try {
    const data = await fetchJson(`/api/v1/map/road-network?level=${encodeURIComponent(roadLevel.value)}`)
    roadsAvailable.value = Boolean(data.available)
    roadEdgeCount.value = Number(data.edge_count || 0)
    roadKm.value = Number(data.total_km || 0)
    roadFeatures.value = Array.isArray(data.edges) ? data.edges : []
    return roadFeatures.value
  } catch (err) {
    loadError.value = `路网加载失败：${err.message}`
    roadFeatures.value = []
    return []
  } finally {
    roadLoading.value = false
  }
}

async function reloadRoads() {
  if (!showRoads.value) return
  const edges = await fetchRoadData()
  if (mapReady.value) renderRoadLayer(edges)
}

function syncRoadLayer() {
  if (!mapReady.value) return
  if (showRoads.value) {
    if (roadPolylines.length) {
      roadPolylines.forEach((l) => l.show())
    } else {
      reloadRoads()
    }
  } else {
    roadPolylines.forEach((l) => l.hide())
  }
}

function clearAiLayer() {
  if (mapRef && aiMarkers.length) mapRef.remove(aiMarkers)
  aiMarkers = []
}

function renderAiLayer(aiFeatures) {
  if (!amapRef || !mapRef) return
  clearAiLayer()
  const markers = []
  aiFeatures.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates
    const p = f.properties || {}
    const marker = new amapRef.Marker({
      position: [lon, lat],
      offset: new amapRef.Pixel(-13, -13),
      zIndex: 200,
      content: `<div class="ai-pin" title="AI 推荐 #${p.rank} ${p.name}">★<span class="ai-rank">${p.rank}</span></div>`,
    })
    marker.on('mouseover', () => {
      const info = new amapRef.InfoWindow({
        content: `<div style="font-size:12px"><b>AI 推荐选址 #${p.rank}</b><br/>${p.name} (${p.node_id})<br/>开放概率 ${(Number(p.score) * 100).toFixed(1)}%<br/>产量 ${Number(p.okra_production_ton || 0).toFixed(1)} 吨</div>`,
        offset: new amapRef.Pixel(0, -16),
      })
      info.open(mapRef, [lon, lat])
      marker._info = info
    })
    marker.on('mouseout', () => marker._info && marker._info.close())
    markers.push(marker)
  })
  aiMarkers = markers
  if (markers.length) mapRef.add(markers)
}

async function loadAiSites() {
  try {
    const data = await fetchJson('/api/v1/map/ai-recommended-sites')
    aiSitesAvailable.value = Boolean(data.available)
    aiTopIds.value = Array.isArray(data.top_k_ids) ? data.top_k_ids : []
    if (showAiSites.value) renderAiLayer(Array.isArray(data.features) ? data.features : [])
  } catch (err) {
    // AI overlay is optional; keep the map usable if it fails.
    aiSitesAvailable.value = false
  }
}

function syncAiLayer() {
  if (!mapReady.value) return
  if (showAiSites.value) {
    if (aiMarkers.length) aiMarkers.forEach((m) => m.show())
    else loadAiSites()
  } else {
    aiMarkers.forEach((m) => m.hide())
  }
}

function renderMarkers(AMap, map) {
  const aiSet = new Set(aiTopIds.value)
  const productions = features.value
    .map((f) => Number(f.properties?.okra_production_ton || 0))
    .filter((v) => v > 0)
  const maxProd = productions.length ? Math.max(...productions) : 1
  const positions = []
  features.value.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates
    const nodeId = f.properties?.node_id
    const cand = Boolean(f.properties?.candidate)
    const isAi = aiSet.has(nodeId)
    const prod = Number(f.properties?.okra_production_ton || 0)
    const r = cand ? 9 : 4 + Math.round((prod / maxProd) * 7)
    // AI-recommended candidates de-emphasised here (the star marker layer owns them).
    const color = cand ? '#d62728' : '#1f77b4'
    const marker = new AMap.CircleMarker({
      center: [lon, lat],
      radius: r,
      strokeColor: isAi ? '#7c3aed' : '#fff',
      strokeWeight: isAi ? 2 : 1,
      fillColor: color,
      fillOpacity: cand ? 0.92 : 0.6,
      cursor: 'pointer',
      zIndex: cand ? 120 : 60,
    })
    const name = f.properties?.name || nodeId || '点位'
    marker.on('mouseover', () => {
      const info = new AMap.InfoWindow({
        content: `<div style="font-size:12px"><b>${name}</b><br/>${cand ? '冷库候选/已选' : '需求点'}${isAi ? '<br/>★ AI 推荐选址' : ''}<br/>产量 ${prod.toFixed(1)} 吨</div>`,
        offset: new AMap.Pixel(0, -6),
      })
      info.open(map, [lon, lat])
      marker._info = info
    })
    marker.on('mouseout', () => marker._info && marker._info.close())
    map.add(marker)
    positions.push([lon, lat])
  })
  if (positions.length) {
    map.setFitView(null, false, [30, 30, 30, 30])
  }
}

onMounted(async () => {
  // 1. load points (database-first via API)
  try {
    const geo = await fetchJson('/api/v1/storages/map')
    features.value = Array.isArray(geo.features) ? geo.features : []
    sourceBackend.value = geo.source_backend || '-'
  } catch (err) {
    loadError.value = `点位加载失败：${err.message}`
    return
  }
  // 2. load map config and decide basemap vs fallback
  let cfg = {}
  try {
    cfg = await fetchJson('/api/v1/map/config')
  } catch (err) {
    loadError.value = `地图配置加载失败：${err.message}`
    return
  }
  provider.value = cfg.provider || 'file'
  keyAvailable.value = Boolean(cfg.js_key_available)

  // load AI top-8 ids early so both basemap markers and fallback can highlight them
  try {
    const ai = await fetchJson('/api/v1/map/ai-recommended-sites')
    aiSitesAvailable.value = Boolean(ai.available)
    aiTopIds.value = Array.isArray(ai.top_k_ids) ? ai.top_k_ids : []
  } catch (err) {
    aiSitesAvailable.value = false
  }

  if (!cfg.js_key_available || !cfg.js_key) {
    if (showRoads.value) await fetchRoadData()
    return // graceful fallback to CSS scatter + OSM road snapshot
  }
  // 3. load AMap and render
  try {
    const AMap = await loadAmapScript(cfg.js_key, cfg.security_code)
    amapRef = AMap
    const map = new AMap.Map(mapEl.value, {
      zoom: cfg.default_zoom || 9,
      center: cfg.default_center || [111.69, 29.05],
      viewMode: '2D',
      mapStyle: 'amap://styles/whitesmoke',
    })
    mapRef = map
    mapReady.value = true
    const onReady = () => {
      if (showRoads.value) reloadRoads()
      renderMarkers(AMap, map)
      if (showAiSites.value) loadAiSites()
    }
    map.on('complete', onReady)
    // also render immediately in case 'complete' already fired
    onReady()
  } catch (err) {
    loadError.value = err.message
    mapReady.value = false
  }
})
</script>

<style scoped>
.amap-wrap { display: flex; flex-direction: column; gap: 8px; }
.amap-toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 12px; color: #4a5568; }
.amap-badge { padding: 2px 10px; border-radius: 999px; font-weight: 600; }
.amap-badge.ok { background: #e6f7ee; color: #1b7a45; }
.amap-badge.warn { background: #fef3e6; color: #ad6313; }
.amap-legend { display: inline-flex; align-items: center; gap: 5px; }
.amap-legend .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.amap-legend .dot.cand { background: #d62728; }
.amap-legend .dot.demand { background: #1f77b4; }
.amap-legend .dot.ai { background: #7c3aed; }
.amap-legend .line { width: 16px; height: 0; border-top: 3px solid #dc2626; display: inline-block; }
.amap-meta { margin-left: auto; color: #718096; }
.amap-controls { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #475569; }
.amap-controls .ctrl { display: inline-flex; align-items: center; gap: 6px; }
.amap-controls select { padding: 3px 6px; border-radius: 8px; border: 1px solid #cbd5e1; }
.amap-controls .loading { color: #d97706; }
.amap-canvas { width: 100%; height: 460px; border-radius: 10px; overflow: hidden; }
.map-box.fallback { position: relative; width: 100%; height: 460px; background: linear-gradient(135deg, #eef2f7, #f7fafc); border-radius: 10px; overflow: hidden; }
.fallback-roads { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.fallback-road { fill: none; stroke: #94a3b8; stroke-width: 0.16; stroke-opacity: 0.38; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
.fallback-road.major { stroke: #ea580c; stroke-width: 0.28; stroke-opacity: 0.5; }
.fallback-road.minor { stroke: #64748b; stroke-opacity: 0.28; }
.map-point { position: absolute; width: 8px; height: 8px; border-radius: 50%; background: #1f77b4; transform: translate(-50%, -50%); }
.map-point.hot { width: 13px; height: 13px; background: #d62728; box-shadow: 0 0 0 3px rgba(214,39,40,0.18); }
.map-point.ai { background: #7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,0.25); }
.fallback-note { position: absolute; left: 12px; bottom: 10px; font-size: 11px; color: #8a94a6; background: rgba(255,255,255,0.7); padding: 3px 8px; border-radius: 6px; }
:deep(.ai-pin) { position: relative; width: 26px; height: 26px; line-height: 26px; text-align: center; color: #fff; background: #7c3aed; border: 2px solid #fff; border-radius: 50%; font-size: 14px; box-shadow: 0 2px 6px rgba(124,58,237,0.45); }
:deep(.ai-pin .ai-rank) { position: absolute; top: -6px; right: -6px; min-width: 14px; height: 14px; line-height: 14px; font-size: 10px; background: #facc15; color: #1f2937; border-radius: 7px; padding: 0 2px; }
</style>
