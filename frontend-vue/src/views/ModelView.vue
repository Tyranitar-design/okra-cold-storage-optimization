<template>
  <div>
    <section class="content-grid single">
      <PanelCard :title="model.title || '数学模型'" subtitle="双层多目标混合整数规划 (Bi-level Multi-objective MIP)" badge="Formulation" badge-class="neutral">
        <div class="model-grid">
          <div class="model-col">
            <h4>集合 Sets</h4>
            <ul class="def-list">
              <li v-for="s in model.sets" :key="s.symbol"><MathBlock :expr="s.symbol" :display="false" /> — {{ s.desc }}</li>
            </ul>
            <h4>参数 Parameters</h4>
            <ul class="def-list">
              <li v-for="p in model.parameters" :key="p.symbol"><MathBlock :expr="p.symbol" :display="false" /> — {{ p.desc }}</li>
            </ul>
            <h4>决策变量 Variables</h4>
            <ul class="def-list">
              <li v-for="v in model.variables" :key="v.symbol"><MathBlock :expr="v.symbol" :display="false" /> — {{ v.desc }}</li>
            </ul>
          </div>
          <div class="model-col">
            <h4>目标函数 Objectives（多目标）</h4>
            <div v-for="o in model.objectives" :key="o.key" class="formula-card">
              <MathBlock :expr="o.latex" />
              <div class="formula-desc">{{ o.desc }}</div>
            </div>
          </div>
        </div>
      </PanelCard>
    </section>

    <section class="content-grid stagger">
      <PanelCard title="约束条件 Constraints" subtitle="分配 / 容量 / 冷链温度 / 设施数">
        <div v-for="(c, i) in model.constraints" :key="i" class="formula-card sm">
          <MathBlock :expr="c.latex" />
          <div class="formula-desc">{{ c.desc }}</div>
        </div>
      </PanelCard>
      <PanelCard title="求解方法 Solution Methods" subtitle="精确求解 + AI 增强 + 启发式对比" badge="Methods" badge-class="ok">
        <div v-for="(m, i) in model.solution_methods" :key="i" class="method-row" :style="{ animationDelay: (i * 90) + 'ms' }">
          <div class="method-name">{{ m.name }}</div>
          <div class="method-desc">{{ m.desc }}</div>
        </div>
        <p class="boundary-note">{{ model.claim_boundary }}</p>
      </PanelCard>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PanelCard from '../components/PanelCard.vue'
import MathBlock from '../components/MathBlock.vue'
import { useBootstrap } from '../utils/format'

const b = useBootstrap()
const model = computed(() => (b.value || {}).model_formulation || { sets: [], parameters: [], variables: [], objectives: [], constraints: [], solution_methods: [] })
</script>

<style scoped>
.model-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
.model-col h4 { margin: 14px 0 8px; color: #1e3a8a; font-size: 14px; }
.def-list { list-style: none; padding: 0; margin: 0; }
.def-list li { padding: 4px 0; font-size: 13px; color: #475569; border-bottom: 1px dashed rgba(148,163,184,0.25); display: flex; gap: 8px; align-items: baseline; }
.formula-card { background: rgba(241,245,249,0.7); border-left: 3px solid #6366f1; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; overflow-x: auto; }
.formula-card.sm { border-left-color: #38bdf8; }
.formula-desc { font-size: 12px; color: #64748b; margin-top: 6px; }
.method-row { padding: 10px 12px; border-radius: 8px; background: rgba(241,245,249,0.6); margin-bottom: 8px; animation: slideIn 0.5s ease both; }
.method-name { font-weight: 600; color: #0f172a; font-size: 13px; }
.method-desc { font-size: 12px; color: #64748b; margin-top: 3px; }
.boundary-note { font-size: 11px; color: #94a3b8; margin-top: 12px; line-height: 1.5; }
@keyframes slideIn { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }
@media (max-width: 1100px) { .model-grid { grid-template-columns: 1fr; } }
</style>
