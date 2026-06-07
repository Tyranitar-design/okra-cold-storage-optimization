<template>
  <div>
    <!-- 参数调节 -->
    <section class="content-grid single">
      <PanelCard title="What-If 决策参数" subtitle="调整参数后实时跑 solver-free 容量筛选，对比选址压力变化" badge="P4" badge-class="ok">
        <div class="whatif-controls">
          <div class="ctrl-group">
            <label>最大设施数 <b>{{ maxFacilities }}</b></label>
            <input type="range" min="3" max="15" step="1" v-model.number="maxFacilities" />
          </div>
          <div class="ctrl-group">
            <label>碳价 <b>{{ carbonPrice }}</b> 元/吨</label>
            <input type="range" min="0" max="300" step="10" v-model.number="carbonPrice" />
          </div>
          <div class="ctrl-group">
            <label>收获峰值因子 <b>{{ peakFactor.toFixed(1) }}</b></label>
            <input type="range" min="1.0" max="2.5" step="0.1" v-model.number="peakFactor" />
          </div>
        </div>

        <div class="share-controls">
          <div class="share-title">下游通道份额（自动归一化，预冷固定 100%）</div>
          <div class="share-row">
            <span>冷藏 {{ (shareCold * 100).toFixed(0) }}%</span>
            <input type="range" min="0" max="1" step="0.05" v-model.number="shareCold" />
            <span>气调 {{ (shareCa * 100).toFixed(0) }}%</span>
            <input type="range" min="0" max="1" step="0.05" v-model.number="shareCa" />
            <span>冷冻 {{ (shareFrozen * 100).toFixed(0) }}%</span>
            <input type="range" min="0" max="1" step="0.05" v-model.number="shareFrozen" />
          </div>
        </div>

        <div class="whatif-actions">
          <button class="btn" @click="runWhatIf" :disabled="loading">{{ loading ? '计算中…' : '▶ 运行 What-If' }}</button>
          <button class="btn ghost" @click="resetParams" :disabled="loading">↺ 恢复基线</button>
          <span v-if="error" class="err">{{ error }}</span>
        </div>
        <p class="boundary-note">{{ researchBoundary }}</p>
      </PanelCard>
    </section>

    <!-- 对比结果 -->
    <section v-if="result" class="kpi-grid">
      <KpiAnimated label="设施数下界变化" :value="deltaFacilities" :decimals="0"
                   :delta="`基线 ${baseLB} → 调参 ${tunedLB}`" :delta-class="deltaFacilities > 0 ? 'warn' : 'positive'" />
      <KpiAnimated label="峰值库存变化" :value="deltaPeak" suffix="吨" :decimals="0"
                   :delta="`基线 ${basePeak} → ${tunedPeak}`" :delta-class="deltaPeak > 0 ? 'warn' : 'positive'" />
      <KpiAnimated label="容量压力变化" :value="deltaPressurePct" suffix="%" :decimals="1"
                   :delta="pressureDeltaNote" :delta-class="deltaPressure > 0 ? 'warn' : 'positive'" />
      <KpiAnimated label="可行性状态" :value="0" :decimals="0"
                   :delta="stateChangeNote" :delta-class="stateChanged ? 'warn' : 'positive'"
                   :class="'state-kpi'" />
    </section>

    <section v-if="result" class="content-grid stagger">
      <PanelCard title="基线 vs What-If 对比" subtitle="solver-free 容量压力筛选" badge="对比" badge-class="ok">
        <SectionTable :headers="['指标', '基线', 'What-If', '变化']" :rows="compareRows" />
      </PanelCard>
      <PanelCard title="通道容量压力（What-If）" subtitle="各通道峰值库存 vs 最大容量档" badge="通道" badge-class="neutral">
        <SectionTable :headers="['通道', '年流量(吨)', '峰值库存(吨)', '设施下界']" :rows="channelRows" />
      </PanelCard>
    </section>

    <section v-if="result" class="content-grid single">
      <PanelCard title="碳价说明" subtitle="为什么碳价不改变这个筛选结果" badge="诚实边界" badge-class="warn">
        <p class="note-box">{{ carbonNote }}</p>
        <p class="boundary-note">想看碳价对最优选址的真实影响？请用「算法求解过程」页的实时求解触发器跑一次 Gurobi。</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import SectionTable from '../components/SectionTable.vue'
import KpiAnimated from '../components/KpiAnimated.vue'
import { formatNumber, safeArray, useBootstrap } from '../utils/format'

// baseline defaults (current v3.0 assumptions)
const BASE = { maxFacilities: 8, carbonPrice: 50, peakFactor: 1.8, cold: 0.6, ca: 0.3, frozen: 0.1 }

const maxFacilities = ref(BASE.maxFacilities)
const carbonPrice = ref(BASE.carbonPrice)
const peakFactor = ref(BASE.peakFactor)
const shareCold = ref(BASE.cold)
const shareCa = ref(BASE.ca)
const shareFrozen = ref(BASE.frozen)

const loading = ref(false)
const error = ref('')
const result = ref(null)

function resetParams() {
  maxFacilities.value = BASE.maxFacilities
  carbonPrice.value = BASE.carbonPrice
  peakFactor.value = BASE.peakFactor
  shareCold.value = BASE.cold
  shareCa.value = BASE.ca
  shareFrozen.value = BASE.frozen
}

async function runWhatIf() {
  loading.value = true
  error.value = ''
  try {
    const body = {
      max_facilities: maxFacilities.value,
      carbon_price: carbonPrice.value,
      harvest_peak_factor: peakFactor.value,
      channel_shares: { cold: shareCold.value, ca: shareCa.value, frozen: shareFrozen.value },
    }
    const resp = await fetch('/api/v1/whatif/screen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    result.value = await resp.json()
  } catch (err) {
    error.value = `计算失败：${err.message}`
  } finally {
    loading.value = false
  }
}

const baseSummary = computed(() => result.value?.baseline?.summary || {})
const tunedSummary = computed(() => result.value?.whatif?.summary || {})
const delta = computed(() => result.value?.delta || {})

const baseLB = computed(() => Number(baseSummary.value.lower_bound_facilities || 0))
const tunedLB = computed(() => Number(tunedSummary.value.lower_bound_facilities || 0))
const deltaFacilities = computed(() => Number(delta.value.lower_bound_facilities || 0))
const basePeak = computed(() => Math.round(Number(baseSummary.value.total_peak_capacity_load_ton || 0)))
const tunedPeak = computed(() => Math.round(Number(tunedSummary.value.total_peak_capacity_load_ton || 0)))
const deltaPeak = computed(() => Number(delta.value.total_peak_capacity_load_ton || 0))
const deltaPressure = computed(() => Number(delta.value.facility_pressure_delta || 0))
const deltaPressurePct = computed(() => deltaPressure.value * 100)
const stateChanged = computed(() => Boolean(delta.value.screen_state_changed))

const pressureDeltaNote = computed(() => {
  const base = Number(baseSummary.value.facility_pressure || 0)
  const tuned = Number(tunedSummary.value.facility_pressure || 0)
  return `基线 ${(base * 100).toFixed(0)}% → ${(tuned * 100).toFixed(0)}%`
})
const stateChangeNote = computed(() => {
  const bs = result.value?.baseline?.screen_state || '-'
  const ws = result.value?.whatif?.screen_state || '-'
  return stateChanged.value ? `${bs} → ${ws}（变化）` : `${ws}（不变）`
})

const STATE_LABEL = { pass: '通过', watch: '关注', fail: '不可行' }
const compareRows = computed(() => {
  if (!result.value) return []
  const b = baseSummary.value
  const t = tunedSummary.value
  const bs = result.value.baseline.screen_state
  const ws = result.value.whatif.screen_state
  return [
    { 指标: '可行性状态', 基线: STATE_LABEL[bs] || bs, 'What-If': STATE_LABEL[ws] || ws, 变化: stateChanged.value ? '⚠ 改变' : '不变' },
    { 指标: '设施数下界', 基线: baseLB.value, 'What-If': tunedLB.value, 变化: signed(deltaFacilities.value) },
    { 指标: '最大设施数', 基线: b.max_facilities, 'What-If': t.max_facilities, 变化: signed(Number(t.max_facilities || 0) - Number(b.max_facilities || 0)) },
    { 指标: '峰值库存(吨)', 基线: formatNumber(basePeak.value), 'What-If': formatNumber(tunedPeak.value), 变化: signed(deltaPeak.value) },
    { 指标: '容量压力', 基线: `${(Number(b.facility_pressure || 0) * 100).toFixed(0)}%`, 'What-If': `${(Number(t.facility_pressure || 0) * 100).toFixed(0)}%`, 变化: signed(deltaPressurePct.value, '%') },
  ]
})

const channelRows = computed(() =>
  safeArray(result.value?.whatif?.channel_capacity_screen).map((c) => ({
    通道: c.type,
    '年流量(吨)': formatNumber(Math.round(c.annual_flow_ton || 0)),
    '峰值库存(吨)': formatNumber(Math.round(c.peak_capacity_load_ton || 0)),
    设施下界: c.min_facilities_lower_bound ?? '-',
  })),
)

const carbonNote = computed(() => result.value?.carbon_price_note || '碳价只改变成本目标权重，不改变容量可行性筛选。')
const researchBoundary = computed(() => result.value?.research_boundary || 'solver-free 容量压力筛选：推断设施数下界与可行性，不等于精确最优选址。')

function signed(v, suffix = '') {
  const n = Number(v)
  if (n === 0) return `0${suffix}`
  return `${n > 0 ? '+' : ''}${n.toFixed(suffix === '%' ? 1 : 0)}${suffix}`
}
</script>

<style scoped>
.whatif-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 18px; margin-bottom: 14px; }
.ctrl-group { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #475569; }
.ctrl-group b { color: #0f172a; }
.ctrl-group input[type=range] { width: 100%; }
.share-controls { background: rgba(241,245,249,0.6); border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; }
.share-title { font-size: 12px; color: #64748b; margin-bottom: 8px; }
.share-row { display: grid; grid-template-columns: auto 1fr auto 1fr auto 1fr; gap: 8px; align-items: center; font-size: 12px; color: #475569; }
.whatif-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.whatif-actions .err { color: #dc2626; font-size: 12px; }
.note-box { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px; font-size: 13px; color: #92400e; line-height: 1.6; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.5; }
:deep(.state-kpi .kpi-anim-value) { font-size: 16px; }
</style>
