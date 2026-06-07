<template>
  <div>
    <section class="content-grid stagger">
      <PanelCard title="数据库连通" subtitle="PostgreSQL 真实探测状态" badge="DB" :badge-class="dbOk ? 'ok' : 'warn'">
        <StatusList :items="databaseItems" />
      </PanelCard>
      <PanelCard title="数据库连通诊断" subtitle="安全连接信息（不暴露密码/URL）">
        <SectionTable :headers="['id', 'state', 'boundary']" :rows="dbDiagRows" />
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="数据证据链" subtitle="baseline / algorithm / paper pack / v3">
        <SectionTable :headers="['name', 'state', 'detail']" :rows="evidenceRows" />
      </PanelCard>
      <PanelCard title="方法烟雾总表" subtitle="主线：v3.0 + direct MIP；子线：Benders cut ranking / SPO">
        <SectionTable :headers="['method', 'status', 'note']" :rows="methodRows" />
      </PanelCard>
    </section>

    <section class="content-grid single">
      <PanelCard title="物流系统接口契约" subtitle="与物流路径规划系统的 API 级对接" badge="Integration" badge-class="neutral">
        <SectionTable :headers="['path', 'purpose', 'status']" :rows="integrationRows" />
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import StatusList from '../components/StatusList.vue'
import SectionTable from '../components/SectionTable.vue'
import { formatNumber, safeArray, useBootstrap } from '../utils/format'

const b = useBootstrap()
const dbOk = computed(() => Boolean((b.value || {}).db_probe?.query_ready))

const databaseItems = computed(() => {
  const d = b.value?.db_probe || {}
  return [
    { label: 'enabled', value: d.enabled ? 'yes' : 'no', className: d.enabled ? 'ok' : 'warn' },
    { label: 'probe_ok', value: d.probe_ok ? 'yes' : 'no', className: d.probe_ok ? 'ok' : 'warn' },
    { label: 'query_ready', value: d.query_ready ? 'yes' : 'no', className: d.query_ready ? 'ok' : 'warn' },
    { label: 'current_database', value: d.probe_current_database || '-' },
    { label: 'current_user', value: d.probe_current_user || '-' },
  ]
})

const dbDiagRows = computed(() =>
  safeArray(b.value?.database_connectivity_report?.checks).map((it) => ({
    id: it.id || '-', state: it.state || '-', boundary: it.boundary || '-',
  })),
)

const evidenceRows = computed(() => {
  const ev = b.value?.algorithm_evidence_report || {}
  const paper = b.value?.paper_evidence_pack?.summary || {}
  return [
    { name: 'baseline_v2_1', state: b.value?.baseline_v2_1_report?.exists ? 'ready' : 'missing', detail: `cost=${formatNumber(b.value?.baseline_v2_1_report?.summary?.total_cost || 0)}` },
    { name: 'algorithm_evidence', state: 'ready', detail: `cuts=${formatNumber(ev.counts?.ai_benders_cut_scores || 0)}` },
    { name: 'paper_evidence_pack', state: paper.paper_ready ? 'ready' : 'pending', detail: `layers=${formatNumber(paper.paper_layer_count || 0)}` },
    { name: 'exact_vs_heuristic', state: b.value?.pareto_front?.available ? 'ready' : 'pending', detail: `scenarios=${formatNumber(safeArray(b.value?.pareto_front?.scenarios).length)}` },
    { name: 'benders_cutmgmt', state: b.value?.benders_convergence?.available ? 'ready' : 'pending', detail: `traces=${formatNumber(safeArray(b.value?.benders_convergence?.traces).length)}` },
  ]
})

const methodRows = computed(() =>
  safeArray(b.value?.method_smoke?.items).map((it) => ({
    method: it.method || '-', status: it.status || '-', note: it.note || '-',
  })),
)

const integrationRows = computed(() =>
  safeArray(b.value?.integration?.interfaces).map((it) => ({
    path: it.path || '-', purpose: it.purpose || '-', status: it.status || '-',
  })),
)
</script>
