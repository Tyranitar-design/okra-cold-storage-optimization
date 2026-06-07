<template>
  <view class="app-root">
    <slot />
  </view>
</template>

<script>
// #ifdef MP-WEIXIN
import { api } from '@/api'
// #endif

export default {
  onLaunch() {
    this.persistSystemInfo()

    // #ifdef MP-WEIXIN
    this.silentWxLogin()
    // #endif

    // #ifdef APP-PLUS
    this.prepareAppRuntime()
    // #endif
  },
  onShow() {
    // #ifdef MP-WEIXIN
    this.checkMiniProgramUpdate()
    // #endif
  },
  methods: {
    // #ifdef MP-WEIXIN
    silentWxLogin() {
      uni.login({
        success: (res) => {
          if (res.code) {
            api.wxLogin(res.code).then(data => {
              if (data?.token) uni.setStorageSync('token', data.token)
            })
          }
        }
      })
    },
    // #endif
    persistSystemInfo() {
      // 系统信息（使用新版 API）
      try {
        const sys = uni.getAppBaseInfo?.() || {}
        const dev = uni.getDeviceInfo?.() || {}
        uni.setStorageSync('systemInfo', { ...sys, ...dev })
      } catch (e) { /* ignore */ }
    },
    // #ifdef APP-PLUS
    prepareAppRuntime() {
      uni.setStorageSync('appRuntime', {
        platform: 'app-plus',
        launchedAt: Date.now(),
      })
    },
    // #endif
    // #ifdef MP-WEIXIN
    checkMiniProgramUpdate() {
      // 检查更新（体验版）
      const updateManager = uni.getUpdateManager?.()
      if (updateManager) {
        updateManager.onCheckForUpdate(() => {})
        updateManager.onUpdateReady(() => {
          uni.showModal({
            title: '更新提示',
            content: '新版本已就绪，是否重启应用？',
            success: (res) => { if (res.confirm) updateManager.applyUpdate() }
          })
        })
      }
    }
    // #endif
  }
}
</script>

<style>
page { background: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif; }
</style>
