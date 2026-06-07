<template>
  <div>
    <!-- 搜索栏 -->
    <div class="search-bar">
      <input v-model="search" type="text" placeholder="搜索路线方案..." @input="debouncedLoad" />
      <select v-model="statusFilter" @change="loadData(1)">
        <option value="">全部状态</option>
        <option value="draft">draft</option>
        <option value="active">active</option>
        <option value="archived">archived</option>
      </select>
      <button class="action-btn primary" @click="openCreateModal">+ 创建路线方案</button>
    </div>

    <!-- 路线列表 -->
    <div class="panel-card" v-if="loading" style="text-align:center;padding:40px">加载中...</div>
    <template v-else>
      <div v-for="plan in items" :key="plan.id" class="panel-card section-gap" style="cursor:pointer" @click="toggleExpand(plan.id)">
        <div class="panel-header" style="margin-bottom:0">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:10px">
              <h2>{{ plan.name }}</h2>
              <span class="status-badge" :class="plan.status || 'draft'">{{ plan.status || 'draft' }}</span>
            </div>
            <p v-if="plan.description" class="panel-subtitle">{{ plan.description }}</p>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
            <span style="font-size:13px;color:var(--muted)">{{ plan.total_distance_km || plan.distance_total ? Number(plan.total_distance_km ?? plan.distance_total).toFixed(1) + ' km' : '' }}</span>
            <span style="font-size:12px;color:var(--muted)">{{ formatDate(plan.created_at) }}</span>
          </div>
        </div>

        <!-- 操作栏 -->
        <div style="display:flex;gap:8px;padding:8px 0 2px;border-top:1px solid var(--line);margin-top:8px" @click.stop>
          <select v-model="plan.status" class="search-bar" style="margin:0;padding:4px 8px;font-size:12px;border:1px solid var(--line);border-radius:6px" @change="updatePlanStatus(plan)">
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </select>
          <button class="action-btn" @click="openAddSiteModal(plan)">+ 添加站点</button>
          <button class="action-btn danger" @click="confirmDeletePlan(plan)">删除</button>
        </div>

        <!-- 展开详情：站点列表 -->
        <div class="detail-expand" :class="{ open: expandedId === plan.id }" @click.stop>
          <div class="detail-inner">
            <div v-if="!plan.stops || plan.stops.length === 0" class="empty-state" style="padding:16px 0">
              <span style="font-size:13px">暂无站点，请点击"添加站点"</span>
            </div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>节点名称</th>
                    <th>动作</th>
                    <th>到达时间</th>
                    <th>离开时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(stop, idx) in plan.stops" :key="stop.id || idx">
                    <td>{{ idx + 1 }}</td>
                    <td>{{ stop.node_name || stop.node_id || '-' }}</td>
                    <td>{{ stop.action || '-' }}</td>
                    <td>{{ stop.planned_arrival || stop.arrival_time || '-' }}</td>
                    <td>{{ stop.planned_departure || stop.departure_time || '-' }}</td>
                    <td>
                      <button class="action-btn danger" @click="removeStop(plan, stop)">移除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div v-if="items.length === 0 && !loading" class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div>暂无路线方案</div>
      </div>
    </template>

    <!-- 分页 -->
    <div class="pagination" v-if="totalPages > 1">
      <button class="page-btn" :disabled="page <= 1" @click="loadData(page - 1)">‹</button>
      <template v-for="p in visiblePages" :key="p">
        <span v-if="p === '...'" class="page-info">...</span>
        <button v-else class="page-btn" :class="{ active: p === page }" @click="loadData(p)">{{ p }}</button>
      </template>
      <button class="page-btn" :disabled="page >= totalPages" @click="loadData(page + 1)">›</button>
      <span class="page-info">共 {{ total }} 条</span>
    </div>

    <!-- 创建路线 Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>创建路线方案</h2>
          <button class="modal-close" @click="showCreateModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label>名称</label>
            <input v-model="createForm.name" type="text" placeholder="方案名称" />
          </div>
          <div class="form-field">
            <label>描述</label>
            <textarea v-model="createForm.description" placeholder="方案描述（选填）" style="width:100%;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px;resize:vertical;min-height:60px"></textarea>
          </div>
          <div class="form-field">
            <label>车辆类型</label>
            <select v-model="createForm.vehicle_type">
              <option value="truck">卡车 (truck)</option>
              <option value="van">厢货 (van)</option>
              <option value="reefer">冷藏车 (reefer)</option>
            </select>
          </div>
        </div>
        <div class="modal-actions">
          <button class="action-btn" @click="showCreateModal = false">取消</button>
          <button class="action-btn primary" :disabled="saving" @click="createPlan">
            {{ saving ? '创建中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 添加站点 Modal -->
    <div v-if="showAddSiteModal" class="modal-overlay" @click.self="showAddSiteModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>添加站点</h2>
          <button class="modal-close" @click="showAddSiteModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label>目标方案</label>
            <input type="text" :value="addSiteTarget?.name" disabled style="padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#f5f7f9;width:100%" />
          </div>
          <div class="form-field">
            <label>节点 ID</label>
            <input v-model.trim="addSiteForm.node_id" type="text" placeholder="例如 C1 / T4 / V21" />
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="form-field">
              <label>动作</label>
              <select v-model="addSiteForm.action">
                <option value="pickup">取货 (pickup)</option>
                <option value="delivery">送货 (delivery)</option>
                <option value="transit">中转 (transit)</option>
              </select>
            </div>
            <div class="form-field">
              <label>顺序</label>
              <input v-model.number="addSiteForm.stop_order" type="number" step="1" placeholder="顺序号" />
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="form-field">
              <label>到达时间</label>
              <input v-model="addSiteForm.planned_arrival" type="text" placeholder="2026-01-01T08:00" />
            </div>
            <div class="form-field">
              <label>离开时间</label>
              <input v-model="addSiteForm.planned_departure" type="text" placeholder="2026-01-01T08:30" />
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="action-btn" @click="showAddSiteModal = false">取消</button>
          <button class="action-btn primary" :disabled="saving" @click="doAddSite">
            {{ saving ? '添加中...' : '添加' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认 -->
    <div v-if="deleteTarget" class="confirm-overlay" @click.self="deleteTarget = null">
      <div class="confirm-box">
        <p>确定要删除路线方案 <strong>{{ deleteTarget.name }}</strong> 吗？此操作不可撤销。</p>
        <div class="confirm-actions">
          <button class="action-btn" @click="deleteTarget = null">取消</button>
          <button class="action-btn danger" @click="doDeletePlan">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { apiFetch } from '../utils/format'

const items = ref([])
const loading = ref(false)
const saving = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 10
const search = ref('')
const statusFilter = ref('')
const expandedId = ref(null)
const deleteTarget = ref(null)

// Create modal
const showCreateModal = ref(false)
const createForm = ref({ name: '', description: '', vehicle_type: 'truck' })

// Add site modal
const showAddSiteModal = ref(false)
const addSiteTarget = ref(null)
const addSiteForm = ref({ node_id: '', action: 'pickup', stop_order: 1, planned_arrival: '', planned_departure: '' })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const visiblePages = computed(() => {
  const tp = totalPages.value
  const cp = page.value
  if (tp <= 7) return Array.from({ length: tp }, (_, i) => i + 1)
  const pages = []
  pages.push(1)
  if (cp > 3) pages.push('...')
  const start = Math.max(2, cp - 1)
  const end = Math.min(tp - 1, cp + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (cp < tp - 2) pages.push('...')
  pages.push(tp)
  return pages
})

let debounceTimer = null
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadData(1), 300)
}

onUnmounted(() => clearTimeout(debounceTimer))

async function loadData(p = 1) {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(p),
      page_size: String(pageSize),
    })
    if (search.value) params.set('search', search.value)
    if (statusFilter.value) params.set('status', statusFilter.value)
    const data = await apiFetch(`/api/v1/routes/plans?${params.toString()}`)
    items.value = data.items || data.data || data || []
    total.value = data.total ?? items.value.length
    page.value = p
  } catch (err) {
    console.error('加载路线方案失败:', err)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function formatDate(v) {
  if (!v) return '-'
  try {
    return new Date(v).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return String(v).slice(0, 16)
  }
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

// Create plan
function openCreateModal() {
  createForm.value = { name: '', description: '', vehicle_type: 'truck' }
  showCreateModal.value = true
}

async function createPlan() {
  if (!createForm.value.name) return
  saving.value = true
  try {
    await apiFetch('/api/v1/routes/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createForm.value),
    })
    showCreateModal.value = false
    await loadData(page.value)
  } catch (err) {
    alert('创建失败: ' + err.message)
  } finally {
    saving.value = false
  }
}

// Update plan status
async function updatePlanStatus(plan) {
  try {
    await apiFetch(`/api/v1/routes/plans/${plan.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: plan.status }),
    })
  } catch (err) {
    alert('状态更新失败: ' + err.message)
  }
}

// Delete plan
function confirmDeletePlan(plan) {
  deleteTarget.value = plan
}

async function doDeletePlan() {
  if (!deleteTarget.value) return
  try {
    await apiFetch(`/api/v1/routes/plans/${deleteTarget.value.id}`, { method: 'DELETE' })
    deleteTarget.value = null
    await loadData(page.value)
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}

// Add site
function openAddSiteModal(plan) {
  addSiteTarget.value = plan
  addSiteForm.value = {
    node_id: '',
    action: 'pickup',
    stop_order: (plan.stops?.length || 0) + 1,
    planned_arrival: '',
    planned_departure: '',
  }
  showAddSiteModal.value = true
}

async function doAddSite() {
  if (!addSiteForm.value.node_id || !addSiteTarget.value) return
  saving.value = true
  try {
    const payload = {
      node_id: addSiteForm.value.node_id,
      action: addSiteForm.value.action,
      stop_order: Number(addSiteForm.value.stop_order),
      planned_arrival: addSiteForm.value.planned_arrival || null,
      planned_departure: addSiteForm.value.planned_departure || null,
      notes: '',
    }
    await apiFetch(`/api/v1/routes/plans/${addSiteTarget.value.id}/stops`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    showAddSiteModal.value = false
    await loadData(page.value)
  } catch (err) {
    alert('添加站点失败: ' + err.message)
  } finally {
    saving.value = false
  }
}

// Remove stop
async function removeStop(plan, stop) {
  try {
    await apiFetch(`/api/v1/routes/plans/${plan.id}/stops/${stop.id}`, { method: 'DELETE' })
    await loadData(page.value)
  } catch (err) {
    alert('移除失败: ' + err.message)
  }
}

onMounted(() => loadData(1))
</script>
