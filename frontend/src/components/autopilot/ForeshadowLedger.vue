<template>
  <div class="foreshadow-ledger">
    <div class="ledger-header">
      <div class="ledger-title-block">
        <span class="ledger-title">📖 伏笔雷达</span>
        <n-text depth="3" class="ledger-sub">
          只读摘要。新增 / 编辑伏笔：侧栏「片场 → 伏笔账本」→「+ 添加伏笔」（与本卡数据同源）。
        </n-text>
      </div>
      <n-space :size="8">
        <n-tag :bordered="false" size="small" type="success">
          已回收 {{ collectedCount }}
        </n-tag>
        <n-tag :bordered="false" size="small" type="warning">
          待回收 {{ pendingCount }}
        </n-tag>
        <n-button size="tiny" quaternary @click="showFullLedger">
          查看全部
        </n-button>
      </n-space>
    </div>

    <div class="ledger-body">
      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">总计</div>
          <div class="stat-value">{{ totalCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">回收率</div>
          <div class="stat-value">{{ collectionRate }}%</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均间隔</div>
          <div class="stat-value">{{ avgInterval }} 章</div>
        </div>
      </div>

      <!-- 空状态提示 -->
      <n-empty
        v-if="foreshadows.length === 0"
        description="暂无伏笔记录"
        size="small"
        style="margin: 16px 0"
      />
    </div>

    <!-- 全部伏笔弹窗 -->
    <n-modal
      v-model:show="showLedgerModal"
      preset="card"
      title="伏笔账本"
      style="width: 700px; max-height: 80vh"
    >
      <n-tabs type="line" animated>
        <n-tab-pane name="all" tab="全部">
          <div class="foreshadow-full-list">
            <n-empty v-if="allForeshadows.length === 0" description="暂无数据" size="small" />
            <div
              v-else
              v-for="item in allForeshadows"
              :key="item.id"
              class="foreshadow-full-item"
              :class="{ collected: item.is_collected }"
            >
              <div class="full-item-header">
                <n-tag
                  :type="importanceTagType(item.importance)"
                  size="small"
                  :bordered="false"
                >
                  {{ importanceLabel(item.importance) }}
                </n-tag>
                <n-text depth="3" style="font-size: 12px">
                  {{ item.is_collected ? '✓ 已回收' : '⏳ 待回收' }}
                </n-text>
              </div>
              <div class="full-item-text">{{ item.description }}</div>
              <div class="full-item-meta">
                <n-text depth="3" style="font-size: 12px">
                  第 {{ item.planted_chapter }} 章埋设
                  <template v-if="item.is_collected && item.collected_chapter">
                    · 第 {{ item.collected_chapter }} 章回收
                  </template>
                </n-text>
              </div>
            </div>
          </div>
        </n-tab-pane>
        <n-tab-pane name="pending" tab="待回收">
          <div class="foreshadow-full-list">
            <n-empty v-if="pendingForeshadows.length === 0" description="暂无数据" size="small" />
            <div
              v-else
              v-for="item in pendingForeshadows"
              :key="item.id"
              class="foreshadow-full-item"
            >
              <div class="full-item-header">
                <n-tag
                  :type="importanceTagType(item.importance)"
                  size="small"
                  :bordered="false"
                >
                  {{ importanceLabel(item.importance) }}
                </n-tag>
                <n-text depth="3" style="font-size: 12px">⏳ 待回收</n-text>
              </div>
              <div class="full-item-text">{{ item.description }}</div>
              <div class="full-item-meta">
                <n-text depth="3" style="font-size: 12px">
                  第 {{ item.planted_chapter }} 章埋设
                </n-text>
              </div>
            </div>
          </div>
        </n-tab-pane>
        <n-tab-pane name="collected" tab="已回收">
          <div class="foreshadow-full-list">
            <n-empty v-if="collectedForeshadows.length === 0" description="暂无数据" size="small" />
            <div
              v-else
              v-for="item in collectedForeshadows"
              :key="item.id"
              class="foreshadow-full-item collected"
            >
              <div class="full-item-header">
                <n-tag
                  :type="importanceTagType(item.importance)"
                  size="small"
                  :bordered="false"
                >
                  {{ importanceLabel(item.importance) }}
                </n-tag>
                <n-text depth="3" style="font-size: 12px">✓ 已回收</n-text>
              </div>
              <div class="full-item-text">{{ item.description }}</div>
              <div class="full-item-meta">
                <n-text depth="3" style="font-size: 12px">
                  第 {{ item.planted_chapter }} 章埋设 · 第 {{ item.collected_chapter }} 章回收
                </n-text>
              </div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { foreshadowApi } from '../../api/foreshadow'
import { isRequestCanceled } from '../../utils/requestCancel'

interface Foreshadow {
  id: string
  description: string
  importance: 'low' | 'medium' | 'high' | 'critical'
  planted_chapter: number
  is_collected: boolean
  collected_chapter?: number
  created_at: string
}

const props = defineProps<{
  novelId: string
  maxRecent?: number  // 最多显示几条最近伏笔，默认 5
  refreshKey?: number  // 🔥 刷新信号，变化时重新拉数据
}>()

const foreshadows = ref<Foreshadow[]>([])
const showLedgerModal = ref(false)
const loading = ref(false)

let pollTimer: number | null = null
// 🔥 请求取消控制器：新请求发出前取消上一个未完成的请求
let loadAbortController: AbortController | null = null

// 统计
const totalCount = computed(() => foreshadows.value.length)
const collectedCount = computed(() => foreshadows.value.filter(f => f.is_collected).length)
const pendingCount = computed(() => totalCount.value - collectedCount.value)
const collectionRate = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round((collectedCount.value / totalCount.value) * 100)
})

// 平均回收间隔
const avgInterval = computed(() => {
  const collected = foreshadows.value.filter(f => f.is_collected && f.collected_chapter)
  if (collected.length === 0) return 0
  const intervals = collected.map(f => (f.collected_chapter! - f.planted_chapter))
  const sum = intervals.reduce((a, b) => a + b, 0)
  return Math.round(sum / intervals.length)
})

// 最近伏笔（按创建时间倒序）
const recentForeshadows = computed(() => {
  const sorted = [...foreshadows.value].sort((a, b) => {
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
  return sorted.slice(0, props.maxRecent ?? 5)
})

// 分类列表
const allForeshadows = computed(() => foreshadows.value)
const pendingForeshadows = computed(() => foreshadows.value.filter(f => !f.is_collected))
const collectedForeshadows = computed(() => foreshadows.value.filter(f => f.is_collected))

// 重要性标签
function importanceLabel(importance: string): string {
  const map: Record<string, string> = {
    low: '次要',
    medium: '一般',
    high: '重要',
    critical: '关键'
  }
  return map[importance] || importance
}

function importanceTagType(importance: string): 'default' | 'info' | 'warning' | 'error' {
  const map: Record<string, 'default' | 'info' | 'warning' | 'error'> = {
    low: 'default',
    medium: 'info',
    high: 'warning',
    critical: 'error'
  }
  return map[importance] || 'default'
}

// 🔥 伏笔列表独立超时：10 秒（远小于全局 120s，避免长时间挂起）
const FORESHADOW_TIMEOUT_MS = 10_000

// 与片场「伏笔账本」共用 foreshadow-ledger，经 foreshadowApi 与监控统计对齐
async function loadForeshadows() {
  // 🔥 取消上一个未完成的请求，防止并发堆积
  if (loadAbortController) {
    loadAbortController.abort()
  }
  const ac = new AbortController()
  loadAbortController = ac

  loading.value = true
  const timeoutId = setTimeout(() => ac.abort(), FORESHADOW_TIMEOUT_MS)
  try {
    const entries = await foreshadowApi.list(props.novelId, undefined, {
      signal: ac.signal,
      timeout: FORESHADOW_TIMEOUT_MS,
    })
    // 🔥 仅在请求未被取消时更新（避免过期响应覆盖新数据）
    if (!ac.signal.aborted) {
      foreshadows.value = entries.map((entry) => ({
        id: entry.id,
        description: entry.question,
        importance: 'medium' as const,
        planted_chapter: entry.chapter,
        is_collected: entry.status === 'consumed',
        collected_chapter: entry.consumed_at_chapter ?? undefined,
        created_at: entry.created_at,
      }))
    }
  } catch (err) {
    if (isRequestCanceled(err)) {
      return
    }
    console.error('Failed to load foreshadows:', err)
  } finally {
    clearTimeout(timeoutId)
    if (loadAbortController === ac) {
      loadAbortController = null
    }
    loading.value = false
  }
}

// 显示全部账本
function showFullLedger() {
  showLedgerModal.value = true
}

// 🔥 定时轮询间隔从 20s 提升到 30s（伏笔数据变化不频繁，降低 DB 压力）
const POLL_INTERVAL_MS = 30_000

function startPolling() {
  loadForeshadows()
  pollTimer = window.setInterval(() => {
    loadForeshadows()
  }, POLL_INTERVAL_MS)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  // 🔥 停止轮询时取消进行中的请求
  if (loadAbortController) {
    loadAbortController.abort()
    loadAbortController = null
  }
}

// 监听
watch(() => props.novelId, () => {
  stopPolling()
  startPolling()
})

// 🔥 刷新信号变化时重新加载（由 Dashboard 的 SSE 事件驱动）
watch(() => props.refreshKey, (newKey) => {
  if (newKey && newKey > 0) void loadForeshadows()
})

// 生命周期
onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.foreshadow-ledger {
  background: var(--card-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.ledger-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.ledger-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ledger-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color-1);
}

.ledger-sub {
  font-size: 11px;
  line-height: 1.35;
}

.ledger-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.stat-card {
  background: var(--color-target-modal);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px;
  text-align: center;
}

.stat-label {
  font-size: 11px;
  color: var(--text-color-3);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-color-1);
  font-variant-numeric: tabular-nums;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color-2);
  margin-bottom: 4px;
}

.foreshadow-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  background: var(--color-target-modal);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  transition: all 0.2s;
}

.foreshadow-item:hover {
  background: var(--hover-color);
  border-color: var(--border-color);
}

.foreshadow-item.collected {
  opacity: 0.7;
}

.item-icon {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  background: var(--color-target-modal);
  border-radius: 50%;
}

.item-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.item-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-1);
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-text {
  font-size: 11px;
}

.importance-tag {
  font-size: 10px;
}

/* 全部伏笔列表样式 */
.foreshadow-full-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 500px;
  overflow-y: auto;
  padding: 8px;
}

.foreshadow-full-item {
  padding: 12px;
  background: var(--color-target-modal);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  transition: all 0.2s;
}

.foreshadow-full-item:hover {
  background: var(--hover-color);
  border-color: var(--border-color);
}

.foreshadow-full-item.collected {
  opacity: 0.7;
}

.full-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.full-item-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-color-1);
  margin-bottom: 8px;
}

.full-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
