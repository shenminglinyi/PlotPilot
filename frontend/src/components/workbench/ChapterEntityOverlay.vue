<template>
  <div class="overlay-trigger" @click="open = !open" :title="open ? '收起' : '展开本章实体速览'">
    📋
    <span v-if="warnings > 0" class="overlay-badge">{{ warnings }}</span>
  </div>

  <transition name="slide-fade">
    <div v-if="open" class="overlay-panel">
      <div class="overlay-header">
        <n-text strong style="font-size:13px">本章速览 · 第 {{ chapter }} 章</n-text>
        <n-button size="tiny" quaternary @click="open = false">✕</n-button>
      </div>
      <n-spin :show="loading" style="flex:1;min-height:0">
        <div v-if="factLock" class="overlay-section">
          <div class="overlay-section__title">⚔ 道具状态锁</div>
          <pre class="overlay-pre">{{ factLock }}</pre>
        </div>
        <div v-if="suggestions" class="overlay-section">
          <div class="overlay-section__title">💡 建议引入</div>
          <pre class="overlay-pre overlay-pre--muted">{{ suggestions }}</pre>
        </div>
        <div v-if="warningText" class="overlay-section">
          <div class="overlay-section__title">⚠ 一致性警告</div>
          <pre class="overlay-pre overlay-pre--warn">{{ warningText }}</pre>
        </div>
        <n-empty v-if="!loading && !factLock && !suggestions && !warningText" description="暂无道具状态" size="small" />
      </n-spin>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { propApi, type PropDTO, LIFECYCLE_LABELS } from '@/api/propApi'

const props = defineProps<{ slug: string; chapter: number | null }>()

const open = ref(false)
const loading = ref(false)
const propsList = ref<PropDTO[]>([])

const factLock = computed(() => {
  const active = propsList.value.filter(
    p => p.lifecycle_state !== 'DORMANT' && p.lifecycle_state !== 'RESOLVED'
  )
  if (!active.length) return ''
  return active.map(p => `- ${p.name}（${LIFECYCLE_LABELS[p.lifecycle_state]}）`).join('\n')
})

const suggestions = computed(() => {
  const ch = props.chapter ?? 0
  const dormant = propsList.value.filter(
    p => p.lifecycle_state === 'DORMANT' || p.lifecycle_state === 'INTRODUCED'
  ).filter(p => !p.introduced_chapter || ch - p.introduced_chapter > 3)
  if (!dormant.length) return ''
  return dormant.slice(0, 4).map(p => `- ${p.name}（${LIFECYCLE_LABELS[p.lifecycle_state]}）`).join('\n')
})

const warningText = computed(() => {
  const damaged = propsList.value.filter(p => p.lifecycle_state === 'DAMAGED')
  if (!damaged.length) return ''
  return damaged.map(p => `⚠ ${p.name} 已损毁，请注意描述`).join('\n')
})

const warnings = computed(() => warningText.value ? warningText.value.split('\n').length : 0)

async function load() {
  if (!props.slug || !open.value) return
  loading.value = true
  try {
    propsList.value = await propApi.list(props.slug)
  } finally {
    loading.value = false
  }
}

watch(open, (v) => { if (v) void load() })
watch(() => [props.slug, props.chapter], () => { if (open.value) void load() })
</script>

<style scoped>
.overlay-trigger {
  position: fixed; right: 16px; top: 50%; transform: translateY(-50%);
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--n-color); border: 1px solid var(--n-border-color);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 16px; z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}
.overlay-badge {
  position: absolute; top: -4px; right: -4px; width: 16px; height: 16px;
  border-radius: 50%; background: var(--n-error-color); color: #fff;
  font-size: 10px; display: flex; align-items: center; justify-content: center;
}
.overlay-panel {
  position: fixed; right: 60px; top: 50%; transform: translateY(-50%);
  width: 280px; max-height: 480px; overflow-y: auto;
  background: var(--app-surface); border: 1px solid var(--n-border-color);
  border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.12);
  z-index: 99; display: flex; flex-direction: column;
}
.overlay-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid var(--n-border-color);
}
.overlay-section { padding: 10px 14px; }
.overlay-section + .overlay-section { border-top: 1px solid var(--n-border-color); }
.overlay-section__title { font-size: 11px; font-weight: 600; color: var(--app-text-muted); margin-bottom: 6px; }
.overlay-pre { font-size: 11px; line-height: 1.6; white-space: pre-wrap; margin: 0; font-family: inherit; }
.overlay-pre--muted { color: var(--app-text-muted); }
.overlay-pre--warn { color: var(--n-warning-color); }
.slide-fade-enter-active, .slide-fade-leave-active { transition: all 0.2s ease; }
.slide-fade-enter-from, .slide-fade-leave-to { opacity: 0; transform: translateX(20px) translateY(-50%); }
</style>
