<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-mark" style="width:48px;height:48px;border-radius:13px;display:flex;align-items:center;justify-content:center;font-size:26px;background:linear-gradient(135deg,#1f6d63,#38bdf8);box-shadow:0 6px 16px rgba(56,189,248,0.35);">🌿</div>
        <div class="brand-title">秋葵冷库优化 MIS</div>
        <div class="brand-subtitle">AI 增强多目标优化平台</div>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div v-if="errorMsg" class="login-error">{{ errorMsg }}</div>

        <div class="form-field">
          <label for="username">用户名</label>
          <input id="username" v-model.trim="username" type="text" placeholder="请输入用户名" autocomplete="username" required />
        </div>

        <div class="form-field">
          <label for="password">密码</label>
          <input id="password" v-model="password" type="password" placeholder="请输入密码" autocomplete="current-password" required />
        </div>

        <button class="login-btn" type="submit" :disabled="submitting">
          {{ submitting ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const submitting = ref(false)

// 如果已有 token，直接跳转
const existingToken = localStorage.getItem('token')
if (existingToken) {
  router.replace(route.query.redirect || '/overview')
}

async function handleLogin() {
  errorMsg.value = ''
  if (!username.value || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  submitting.value = true
  try {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
      }),
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: '登录失败' }))
      throw new Error(err.detail || err.message || `HTTP ${response.status}`)
    }
    const data = await response.json()
    const token = data.access_token || data.token
    if (token) {
      localStorage.setItem('token', token)
      const redirect = route.query.redirect || '/overview'
      router.replace(redirect)
    } else {
      throw new Error('响应中未包含 token')
    }
  } catch (err) {
    errorMsg.value = err.message || '登录失败，请检查网络'
  } finally {
    submitting.value = false
  }
}
</script>
