<template>
  <div>
    <section class="content-grid single">
      <PanelCard title="地图选址视图" subtitle="高德底图 · 候选冷库与需求点（按产量）">
        <AmapView />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="地图就绪度" subtitle="点位、候选点、布局与数据源边界" badge="Map" badge-class="ok">
        <StatusList :items="mapReadinessItems" />
      </PanelCard>
      <PanelCard title="地图服务商状态" subtitle="高德 Key 配置与安全边界" badge="Provider" badge-class="neutral">
        <StatusList :items="mapProviderItems" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import AmapView from '../components/AmapView.vue'
import { formatNumber, useBootstrap } from '../utils/format'

const b = useBootstrap()

const mapReadinessItems = computed(() => {
  const s = b.value?.map_readiness_report?.summary || {}
  return [
    { label: 'map_feature_count', value: formatNumber(s.map_feature_count || 0) },
    { label: 'candidate_feature_count', value: formatNumber(s.candidate_feature_count || 0) },
    { label: 'layout_storage_count', value: formatNumber(s.layout_storage_count || 0) },
    { label: 'database_query_ready', value: s.database_query_ready ? 'yes' : 'no', className: s.database_query_ready ? 'ok' : 'warn' },
    { label: 'browser_provider_ready', value: s.browser_provider_ready ? 'yes' : 'no', className: s.browser_provider_ready ? 'ok' : 'warn' },
    { label: 'source_backend', value: s.source_backend || '-', className: s.source_backend === 'database' ? 'ok' : '' },
  ]
})

const mapProviderItems = computed(() => {
  const s = b.value?.map_provider_status?.summary || {}
  return [
    { label: 'provider', value: s.provider || 'file', className: s.provider === 'amap' ? 'ok' : '' },
    { label: 'public_key_configured', value: s.public_key_configured ? 'yes' : 'no', className: s.public_key_configured ? 'ok' : 'warn' },
    { label: 'browser_provider_ready', value: s.browser_provider_ready ? 'yes' : 'no', className: s.browser_provider_ready ? 'ok' : 'warn' },
    { label: 'file_fallback_ready', value: s.file_fallback_ready ? 'yes' : 'no' },
  ]
})
</script>
