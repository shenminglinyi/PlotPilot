import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Workbench from '../views/Workbench.vue'
import Chapter from '../views/Chapter.vue'
import Cast from '../views/Cast.vue'
import CharacterGraph from '../views/CharacterGraph.vue'
import LocationGraph from '../views/LocationGraph.vue'
import CharacterSchedulerSimulator from '../components/debug/CharacterSchedulerSimulator.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Home', component: Home },
    { path: '/book/:slug/workbench', name: 'Workbench', component: Workbench },
    { path: '/book/:slug/cast', name: 'Cast', component: Cast },
    { path: '/book/:slug/chapter/:id', name: 'Chapter', component: Chapter },
    { path: '/book/:slug/characters', name: 'CharacterGraph', component: CharacterGraph },
    { path: '/book/:slug/location-graph', name: 'LocationGraph', component: LocationGraph },
    { path: '/debug/scheduler', name: 'CharacterSchedulerSimulator', component: CharacterSchedulerSimulator },
  ],
})

export default router
