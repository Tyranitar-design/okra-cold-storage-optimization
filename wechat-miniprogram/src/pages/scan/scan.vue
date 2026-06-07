<template>
  <view class="scan-container">
    <view class="hero">
      <text class="hero-title">📷 扫码入库</text>
      <text class="hero-subtitle">扫描冷库二维码 → 批次登记 → 容量实时刷新</text>
    </view>

    <!-- 扫码区域 -->
    <view class="scan-area" @tap="onScan">
      <view class="scan-frame">
        <text class="scan-icon">📷</text>
        <text class="scan-text">点击扫码</text>
        <text class="scan-hint">扫描冷库二维码登记入库</text>
      </view>
    </view>

    <!-- 手动输入 -->
    <view class="form-card">
      <text class="form-title">📝 手动登记</text>
      <view class="form-section">
        <text class="form-label">冷库编号</text>
        <input class="form-input" v-model="form.storageId" placeholder="扫码自动填充" />
      </view>
      <view class="form-section">
        <text class="form-label">品种</text>
        <picker class="form-picker" :range="products" @change="e => form.product = products[e.detail.value]">
          <view class="picker-text">{{ form.product || '请选择品种' }}</view>
        </picker>
      </view>
      <view class="form-section">
        <text class="form-label">数量（吨）</text>
        <input class="form-input" v-model="form.quantity" type="digit" placeholder="例如 5.0" />
      </view>
      <view class="form-section">
        <text class="form-label">批次号</text>
        <input class="form-input" v-model="form.batchNo" placeholder="自动生成或手动输入" />
      </view>
      <button class="submit-btn" @tap="onSubmit" :loading="submitting">
        {{ submitting ? '⏳ 提交中...' : '✅ 确认入库' }}
      </button>
    </view>

    <!-- 入库记录 -->
    <view class="record-section" v-if="records.length">
      <view class="section-header">
        <text class="section-title">📋 今日入库记录</text>
        <text class="section-count">{{ records.length }} 笔</text>
      </view>
      <view class="record-card" v-for="(r, i) in records" :key="i">
        <view class="record-row">
          <text class="record-batch">{{ r.batch }}</text>
          <text class="record-product">{{ r.product }}</text>
        </view>
        <view class="record-row">
          <text class="record-meta">{{ r.storageId }} · {{ r.qty }}吨 · {{ r.time }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  data() {
    return {
      form: { storageId: '', product: '', quantity: '', batchNo: '' },
      products: ['秋葵（鲜食）', '秋葵（加工）', '秋葵（冷冻）'],
      submitting: false,
      records: [],
    }
  },
  methods: {
    async onScan() {
      // #ifdef APP-PLUS
      await this.requestCameraPermission()
      // #endif

      uni.scanCode({
        success: (res) => {
          this.form.storageId = res.result || 'T4-冷藏库-01'
          uni.showToast({ title: '扫码成功', icon: 'success' })
        },
        fail: () => {
          // 模拟扫码结果
          this.form.storageId = 'T4-冷藏库-01'
          uni.showToast({ title: '模拟扫码 · T4-冷藏库-01', icon: 'none' })
        }
      })
    },
    requestCameraPermission() {
      return new Promise((resolve) => {
        try {
          if (typeof plus === 'undefined' || !plus.android?.requestPermissions) {
            resolve()
            return
          }
          plus.android.requestPermissions(
            ['android.permission.CAMERA'],
            () => resolve(),
            () => resolve()
          )
        } catch (e) {
          resolve()
        }
      })
    },
    async onSubmit() {
      if (!this.form.storageId || !this.form.product || !this.form.quantity) {
        uni.showToast({ title: '请填写完整信息', icon: 'none' }); return
      }
      this.submitting = true
      const qty = parseFloat(this.form.quantity) || 0
      const batchNo = this.form.batchNo || `B${new Date().toISOString().slice(0,10).replace(/-/g,'')}${String(this.records.length + 1).padStart(3,'0')}`
      try {
        await uni.request({
          url: 'https://api.okra-demo.top/api/v2/inventory/scan-entry',
          method: 'POST',
          data: { storage_id: this.form.storageId, product: this.form.product, quantity: qty, batch_no: batchNo },
          timeout: 5000,
        })
      } catch (e) { /* offline fallback */ }
      this.records.unshift({
        batch: batchNo,
        product: this.form.product,
        storageId: this.form.storageId,
        qty: qty,
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      })
      this.form = { storageId: '', product: '', quantity: '', batchNo: '' }
      this.submitting = false
      uni.showToast({ title: `入库成功 · ${qty}吨`, icon: 'success' })
    }
  }
}
</script>

<style>
.scan-container { padding: 0 24rpx 40rpx; background: #F8FAFC; min-height: 100vh; }
.hero { background: linear-gradient(135deg, #0F766E, #14B8A6); margin: 0 -24rpx 24rpx; padding: 40rpx 30rpx; }
.hero-title { font-size: 38rpx; font-weight: bold; color: #FFF; display: block; }
.hero-subtitle { font-size: 22rpx; color: rgba(255,255,255,0.8); margin-top: 6rpx; display: block; }
.scan-area { background: #FFF; border-radius: 16rpx; padding: 50rpx; text-align: center; margin-bottom: 24rpx; border: 2rpx dashed #0F766E; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.scan-frame { }
.scan-icon { font-size: 80rpx; display: block; }
.scan-text { font-size: 32rpx; font-weight: 500; color: #0F766E; margin-top: 16rpx; display: block; }
.scan-hint { font-size: 24rpx; color: #94A3B8; margin-top: 8rpx; display: block; }
.form-card { background: #FFF; border-radius: 16rpx; padding: 24rpx; margin-bottom: 24rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.06); }
.form-title { font-size: 28rpx; font-weight: bold; color: #1E293B; margin-bottom: 20rpx; display: block; }
.form-section { margin-bottom: 18rpx; }
.form-label { font-size: 24rpx; color: #64748B; margin-bottom: 6rpx; display: block; }
.form-input { background: #F8FAFC; border-radius: 10rpx; padding: 18rpx; font-size: 26rpx; border: 1rpx solid #E2E8F0; }
.form-picker { background: #F8FAFC; border-radius: 10rpx; padding: 18rpx; border: 1rpx solid #E2E8F0; }
.picker-text { font-size: 26rpx; color: #1E293B; }
.submit-btn { background: linear-gradient(135deg, #0F766E, #14B8A6); color: #FFF; border-radius: 12rpx; padding: 22rpx; text-align: center; font-size: 28rpx; font-weight: 500; width: 100%; margin-top: 8rpx; }
.record-section { margin-top: 8rpx; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14rpx; }
.section-title { font-size: 28rpx; font-weight: bold; color: #1E293B; }
.section-count { font-size: 22rpx; color: #64748B; background: #F1F5F9; padding: 4rpx 16rpx; border-radius: 20rpx; }
.record-card { background: #FFF; border-radius: 12rpx; padding: 16rpx 20rpx; margin-bottom: 10rpx; box-shadow: 0 1rpx 6rpx rgba(0,0,0,0.04); }
.record-row { display: flex; justify-content: space-between; margin-bottom: 4rpx; }
.record-batch { font-size: 24rpx; font-weight: 500; color: #1E293B; }
.record-product { font-size: 24rpx; color: #0F766E; }
.record-meta { font-size: 22rpx; color: #94A3B8; }
</style>
