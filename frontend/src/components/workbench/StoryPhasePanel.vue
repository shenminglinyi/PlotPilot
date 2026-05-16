<template>
  <div class="story-phase-panel">
    <div class="phase-header">
      <n-text strong style="font-size: 14px">故事阶段</n-text>
      <n-button size="small" :loading="loading" @click="load">刷新</n-button>
    </div>

    <n-spin :show="loading">
      <n-card v-if="phase" size="small" :bordered="true" class="phase-card">
        <!-- 阶段进度条（4阶段，对齐后端 StoryPhase） -->
        <div class="phase-visual">
          <div class="phase-track">
            <div
              v-for="s in PHASE_STAGES"
              :key="s.key"
              class="phase-stage"
              :class="{
                'phase-stage--active': s.key === phase.phase,
                'phase-stage--past': PHASE_ORDER.indexOf(s.key) < PHASE_ORDER.indexOf(phase.phase),
              }"
            >
              <div class="stage-dot" />
              <n-text depth="3" style="font-size: 10px">{{ s.label }}</n-text>
            </div>
          </div>
        </div>

        <!-- 当前阶段信息 -->
        <div class="phase-info">
          <n-space align="center" :size="8">
            <n-tag :type="phaseTagType" size="small" round>
              {{ phaseLabel }}
            </n-tag>
            <n-text depth="3" style="font-size: 12px">{{ phase.description }}</n-text>
          </n-space>

          <n-progress
            type="line"
            :percentage="Math.round(phase.progress * 100)"
            :height="8"
            :color="phaseColor"
            style="margin-top: 8px"
          />

          <n-text depth="3" style="font-size: 11px">
            进度 {{ Math.round(phase.progress * 100) }}%
          </n-text>
        </div>
      </n-card>

      <n-empty v-else-if="!loading" description="暂无故事阶段信息" size="small" style="margin-top: 24px" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storyPhaseApi, type StoryPhaseDTO } from '@/api/engineCore'

const props = defineProps<{ slug: string }>()

const loading = ref(false)
const phase = ref<StoryPhaseDTO | null>(null)

// 对齐后端 4 阶段模型: opening / development / convergence / finale
const PHASE_STAGES = [
  { key: 'opening', label: '开局' },
  { key: 'development', label: '发展' },
  { key: 'convergence', label: '收敛' },
  { key: 'finale', label: '终局' },
]

const PHASE_ORDER = PHASE_STAGES.map(s => s.key)

const PHASE_LABELS: Record<string, string> = {
  opening: '开局期',
  development: '发展期',
  convergence: '收敛期',
  finale: '终局期',
  // 兼容旧后端可能返回的5阶段值
  setup: '设定阶段',
  rising_action: '冲突升级',
  crisis: '危机阶段',
  climax: '高潮阶段',
  resolution: '收束阶段',
}

// 旧5阶段到新4阶段的映射
function normalizePhase(p: string): string {
  const LEGACY_MAP: Record<string, string> = {
    setup: 'opening',
    rising_action: 'development',
    crisis: 'development',
    climax: 'convergence',
    resolution: 'finale',
  }
  return LEGACY_MAP[p] || p
}

const phaseLabel = computed(() => {
  if (!phase.value) return ''
  return PHASE_LABELS[phase.value.phase] || phase.value.phase
})

const phaseTagType = computed((): 'default' | 'info' | 'success' | 'warning' | 'error' => {
  if (!phase.value) return 'default'
  const normalized = normalizePhase(phase.value.phase)
  const idx = PHASE_ORDER.indexOf(normalized)
  if (idx <= 0) return 'info'
  if (idx <= 1) return 'warning'
  if (idx === 2) return 'error'
  return 'success'
})

const phaseColor = computed(() => {
  if (!phase.value) return '#2080f0'
  const p = phase.value.progress
  if (p < 0.3) return '#2080f0'
  if (p < 0.6) return '#f59e0b'
  if (p < 0.85) return '#ef4444'
  return '#10b981'
})

async function load() {
  if (!props.slug) return
  loading.value = true
  try {
    const result = await storyPhaseApi.get(props.slug)
    // 规范化阶段值
    if (result) {
      result.phase = normalizePhase(result.phase)
    }
    phase.value = result
  } catch {
    phase.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.story-phase-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.phase-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.phase-card {
  transition: all 0.2s ease;
}

.phase-card:hover {
  border-color: var(--n-primary-color-hover);
}

.phase-visual {
  margin-bottom: 12px;
}

.phase-track {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
  padding: 0 4px;
}

.phase-track::before {
  content: '';
  position: absolute;
  top: 7px;
  left: 16px;
  right: 16px;
  height: 2px;
  background: var(--n-border-color);
}

.phase-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  position: relative;
  z-index: 1;
}

.stage-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--n-color-modal);
  border: 2px solid var(--n-border-color);
  transition: all 0.2s ease;
}

.phase-stage--past .stage-dot {
  background: #2080f0;
  border-color: #2080f0;
}

.phase-stage--active .stage-dot {
  background: #18a058;
  border-color: #18a058;
  box-shadow: 0 0 0 3px rgba(24, 160, 88, 0.2);
}

.phase-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
