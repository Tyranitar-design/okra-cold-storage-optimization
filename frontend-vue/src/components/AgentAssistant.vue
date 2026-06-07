<template>
  <div class="agent-assistant">
    <el-button
      v-if="!open"
      class="agent-fab"
      type="primary"
      :icon="ChatDotRound"
      circle
      @click="open = true"
    />

    <el-card v-else class="agent-panel" shadow="always">
      <template #header>
        <div class="agent-header">
          <div>
            <div class="agent-title">秋葵决策助手</div>
            <div class="agent-subtitle">轻量 Agent · 只读查询与可控动作</div>
          </div>
          <el-button :icon="Close" text circle @click="open = false" />
        </div>
      </template>

      <el-scrollbar ref="scrollbarRef" class="agent-messages">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="agent-message"
          :class="msg.role"
        >
          <div class="agent-bubble">
            <p>{{ msg.content }}</p>

            <div v-if="msg.cards?.length" class="agent-cards">
              <div v-for="card in msg.cards" :key="card.title" class="agent-status-card">
                <div class="agent-card-top">
                  <span>{{ card.title }}</span>
                  <el-tag :type="card.level === 'ok' ? 'success' : card.level === 'warn' ? 'warning' : 'info'" size="small">
                    {{ card.value }}
                  </el-tag>
                </div>
                <div class="agent-card-detail">{{ card.detail }}</div>
              </div>
            </div>

            <div v-if="msg.evidence_refs?.length" class="agent-evidence">
              <div class="agent-evidence-title">证据引用</div>
              <div v-for="ref in msg.evidence_refs" :key="`${ref.source}-${ref.title}`" class="agent-evidence-item">
                <div>
                  <div class="agent-evidence-name">{{ ref.title }}</div>
                  <div class="agent-evidence-detail">{{ ref.value }} · {{ ref.detail }}</div>
                  <div class="agent-evidence-source">{{ ref.source }}</div>
                </div>
                <el-button v-if="ref.route" size="small" text @click="goEvidence(ref.route)">
                  查看
                </el-button>
              </div>
            </div>

            <div v-if="msg.claim_boundary" class="agent-boundary">
              {{ msg.claim_boundary }}
            </div>

            <div v-if="msg.actions?.length" class="agent-actions">
              <el-button
                v-for="action in msg.actions"
                :key="`${action.type}-${action.route || action.label}`"
                size="small"
                :type="action.type?.startsWith('confirm') ? 'warning' : 'primary'"
                plain
                @click="runAction(action)"
              >
                {{ action.label }}
              </el-button>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <div class="agent-suggestions">
        <button
          v-for="item in suggestions"
          :key="item"
          type="button"
          @click="ask(item)"
        >
          {{ item }}
        </button>
      </div>

      <div class="agent-input">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="问我：数据库状态、解释 Pareto、带我去导出页..."
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :icon="Promotion" :loading="loading" @click="send">
          发送
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Close, Promotion } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiFetch } from '../utils/format'

const emit = defineEmits(['refresh'])
const router = useRouter()

const open = ref(false)
const loading = ref(false)
const draft = ref('')
const scrollbarRef = ref(null)
const suggestions = ref(['解释 Optuna AI warm start', '检查论文能怎么写', 'AI-Benders 能不能写加速', '下一步建议'])
const messages = ref([
  {
    role: 'assistant',
    content: '您好，我是轻量版秋葵决策助手。可以帮您查询、解释、跳转和刷新；导出或运行求解前会先请您确认。',
  },
])

function scrollToBottom() {
  nextTick(() => {
    const wrap = scrollbarRef.value?.wrapRef
    if (wrap) wrap.scrollTop = wrap.scrollHeight
  })
}

function ask(text) {
  draft.value = text
  send()
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  draft.value = ''
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  loading.value = true
  try {
    const data = await apiFetch('/api/v1/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, context: { path: router.currentRoute.value.path } }),
    })
    messages.value.push({
      role: 'assistant',
      content: data.reply || '我已处理这条请求。',
      actions: data.actions || [],
      cards: data.cards || [],
      evidence_refs: data.evidence_refs || [],
      claim_boundary: data.claim_boundary || '',
      intent: data.intent || 'general_help',
      confidence: data.confidence || 'low',
    })
    suggestions.value = data.suggestions?.length ? data.suggestions : suggestions.value
  } catch (err) {
    messages.value.push({
      role: 'assistant',
      content: `助手暂时无法响应：${err.message || err}`,
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function runAction(action) {
  if (action.type === 'navigate') {
    await router.push(action.route)
    ElMessage.success(action.label)
    return
  }

  if (action.type === 'refresh') {
    emit('refresh')
    ElMessage.success('已刷新看板数据')
    return
  }

  if (action.type === 'confirm_download' || action.type === 'confirm_solve') {
    try {
      await ElMessageBox.confirm(
        action.detail || '这个动作需要您确认后再继续。',
        '请确认',
        {
          confirmButtonText: '确认前往',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
      await router.push(action.route)
      ElMessage.success(action.label)
    } catch {
      ElMessage.info('已取消')
    }
  }
}

async function goEvidence(route) {
  await router.push(route)
  ElMessage.success('已打开证据页面')
}
</script>

<style scoped>
.agent-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 40;
}

.agent-fab {
  width: 52px;
  height: 52px;
  box-shadow: 0 14px 34px rgba(31, 109, 99, 0.28);
}

.agent-panel {
  width: min(420px, calc(100vw - 32px));
  border-radius: 8px;
  overflow: hidden;
}

.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.agent-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--ink);
}

.agent-subtitle,
.agent-card-detail {
  margin-top: 3px;
  color: var(--muted);
  font-size: 12px;
}

.agent-messages {
  height: 360px;
  padding-right: 4px;
}

.agent-message {
  display: flex;
  margin-bottom: 10px;
}

.agent-message.user {
  justify-content: flex-end;
}

.agent-bubble {
  max-width: 88%;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f2f6f8;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.55;
}

.agent-message.user .agent-bubble {
  background: var(--accent);
  color: #fff;
}

.agent-bubble p {
  margin: 0;
}

.agent-cards,
.agent-evidence,
.agent-actions,
.agent-suggestions,
.agent-input {
  margin-top: 10px;
}

.agent-cards {
  display: grid;
  gap: 8px;
}

.agent-status-card {
  padding: 9px;
  border: 1px solid #e3e9ee;
  border-radius: 8px;
  background: #fff;
}

.agent-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 700;
}

.agent-evidence {
  display: grid;
  gap: 8px;
}

.agent-evidence-title {
  font-size: 12px;
  font-weight: 800;
  color: var(--accent);
}

.agent-evidence-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border: 1px solid #e3e9ee;
  border-radius: 8px;
  background: #fff;
}

.agent-evidence-name {
  font-size: 12px;
  font-weight: 800;
  color: var(--ink);
}

.agent-evidence-detail,
.agent-evidence-source,
.agent-boundary {
  margin-top: 3px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}

.agent-evidence-source {
  font-family: monospace;
}

.agent-boundary {
  padding: 8px;
  border-left: 3px solid #f59e0b;
  background: #fff7ed;
  border-radius: 6px;
}

.agent-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-suggestions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-suggestions button {
  border: 1px solid #d8e0e8;
  border-radius: 999px;
  background: #fff;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
  padding: 5px 10px;
}

.agent-suggestions button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.agent-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
}

@media (max-width: 640px) {
  .agent-assistant {
    right: 16px;
    bottom: 16px;
  }

  .agent-messages {
    height: 300px;
  }
}
</style>
