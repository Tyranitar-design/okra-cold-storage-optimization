import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 拆分 chunk，避免单文件过大（原来 ~1.5MB 全打进一个 bundle）
    rollupOptions: {
      output: {
        manualChunks: {
          // ECharts 核心 + 渲染器（最重，单独一个 chunk）
          'echarts-core': ['echarts/core', 'echarts/renderers'],
          // ECharts 图表组件（按需引入，但仍独立 chunk 方便缓存）
          'echarts-charts': [
            'echarts/charts',
            'echarts/components',
          ],
          // Vue 运行时
          'vue-vendor': ['vue'],
          // Element Plus UI 库与图标
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          // KaTeX（公式渲染，只在 ModelView 用）
          'katex': ['katex'],
        },
      },
    },
    // chunk 超过 500KB 时警告（ECharts 按需后单 chunk 应低于此值）
    chunkSizeWarningLimit: 500,
  },
})
