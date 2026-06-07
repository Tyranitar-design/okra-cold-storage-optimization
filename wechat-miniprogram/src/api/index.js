/**
 * 秋葵冷库优化小程序 — API 模块
 * 优先调后端接口，异常时回落至 mockData
 */
import { mockData } from '@/utils/mockData'

const DEFAULT_BASE_URL = 'http://106.14.181.83/api/v1'
const LEGACY_BASE_URL = 'https://api.okra-demo.top/api/v2'
const TIMEOUT = 15000

export function getBaseUrl() {
  const stored = uni.getStorageSync('OKRA_API_BASE_URL')
  // #ifdef H5
  const envBase = import.meta?.env?.VITE_OKRA_API_BASE_URL || import.meta?.env?.VITE_API_BASE_URL
  // #endif
  // #ifndef H5
  const envBase = ''
  // #endif
  return (stored || envBase || DEFAULT_BASE_URL).replace(/\/$/, '')
}

export function setBaseUrl(url) {
  if (url) uni.setStorageSync('OKRA_API_BASE_URL', url.replace(/\/$/, ''))
}

async function request(path, options = {}) {
  const token = uni.getStorageSync('token')
  const header = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...options.header,
  }
  try {
    const res = await uni.request({
      url: `${getBaseUrl()}${path}`,
      method: options.method || 'GET',
      data: options.data,
      header,
      timeout: options.timeout || TIMEOUT,
    })
    if (res.statusCode === 401) {
      uni.removeStorageSync('token')
      return null
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      console.warn(`[API] ${path} returned ${res.statusCode}, using fallback`)
      return null
    }
    return res.data
  } catch (e) {
    console.warn(`[API] ${path} unavailable, using fallback:`, e.message)
    return null
  }
}

async function legacyRequest(path, options = {}) {
  try {
    const res = await uni.request({
      url: `${LEGACY_BASE_URL}${path}`,
      method: options.method || 'GET',
      data: options.data,
      header: { 'Content-Type': 'application/json', ...options.header },
      timeout: options.timeout || TIMEOUT,
    })
    if (res.statusCode < 200 || res.statusCode >= 300) return null
    return res.data
  } catch (e) {
    return null
  }
}

export const api = {
  /* ── 认证 ── */
  wxLogin: (code) => request('/auth/wx-login', { method: 'POST', data: { code } }),

  /* ── 冷库布局 ── */
  getLatestLayout: () => request('/optimization/latest-layout'),

  /* ── 选址推荐 ── */
  getRecommend: async (data) => request('/optimization/recommend', { method: 'POST', data, timeout: 30000 })
    || legacyRequest('/optimization/recommend', { method: 'POST', data, timeout: 30000 }),

  /* ── AI / Agent 证据层 ── */
  chatAgent: (message, context = {}) => request('/agent/chat', { method: 'POST', data: { message, context } }),
  getAiWarmstartReport: () => request('/experiments/ai-warmstart-report'),
  getAiFusion: () => request('/ai/fusion'),

  /* ── 气象预警 ── */
  getWeatherAlert: () => request('/weather/panel'),
  getWeatherPanel: () => request('/weather/panel'),
  refreshWeather: (options = {}) => {
    const force = options.force ? 'true' : 'false'
    const maxAge = options.maxAgeSeconds == null ? 300 : Number(options.maxAgeSeconds)
    return request(`/weather/refresh?force=${force}&max_age_seconds=${maxAge}`)
  },

  /* ── 扫码入库 ── */
  scanEntry: (data) => request('/inventory/scan-entry', { method: 'POST', data }),

  /* ── 我的冷库 ── */
  getMyStorage: () => request('/storage/my-storage'),

  /* ── 物流路线 ── */
  getLogisticsRoute: (data) => request('/logistics/route', { method: 'POST', data }),
}

export default api

/* ── 回落数据工厂 ── */
export function fallback(endpoint) {
  switch (endpoint) {
    case 'latest-layout': return { facilities: mockData.facilities, cost: mockData.kpi.optimalCost, gap: mockData.kpi.mipGap }
    case 'recommend': return mockData.recommendFallback
    case 'weather': return { alert: null, advice: mockData.weather.advice, current: mockData.weather.current }
    case 'my-storage': return mockData.storage
    case 'logistics': return { routes: mockData.logistics.routes }
    default: return null
  }
}
