<template>
  <div>
    <!-- 搜索栏 -->
    <div class="search-bar">
      <input v-model="search" type="text" placeholder="搜索节点名称..." @input="debouncedLoad" />
      <select v-model="typeFilter" @change="loadData(1)">
        <option value="">全部层级</option>
        <option value="县级">县级</option>
        <option value="乡镇级">乡镇级</option>
        <option value="村级">村级</option>
      </select>
      <button class="action-btn primary" @click="openCreateModal">+ 新增节点</button>
    </div>

    <!-- 数据表格 -->
    <div class="panel-card">
      <div v-if="loading" class="empty-state">加载中...</div>
      <div v-else-if="items.length === 0" class="empty-state">
        <div class="empty-state-icon">📦</div>
        <div>暂无节点数据</div>
      </div>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>名称</th>
              <th>经度</th>
              <th>纬度</th>
              <th>类型</th>
              <th>容量</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="node in items" :key="node.node_id || node.id">
              <td>{{ node.node_id || node.id }}</td>
              <td><strong>{{ node.name }}</strong></td>
              <td>{{ formatCoord(node.lon ?? node.longitude) }}</td>
              <td>{{ formatCoord(node.lat ?? node.latitude) }}</td>
              <td><span class="status-badge" :class="typeBadgeClass(node.level_name || node.type)">{{ node.level_name || node.type }}</span></td>
              <td>{{ formatTon(node.okra_production_ton ?? node.capacity) }}</td>
              <td><span class="status-badge" :class="node.is_candidate ? 'active' : 'archived'">{{ node.is_candidate ? '候选' : '普通' }}</span></td>
              <td>
                <div class="action-group">
                  <button class="action-btn" @click="openEditModal(node)">编辑</button>
                  <button class="action-btn danger" @click="confirmDelete(node)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

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

    <!-- 新增 / 编辑 Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <h2>{{ editingNode ? '编辑节点' : '新增节点' }}</h2>
          <button class="modal-close" @click="closeModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label>名称</label>
            <input v-model="form.name" type="text" placeholder="节点名称" />
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="form-field">
              <label>经度</label>
              <input v-model.number="form.lon" type="number" step="0.0001" />
            </div>
            <div class="form-field">
              <label>纬度</label>
              <input v-model.number="form.lat" type="number" step="0.0001" />
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="form-field">
              <label>层级</label>
              <select v-model.number="form.level">
                <option :value="3">县级</option>
                <option :value="2">乡镇级</option>
                <option :value="1">村级</option>
              </select>
            </div>
            <div class="form-field">
              <label>秋葵产量（吨）</label>
              <input v-model.number="form.okra_production_ton" type="number" step="0.1" />
            </div>
          </div>
          <div class="form-field">
            <label>
              <input type="checkbox" v-model="form.is_candidate" /> 作为候选点
            </label>
          </div>
        </div>
        <div class="modal-actions">
          <button class="action-btn" @click="closeModal">取消</button>
          <button class="action-btn primary" :disabled="saving" @click="saveNode">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认 -->
    <div v-if="deleteTarget" class="confirm-overlay" @click.self="deleteTarget = null">
      <div class="confirm-box">
        <p>确定要删除节点 <strong>{{ deleteTarget.name }}</strong> 吗？此操作不可撤销。</p>
        <div class="confirm-actions">
          <button class="action-btn" @click="deleteTarget = null">取消</button>
          <button class="action-btn danger" @click="doDelete">确认删除</button>
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
const pageSize = 20
const search = ref('')
const typeFilter = ref('')
const showModal = ref(false)
const editingNode = ref(null)
const deleteTarget = ref(null)

const form = ref({
  name: '',
  level: 1,
  lat: null,
  lon: null,
  okra_production_ton: 0,
  is_candidate: true,
})

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
    if (typeFilter.value) params.set('type', typeFilter.value)
    const data = await apiFetch(`/api/v1/nodes?${params.toString()}`)
    items.value = data.items || data.data || data || []
    total.value = data.total ?? items.value.length
    page.value = p
  } catch (err) {
    console.error('加载节点失败:', err)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function formatCoord(v) {
  if (v == null) return '-'
  return Number(v).toFixed(4)
}

function formatTon(v) {
  if (v == null) return '-'
  return Number(v).toFixed(1)
}

function typeBadgeClass(type) {
  const map = {
    县级: 'active',
    乡镇级: 'draft',
    村级: 'ok',
  }
  return map[type] || ''
}

function openCreateModal() {
  editingNode.value = null
  form.value = { name: '', level: 1, lat: null, lon: null, okra_production_ton: 0, is_candidate: true }
  showModal.value = true
}

function openEditModal(node) {
  editingNode.value = node
  form.value = {
    name: node.name || '',
    level: Number(node.level ?? 1),
    lat: Number(node.lat ?? node.latitude ?? 0),
    lon: Number(node.lon ?? node.longitude ?? 0),
    okra_production_ton: Number(node.okra_production_ton ?? node.capacity ?? 0),
    is_candidate: Boolean(node.is_candidate ?? node.active ?? true),
  }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingNode.value = null
}

async function saveNode() {
  if (!form.value.name) return
  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      level: Number(form.value.level),
      lat: Number(form.value.lat),
      lon: Number(form.value.lon),
      okra_production_ton: Number(form.value.okra_production_ton || 0),
      is_candidate: Boolean(form.value.is_candidate),
    }
    const url = editingNode.value
      ? `/api/v1/nodes/${editingNode.value.node_id || editingNode.value.id}`
      : '/api/v1/nodes'
    const method = editingNode.value ? 'PUT' : 'POST'
    await apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    closeModal()
    await loadData(page.value)
  } catch (err) {
    alert('保存失败: ' + err.message)
  } finally {
    saving.value = false
  }
}

function confirmDelete(node) {
  deleteTarget.value = node
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await apiFetch(`/api/v1/nodes/${deleteTarget.value.node_id || deleteTarget.value.id}`, { method: 'DELETE' })
    deleteTarget.value = null
    await loadData(page.value)
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}

onMounted(() => loadData(1))
</script>
