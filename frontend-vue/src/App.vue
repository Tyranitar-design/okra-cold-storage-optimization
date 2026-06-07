<template>
  <router-view v-if="isPublicRoute" :key="$route.path" />

  <ParticlesBg v-if="!isPublicRoute" />
  <el-container v-if="!isPublicRoute" class="app-shell">
    <el-aside class="sidebar" width="264px">
      <div class="brand">
        <div class="brand-mark">秋</div>
        <div>
          <div class="brand-title">秋葵冷库优化 MIS</div>
          <div class="brand-subtitle">AI 增强多目标优化平台</div>
        </div>
      </div>

      <el-scrollbar class="nav-scroll">
        <el-menu
          :default-active="$route.path"
          class="nav-menu"
          router
        >
          <el-menu-item
            v-for="item in navItems"
            :key="item.key"
            :index="item.route"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu>
      </el-scrollbar>

      <el-card class="sidebar-status" shadow="never">
        <div class="status-card-head">
          <el-tag :type="bootstrapTagType" size="small">{{ bootstrapStateLabel }}</el-tag>
          <span class="ws-indicator">
            <span class="ws-dot" :class="wsStatus"></span>
            {{ wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中' : '未连接' }}
          </span>
        </div>
        <div class="note-line">数据源：{{ dbBackendLabel }}</div>
        <div class="note-line">底图：{{ mapProviderLabel }}</div>
      </el-card>
    </el-aside>

    <el-container class="workspace">
      <el-header class="topbar" height="72px">
        <div class="topbar-title">
          <h1>{{ currentMeta.label }}</h1>
          <p>{{ currentMeta.subtitle }}</p>
        </div>
        <div class="topbar-actions">
          <el-button :icon="RefreshRight" plain @click="reload">刷新</el-button>
          <el-tag :type="bootstrapTagType">{{ bootstrapStateLabel }}</el-tag>
          <el-button :icon="SwitchButton" text @click="logout">退出</el-button>
        </div>
      </el-header>

      <el-main class="main">
        <transition name="view-fade" mode="out-in">
          <router-view :key="$route.path" />
        </transition>
      </el-main>
    </el-container>

    <AgentAssistant @refresh="reload" />
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Aim,
  Box,
  Connection,
  Cpu,
  DataAnalysis,
  Document,
  Download,
  Files,
  Histogram,
  Location,
  MapLocation,
  Odometer,
  Operation,
  RefreshRight,
  SwitchButton,
  TrendCharts,
} from '@element-plus/icons-vue'
import AgentAssistant from './components/AgentAssistant.vue'
import ParticlesBg from './components/ParticlesBg.vue'
import { wsClient } from './utils/ws'

const route = useRoute()
const router = useRouter()
const isPublicRoute = computed(() => Boolean(route.meta.public))

// ===== Navigation items =====
const navItems = [
  { key: 'overview', route: '/overview', label: '总览看板', icon: Odometer, subtitle: '关键指标、就绪度与系统状态' },
  { key: 'map', route: '/map', label: '地图选址', icon: MapLocation, subtitle: '高德底图 · 候选冷库与需求点分布' },
  { key: 'nodes', route: '/nodes', label: '节点管理', icon: Location, subtitle: '冷库、客户、配送站 CRUD' },
  { key: 'routes', route: '/routes', label: '路线管理', icon: Connection, subtitle: '路线方案与站点编排' },
  { key: 'weather', route: '/weather', label: '实时气象', icon: Histogram, subtitle: '39 节点气象 · 4 天预报 · 冷链温区联动' },
  { key: 'aisolve', route: '/aisolve', label: 'AI 增强求解', icon: Cpu, subtitle: 'AI warm start 7.3× 加速 + 四方法对比' },
  { key: 'solve', route: '/solve', label: '算法求解过程', icon: Operation, subtitle: '直解主线收敛 + Benders cut ranking / robustness 子线' },
  { key: 'pareto', route: '/pareto', label: '多目标 Pareto', icon: TrendCharts, subtitle: '成本 / 腐损 / 碳排放三目标前沿' },
  { key: 'analysis', route: '/analysis', label: '分析可视化', icon: DataAnalysis, subtitle: '成本结构、场景与灵敏度' },
  { key: 'whatif', route: '/whatif', label: 'What-If 决策', icon: Aim, subtitle: '调参实时对比选址压力变化' },
  { key: 'model', route: '/model', label: '数学模型', icon: Document, subtitle: '双层多目标 MIP 形式化' },
  { key: 'ai', route: '/ai', label: 'AI 融合增强', icon: Box, subtitle: 'ML / DL / RL 在优化中的角色' },
  { key: 'evidence', route: '/evidence', label: '数据与证据链', icon: Files, subtitle: '数据库、证据登记与物流契约' },
  { key: 'export', route: '/export', label: '论文证据导出', icon: Download, subtitle: '一键导出 LaTeX 表格 / Word 报告' },
]

const currentMeta = computed(() => {
  const found = navItems.find((n) => n.route === route.path)
  return found || navItems[0]
})

// ===== Bootstrap loading (from original App.vue) =====
const bootstrap = ref(null)
const error = ref('')

// Provide bootstrap to all child views (replaces the old :bootstrap prop)
provide('bootstrap', bootstrap)

const bootstrapStateLabel = computed(() => (error.value ? '离线兜底' : bootstrap.value ? '已联通' : '加载中'))
const bootstrapTagType = computed(() => (error.value ? 'warning' : bootstrap.value ? 'success' : 'info'))
const dbBackendLabel = computed(() => (bootstrap.value?.db_probe?.query_ready ? 'PostgreSQL' : '文件兜底'))
const mapProviderLabel = computed(() => bootstrap.value?.map_provider_status?.summary?.browser_provider_ready ? '高德 AMap' : '文件点位')

async function reload() {
  error.value = ''
  try {
    const token = localStorage.getItem('token')
    const headers = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const response = await fetch('/api/v1/dashboard/bootstrap', { headers })
    if (response.status === 401) {
      localStorage.removeItem('token')
      router.push({ name: 'login', query: { redirect: route.fullPath } })
      return
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    bootstrap.value = await response.json()
  } catch (err) {
    if (err instanceof Error && err.message === 'Unauthorized') return
    error.value = err instanceof Error ? err.message : String(err)
  }
}

// ===== WebSocket connection =====
const wsStatus = ref('disconnected')
const WS_CHANNEL = 'data_changes'
let wsInterval = null

function connectWs() {
  const token = localStorage.getItem('token')
  if (!token) return
  try {
    wsClient.connect(WS_CHANNEL, token)
    wsClient.on(WS_CHANNEL, handleWsMessage)
    wsStatus.value = wsClient.getStatus(WS_CHANNEL)
    wsInterval = setInterval(() => {
      wsStatus.value = wsClient.getStatus(WS_CHANNEL)
    }, 3000)
  } catch {
    // WebSocket might not be available
  }
}

function handleWsMessage(data) {
  if (data.type === 'bootstrap_update' || data.type === 'data_update') {
    bootstrap.value = data.payload || data.data || bootstrap.value
  }
}

function disconnectWs() {
  wsClient.disconnect(WS_CHANNEL)
  wsClient.off(WS_CHANNEL, handleWsMessage)
  if (wsInterval) {
    clearInterval(wsInterval)
    wsInterval = null
  }
  wsStatus.value = 'disconnected'
}

// ===== Logout =====
function logout() {
  disconnectWs()
  localStorage.removeItem('token')
  router.push('/login')
}

// ===== Lifecycle =====
onMounted(() => {
  if (!isPublicRoute.value) {
    reload()
    connectWs()
  }
})

watch(isPublicRoute, (isPublic) => {
  if (isPublic) {
    disconnectWs()
    return
  }
  reload()
  connectWs()
})

onUnmounted(() => {
  disconnectWs()
})
</script>
