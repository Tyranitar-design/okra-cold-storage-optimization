/**
 * 秋葵冷库优化小程序 — 真实实验回落数据
 * 当后端 API 不可用时使用，数据来自运行产物
 */
export const mockData = {
  /* ── 首页 KPI ── */
  kpi: {
    optimalCost: '4,433,112',
    speedup: '7.18×',
    facilityCount: '6',
    mipGap: '0.91%',
    solveTime: '24.44s',
    model: 'v3.0 容量链 MIP',
    region: '湖南 J 县 · 39 节点',
    distanceMatrix: 'OSM 真实路网（10,140 边 / 8,953 km）',
    solver: 'Gurobi + XGBoost AI warm start',
    status: 'solved to tolerance (1% MIPGap)',
  },

  /* ── 成本分解 ── */
  costBreakdown: [
    { label: '固定建设成本', value: 3330000, pct: 75.0, color: '#0F766E' },
    { label: '年度运营成本', value: 734000,  pct: 16.5, color: '#14B8A6' },
    { label: '运输成本',     value: 46900,   pct: 1.1,  color: '#F59E0B' },
    { label: '损耗成本',     value: 94100,   pct: 2.1,  color: '#EF4444' },
    { label: '碳排放成本',   value: 346,     pct: 0.1,  color: '#8B5CF6' },
  ],

  /* ── 设施列表 ── */
  facilities: [
    { id: 'f1', name: 'C1 县级中心', type: '冷藏库', capacity: 30, lat: 29.337, lng: 111.725, cost: 12.0, status: '建设中', loadPct: 82 },
    { id: 'f2', name: 'T4 乡镇',     type: '冷藏库', capacity: 30, lat: 29.310, lng: 111.690, cost: 12.0, status: '运营中', loadPct: 76 },
    { id: 'f3', name: 'T7 乡镇',     type: '预冷库', capacity: 20, lat: 29.250, lng: 111.650, cost: 8.0,  status: '运营中', loadPct: 91 },
    { id: 'f4', name: 'T8 乡镇',     type: '气调库', capacity: 20, lat: 29.220, lng: 111.720, cost: 12.0, status: '运营中', loadPct: 68 },
    { id: 'f5', name: 'V12 村',      type: '预冷库', capacity: 10, lat: 29.195, lng: 111.755, cost: 4.0,  status: '运营中', loadPct: 74 },
    { id: 'f6', name: 'V19 村',      type: '冷冻库', capacity: 10, lat: 29.265, lng: 111.580, cost: 6.0,  status: '规划中', loadPct: 45 },
  ],

  /* ── 选址推荐 fallback ── */
  recommendFallback: {
    totalCost: '4,433,112',
    speedup: '7.18×',
    sites: [
      { name: 'C1 县级中心', type: '冷藏库', capacity: 30, cost: 12.0, reason: '区域中心，交通便利，覆盖 8 村' },
      { name: 'T4 乡镇',     type: '冷藏库', capacity: 30, cost: 12.0, reason: '产量密集区，辐射西片 6 村' },
      { name: 'T7 乡镇',     type: '预冷库', capacity: 20, cost: 8.0,  reason: '预冷时效关键节点，覆盖南片 5 村' },
      { name: 'T8 乡镇',     type: '气调库', capacity: 20, cost: 12.0, reason: '延长储藏周期，调节市场供给' },
      { name: 'V12 村',      type: '预冷库', capacity: 10, cost: 4.0,  reason: 'AI 推荐 · 高产区就近预冷' },
      { name: 'V19 村',      type: '冷冻库', capacity: 10, cost: 6.0,  reason: 'AI 推荐 · 冷冻加工需求节点' },
    ],
  },

  /* ── 气象预警 ── */
  weather: {
    current: { temp: 28, desc: '多云', humidity: 53, wind: '3 级', location: '湖南 J 县', time: '2026-06-03 14:00' },
    forecast: [
      { date: '6/4', icon: '☀️', temp: 31, desc: '晴' },
      { date: '6/5', icon: '⛅',  temp: 29, desc: '多云' },
      { date: '6/6', icon: '🌧️', temp: 25, desc: '小雨' },
      { date: '6/7', icon: '☁️', temp: 26, desc: '阴' },
    ],
    advice: [
      { icon: '✅', title: '预冷作业正常', desc: '当前温度 28°C 适合采后预冷，建议采收后 2h 内完成预冷入库' },
      { icon: '✅', title: '冷藏库运行平稳', desc: '库温 7-10°C，能耗 73.4 万/年，建议每 4h 巡检' },
      { icon: '⚠️', title: '6/6 有小雨', desc: '预计降雨，建议提前采收并增加预冷产能储备' },
      { icon: 'ℹ️', title: '气调库 O₂ 监测', desc: '当前 O₂ 浓度 3.2%，CO₂ 4.5%，运行正常' },
    ],
  },

  /* ── 我的冷库 ── */
  storage: {
    name: 'T4 乡镇冷藏库',
    type: '冷藏库',
    capacity: { used: 22.8, total: 30, unit: '吨' },
    temp: { current: 8.2, target: '7-10', unit: '°C' },
    energy: { monthly: 12500, unit: 'kWh', cost: 10000, costUnit: '元/月' },
    inventory: [
      { batch: 'B20260601', product: '秋葵', qty: 8.5, date: '2026-06-01', loss: 1.2, eta: '6/10' },
      { batch: 'B20260602', product: '秋葵', qty: 6.3, date: '2026-06-02', loss: 0.8, eta: '6/12' },
      { batch: 'B20260603', product: '秋葵', qty: 8.0, date: '2026-06-03', loss: 0.5, eta: '6/15' },
    ],
    history: [
      { date: '6/1', temp: 8.5, fill: 65 },
      { date: '6/2', temp: 8.0, fill: 73 },
      { date: '6/3', temp: 8.2, fill: 76 },
    ],
  },

  /* ── 物流路线 ── */
  logistics: {
    routes: [
      { from: 'C1 县级中心', to: 'T4 乡镇冷藏库', dist: 12.5, eta: 25, status: '已送达', time: '09:30' },
      { from: 'T7 乡镇预冷库', to: 'C1 县级中心', dist: 18.2, eta: 35, status: '运输中', time: '10:15' },
      { from: 'V12 村预冷库', to: 'T4 乡镇冷藏库', dist: 8.0, eta: 16, status: '待发车', time: '14:00' },
    ],
  },
}

export default mockData
