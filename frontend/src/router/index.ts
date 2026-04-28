import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Home', component: () => import('../views/Home.vue') },
    { path: '/book/:slug/workbench', name: 'Workbench', component: () => import('../views/Workbench.vue') },
    { path: '/book/:slug/cast', name: 'Cast', component: () => import('../views/Cast.vue') },
    { path: '/book/:slug/chapter/:id', name: 'Chapter', component: () => import('../views/Chapter.vue') },
    { path: '/book/:slug/characters', name: 'CharacterGraph', component: () => import('../views/CharacterGraph.vue') },
    { path: '/book/:slug/location-graph', name: 'LocationGraph', component: () => import('../views/LocationGraph.vue') },
    { path: '/debug/scheduler', name: 'CharacterSchedulerSimulator', component: () => import('../components/debug/CharacterSchedulerSimulator.vue') },
  ],
})

export default router
