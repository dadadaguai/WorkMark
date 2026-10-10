import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
  },
  {
    path: '/document/:id',
    name: 'editor',
    component: () => import('@/views/EditorView.vue'),
    props: true,
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
