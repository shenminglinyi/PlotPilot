<template>
  <div class="character-graph-page">
    <n-page-header @back="handleBack" title="人物关系图">
      <template #extra>
        <n-space>
          <n-button @click="handleRefresh" :loading="loading">
            <template #icon>
              <n-icon><RefreshOutline /></n-icon>
            </template>
            刷新
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <div class="graph-container">
      <CharacterRelationGraph
        v-if="novelId"
        :slug="novelId"
        @loading="loading = $event"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NPageHeader, NButton, NSpace, NIcon } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import CharacterRelationGraph from '../components/graphs/CharacterRelationGraph.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)

const novelId = computed(() => route.params.slug as string)

const handleBack = () => {
  router.push(`/book/${novelId.value}/workbench`)
}

const handleRefresh = () => {
  window.location.reload()
}
</script>

<style scoped>
.character-graph-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--app-page-bg);
}

.graph-container {
  flex: 1;
  overflow: hidden;
  padding: 16px;
}
</style>
