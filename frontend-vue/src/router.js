import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from './views/OverviewView.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('./views/LoginView.vue'),
    meta: { public: true },
  },
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'overview', component: OverviewView },
  { path: '/map', name: 'map', component: () => import('./views/MapView.vue') },
  { path: '/nodes', name: 'nodes', component: () => import('./views/NodesManageView.vue') },
  { path: '/routes', name: 'routes', component: () => import('./views/RoutesManageView.vue') },
  { path: '/weather', name: 'weather', component: () => import('./views/WeatherView.vue') },
  { path: '/solve', name: 'solve', component: () => import('./views/SolveView.vue') },
  { path: '/aisolve', name: 'aisolve', component: () => import('./views/AiSolveView.vue') },
  { path: '/pareto', name: 'pareto', component: () => import('./views/ParetoView.vue') },
  { path: '/analysis', name: 'analysis', component: () => import('./views/AnalysisView.vue') },
  { path: '/whatif', name: 'whatif', component: () => import('./views/WhatIfView.vue') },
  { path: '/model', name: 'model', component: () => import('./views/ModelView.vue') },
  { path: '/ai', name: 'ai', component: () => import('./views/AiFusionView.vue') },
  { path: '/evidence', name: 'evidence', component: () => import('./views/DataEvidenceView.vue') },
  { path: '/export', name: 'export', component: () => import('./views/ExportView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

export default router
