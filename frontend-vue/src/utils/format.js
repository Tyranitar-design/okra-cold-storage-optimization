export function formatNumber(value, digits = 0) {
  const num = Number(value)
  if (!Number.isFinite(num)) return value == null ? '-' : String(value)
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(num)
}

export function formatPercent(value, digits = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return value == null ? '-' : String(value)
  return `${num.toFixed(digits)}%`
}

export function formatSignedPercent(value, digits = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return value == null ? '-' : String(value)
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(digits)}%`
}

export function safeArray(value) {
  return Array.isArray(value) ? value : []
}

import { inject } from 'vue'

/**
 * Get the bootstrap data provided by App.vue.
 * Replaces the old `defineProps({ bootstrap })` pattern.
 */
export function useBootstrap() {
  return inject('bootstrap', null)
}

/**
 * Unified API fetch with Bearer auth token and automatic 401 handling.
 * Redirects to /login when the backend returns 401 Unauthorized.
 */
export async function apiFetch(url, options = {}) {
  const token = localStorage.getItem('token')
  const headers = { ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(error.message || error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}
