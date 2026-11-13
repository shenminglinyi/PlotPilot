<template>
  <div class="plaza-entry">
    <button
      type="button"
      class="plaza-main"
      :class="appearance === 'sidebar' ? 'variant-sidebar' : 'variant-topbar'"
      aria-label="打开墨枢模组中心"
      @mouseenter="prefetchPromptPlaza"
      @click="openModal"
    >
      <span class="plaza-main-content">
        <template v-if="appearance === 'sidebar'">
          <span class="plaza-plain-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none">
              <path
                d="M6.5 3v3M13.5 3v3M4.5 6h11v3.5a5.5 5.5 0 0 1-11 0V6ZM10 15v2"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </span>
          <span class="plaza-title">模组中心</span>
          <span v-if="modHubStore.installedCount > 0" class="sidebar-badge numeric">
            已装 {{ modHubStore.installedCount }}
          </span>
        </template>
        <template v-else>
          <span class="plaza-icon-core" aria-hidden="true">模</span>
          <span class="plaza-copy">
            <span class="plaza-title-row">
              <span class="plaza-title">模组中心</span>
              <span v-if="promptCount > 0" class="plaza-count numeric">{{ promptCount }}</span>
            </span>
            <span class="plaza-subtitle">发现 · 安装 · 内核管理</span>
          </span>
        </template>
      </span>
    </button>

    <teleport to="body">
      <n-modal
        v-model:show="showModal"
        preset="card"
        title=""
        :style="{ width: '94vw', maxWidth: '1140px', height: '86vh', marginTop: '4vh' }"
        :bordered="true"
        :content-style="{ padding: '0', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
        :mask-closable="true"
        :close-on-esc="true"
        @after-leave="onModalClose"
      >
        <template #header>
          <div class="modal-header">
            <div class="modal-header-left">
              <span class="modal-header-icon" aria-hidden="true">模</span>
              <span class="modal-header-title">墨枢模组中心</span>
              <span class="modal-header-sub">
                安装文风与审稿模组 · 同步云端书元 · 管理 {{ promptCount || 78 }} 个内核节点
              </span>
            </div>
            <button type="button" class="open-fullpage-btn" @click="goFullScreenSquare">
              全屏打开 ↗
            </button>
          </div>
        </template>

        <div class="modal-body">
          <PromptPlaza
            v-if="showModal"
            ref="plazaRef"
            :seed-stats="stats"
            @refresh-stats="onPlazaRefreshStats"
            @request-cloud-login="goFullScreenSquare"
          />
        </div>
      </n-modal>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent, h } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, NSpin } from 'naive-ui'
import { promptPlazaApi, type PromptStats } from '../../api/llmControl'
import { useModHubStore } from '@/stores/modHubStore'

const PromptPlaza = defineAsyncComponent({
  loader: () => import('../workbench/PromptPlaza.vue'),
  delay: 0,
  loadingComponent: {
    name: 'PromptPlazaChunkLoading',
    setup() {
      return () =>
        h(
          'div',
          { class: 'plaza-chunk-loading' },
          h(NSpin, { size: 'large', description: '加载模组中心…' }),
        )
    },
  },
})

type Appearance = 'sidebar' | 'topbar'

withDefaults(
  defineProps<{
    appearance?: Appearance
  }>(),
  {
    appearance: 'sidebar',
  },
)

const router = useRouter()
const modHubStore = useModHubStore()

const showModal = ref(false)
const promptCount = ref(0)
const stats = ref<PromptStats | null>(null)
const plazaRef = ref<{ loadData: () => Promise<void> } | null>(null)

function openModal(): void {
  showModal.value = true
}

function onModalClose(): void {
  void loadStats()
}

function goFullScreenSquare(): void {
  showModal.value = false
  void router.push('/square')
}

async function loadStats(): Promise<void> {
  try {
    const res = await promptPlazaApi.getStats()
    const data = res as unknown as PromptStats
    stats.value = data
    promptCount.value = data?.total_nodes || 0
  } catch {
    // 静默
  }
}

function onPlazaRefreshStats(payload: PromptStats | null): void {
  if (payload != null) {
    stats.value = payload
    promptCount.value = payload.total_nodes || 0
    return
  }
  void loadStats()
}

let plazaChunkPrefetchStarted = false
function prefetchPromptPlaza(): void {
  if (plazaChunkPrefetchStarted) return
  plazaChunkPrefetchStarted = true
  void import('../workbench/PromptPlaza.vue')
}

onMounted(() => {
  void loadStats()
})
</script>

<style scoped>
.plaza-entry {
  display: inline-flex;
  align-items: center;
  width: 100%;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.plaza-main {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-primary);
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.plaza-main.variant-sidebar {
  min-height: 38px;
  padding: 0 12px;
  border-radius: 9px;
}

.plaza-main.variant-sidebar:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.plaza-main.variant-topbar {
  width: 220px;
  min-height: 46px;
  padding: 8px 12px;
  border-radius: 10px;
}

.plaza-main-content {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
}

.plaza-plain-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-brand);
  flex: none;
}

.plaza-plain-icon svg {
  width: 16px;
  height: 16px;
}

.plaza-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  flex: 1;
  text-align: left;
}

.sidebar-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.plaza-icon-core {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}

.plaza-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.plaza-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.plaza-count {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
}

.plaza-subtitle {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding-right: 12px;
}

.modal-header-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.modal-header-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand);
  color: var(--app-text-inverse);
  font-size: 13px;
  font-weight: 700;
}

.modal-header-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.modal-header-sub {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.open-fullpage-btn {
  height: 30px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.open-fullpage-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.modal-body {
  height: calc(86vh - 62px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.plaza-chunk-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

@media (max-width: 640px) {
  .modal-header-sub {
    display: none;
  }
}
</style>
