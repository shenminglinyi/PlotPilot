<template>
  <n-drawer
    v-model:show="visible"
    placement="left"
    :width="650"
    native-scrollbar="false"
    title="Token 监控"
  >
    <div class="watcher-drawer">
      <div class="watcher-header-extra">
        <n-space align="center" :size="16">
          <n-tooltip trigger="hover" placement="bottom">
            <template #trigger>
              <n-space align="center" :size="8">
                <span class="status-label">自动刷新</span>
                <n-switch
                  :value="autoRefresh"
                  @update:value="handleToggleAutoRefresh"
                  color="#10b981"
                >
                  <template #checked>开</template>
                  <template #unchecked>关</template>
                </n-switch>
              </n-space>
            </template>
            开启后每 2 秒自动刷新面板数据
          </n-tooltip>

          <n-tooltip trigger="hover" placement="bottom">
            <template #trigger>
              <n-space align="center" :size="8">
                <span class="status-label">监控状态</span>
                <n-switch
                  :value="config.enabled"
                  :loading="loadingToggle"
                  @update:value="handleToggleEnabled"
                >
                  <template #checked>开</template>
                  <template #unchecked>关</template>
                </n-switch>
              </n-space>
            </template>
            开启后会记录所有 LLM 调用的 token 使用情况，包括输入/输出 token 数量、延迟等
          </n-tooltip>

          <n-tooltip trigger="hover" placement="bottom">
            <template #trigger>
              <n-space align="center" :size="8">
                <span class="status-label">详情记录</span>
                <n-switch
                  :value="!config.usage_only"
                  :loading="loadingToggle"
                  @update:value="handleToggleUsageOnly"
                >
                  <template #checked>开</template>
                  <template #unchecked>关</template>
                </n-switch>
              </n-space>
            </template>
            开启后会在 Log 记录请求和响应的详细内容，便于调试和分析
          </n-tooltip>
          <n-button size="small" type="error" @click="showResetStatsConfirm = true">
            重置统计
          </n-button>
        </n-space>
      </div>

      <n-spin :show="loading">
        <div class="watcher-content">
          <div class="content-section">
            <div class="summary-cards">
              <div class="summary-card">
                <div class="summary-value">{{ formatNumber(summary.total_tokens) }}</div>
                <div class="summary-label">总 Token</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ summary.total_calls }}</div>
                <div class="summary-label">调用次数</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ formatNumber(summary.total_input_tokens) }}</div>
                <div class="summary-label">输入 Token</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ formatNumber(summary.total_output_tokens) }}</div>
                <div class="summary-label">输出 Token</div>
              </div>
              
              <div class="summary-card">
                <div class="summary-value">{{ Math.round(summary.avg_latency_ms) }}ms</div>
                <div class="summary-label">平均延迟</div>
              </div>
            </div>
          </div>

          <div class="content-section">
            <n-collapse>
              <n-collapse-item name="stats">
                <template #header>
                  <span class="stats-title">维度统计</span>
                </template>
                <div class="stats-header">
                  <n-select
                    v-model:value="statsGroupBy"
                    :options="groupByOptions"
                    size="small"
                    style="width: 140px"
                    @update:value="loadStats"
                  />
                </div>
                <n-spin :show="loadingStats" size="small">
                  <n-scrollbar style="max-height: 200px">
                    <div v-if="dimensionStats.length === 0" class="empty-stats">
                      暂无统计数据
                    </div>
                    <div v-else class="stats-list">
                      <div v-for="(stat, index) in dimensionStats" :key="index" class="stat-item">
                        <div class="stat-name">
                          <template v-if="statsGroupBy === 'provider_model'">
                            <n-tag size="small" type="info">{{ stat.provider }}</n-tag>
                            <span class="stat-model">{{ stat.model }}</span>
                          </template>
                          <template v-else-if="statsGroupBy === 'provider'">
                            <n-tag size="small" type="info">{{ stat.provider }}</n-tag>
                          </template>
                          <template v-else>
                            <span class="stat-model">{{ stat.model }}</span>
                          </template>
                        </div>
                        <div class="stat-values">
                          <span class="stat-token">{{ formatNumber(stat.total_tokens) }} tokens</span>
                          <span class="stat-calls">{{ stat.total_calls }} 次</span>
                        </div>
                      </div>
                    </div>
                  </n-scrollbar>
                </n-spin>
              </n-collapse-item>
            </n-collapse>
          </div>

          <div class="content-section">
            <div class="logs-header">
              <span class="logs-title">调用记录</span>
              <n-space :size="8">
                <n-button size="small" quaternary @click="handleExportLogs">
                  导出
                </n-button>
              </n-space>
            </div>

            <div class="logs-filters">
              <n-select
                v-model:value="filterTimeRange"
                :options="timeRangeOptions"
                size="small"
                placeholder="时间范围"
                clearable
                style="width: 100px"
                @update:value="handleFilterChange"
              />
              <n-select
                v-model:value="filterProvider"
                :options="providerOptions"
                size="small"
                placeholder="提供商"
                clearable
                style="width: 120px"
                @update:value="handleFilterChange"
              />
              <n-select
                v-model:value="filterModel"
                :options="modelOptions"
                size="small"
                placeholder="模型"
                clearable
                style="width: 150px"
                @update:value="handleFilterChange"
              />
            </div>

            <n-spin :show="loadingLogs" size="small">
              <n-scrollbar style="max-height: 400px">
                <div v-if="logs.length === 0" class="empty-logs">
                  暂无调用记录
                </div>
                <div v-else class="logs-list">
                  <div
                    v-for="log in logs"
                    :key="log.id"
                    class="log-item"
                    :class="{
                      'log-error': getLogWarningLevel(log).level === 'error',
                      'log-danger': getLogWarningLevel(log).level === 'danger',
                      'log-warning': getLogWarningLevel(log).level === 'warning'
                    }"
                  >
                    <div class="log-header">
                      <span class="log-model">{{ log.model }}</span>
                      <n-tag size="small" :type="log.success ? 'success' : 'error'">
                        {{ log.provider }}
                      </n-tag>
                      <span class="log-time">{{ formatTime(log.timestamp) }}</span>
                    </div>
                    <div class="log-stats">
                      <span>输入: {{ log.input_tokens }}</span>
                      <span>输出: {{ log.output_tokens }}</span>
                      <span>延迟: {{ log.latency_ms }}ms</span>
                    </div>
                    <div v-if="getLogWarningLevel(log).reasons.length > 0" class="log-warnings">
                      <n-tag
                        v-for="(reason, index) in getLogWarningLevel(log).reasons"
                        :key="index"
                        size="small"
                        :type="getLogWarningLevel(log).level === 'error' ? 'error' : getLogWarningLevel(log).level === 'danger' ? 'warning' : 'info'"
                      >
                        {{ reason }}
                      </n-tag>
                    </div>
                    <div v-if="log.error_message" class="log-error-msg">
                      {{ log.error_message }}
                    </div>
                  </div>
                </div>
              </n-scrollbar>
            </n-spin>

            <div v-if="pagination.totalPages > 1" class="pagination-wrapper">
              <n-pagination
                v-model:page="currentPage"
                :page-count="pagination.totalPages"
                :page-size="pagination.pageSize"
                @update:page="loadLogs"
              />
            </div>
          </div>
        </div>
      </n-spin>
    </div>
  </n-drawer>

  <n-modal
    v-model:show="showResetStatsConfirm"
    preset="confirm"
    title="确认重置"
    type="warning"
    content="确定要重置统计数据吗？此操作将同时清空所有日志记录，不可撤销。"
    positive-text="确定"
    negative-text="取消"
    @positive-click="handleResetStats"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  tokenWatcherApi,
  type TokenLogItem,
  type TokenSummary,
  type TokenWatcherConfig,
  type TokenStatsItem,
} from '@/api/tokenWatcher'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'config-change': [config: TokenWatcherConfig]
}>()

const message = useMessage()

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val),
})

const loading = ref(false)
const loadingLogs = ref(false)
const loadingStats = ref(false)
const loadingToggle = ref(false)
const showResetStatsConfirm = ref(false)
const autoRefresh = ref(true)
const refreshInterval = 2000
let refreshTimer: ReturnType<typeof setInterval> | null = null
const config = ref<TokenWatcherConfig>({
  enabled: false,
  paginate: 20,
  usage_only: true,
})
const summary = ref<TokenSummary>({
  total_calls: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  total_tokens: 0,
  avg_latency_ms: 0,
})
const logs = ref<TokenLogItem[]>([])
const currentPage = ref(1)
const pagination = ref({
  total: 0,
  totalPages: 0,
  pageSize: 20,
})

const statsGroupBy = ref<string>('provider_model')
const dimensionStats = ref<TokenStatsItem[]>([])
const groupByOptions = [
  { label: '提供商 + 模型', value: 'provider_model' },
  { label: '按提供商', value: 'provider' },
  { label: '按模型', value: 'model' },
]

const filterTimeRange = ref<string | null>(null)
const filterProvider = ref<string | null>(null)
const filterModel = ref<string | null>(null)
const availableProviders = ref<string[]>([])
const availableModels = ref<string[]>([])

const timeRangeOptions = [
  { label: '今天', value: 'today' },
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
]

const providerOptions = computed(() =>
  availableProviders.value.map(p => ({ label: p, value: p }))
)

const modelOptions = computed(() =>
  availableModels.value.map(m => ({ label: m, value: m }))
)

const formatTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return timestamp
  }
}

interface LogWarningLevel {
  level: 'none' | 'warning' | 'danger' | 'error'
  reasons: string[]
}

const getLogWarningLevel = (log: TokenLogItem): LogWarningLevel => {
  const reasons: string[] = []
  let level: LogWarningLevel['level'] = 'none'

  // 1. 错误级：请求失败
  if (!log.success) {
    level = 'error'
    reasons.push('请求失败')
    return { level, reasons }
  }

  // 2. 危险级：延迟过高（> 60秒）
  if (log.latency_ms > 60000) {
    level = 'danger'
    reasons.push('延迟过高')
  }

  // 3. 警告级：延迟偏高（> 30秒）
  if (log.latency_ms > 30000 && level === 'none') {
    level = 'warning'
    reasons.push('延迟偏高')
  }

  return { level, reasons }
}

const loadStatus = async () => {
  loading.value = true
  try {
    const status = await tokenWatcherApi.getStatus()
    config.value = status.config
    summary.value = status.summary
    emit('config-change', status.config)
  } catch (e) {
    console.error('Failed to load token watcher status:', e)
  } finally {
    loading.value = false
  }
}

const loadLogs = async (page: number = 1) => {
  loadingLogs.value = true
  try {
    const result = await tokenWatcherApi.getLogs({
      page,
      pageSize: config.value.paginate,
      provider: filterProvider.value || undefined,
      model: filterModel.value || undefined,
      timeRange: filterTimeRange.value || undefined,
    })
    logs.value = result.logs
    pagination.value = {
      total: result.total,
      totalPages: result.total_pages,
      pageSize: result.page_size,
    }
    currentPage.value = result.page
  } catch (e) {
    console.error('Failed to load logs:', e)
  } finally {
    loadingLogs.value = false
  }
}

const loadSummary = async () => {
  try {
    summary.value = await tokenWatcherApi.getSummary()
  } catch (e) {
    console.error('Failed to load summary:', e)
  }
}

const loadStats = async () => {
  loadingStats.value = true
  try {
    dimensionStats.value = await tokenWatcherApi.getStats(
      statsGroupBy.value,
      undefined,
      undefined,
      filterTimeRange.value || undefined
    )
  } catch (e) {
    console.error('Failed to load stats:', e)
  } finally {
    loadingStats.value = false
  }
}

const loadFilters = async () => {
  try {
    const filters = await tokenWatcherApi.getFilters()
    availableProviders.value = filters.providers
    availableModels.value = filters.models
  } catch (e) {
    console.error('Failed to load filters:', e)
  }
}

const handleFilterChange = () => {
  loadLogs(1)
  loadStats()
}

const handleToggleEnabled = async (enabled: boolean) => {
  loadingToggle.value = true
  try {
    config.value = await tokenWatcherApi.updateConfig({ enabled })
    emit('config-change', config.value)
    message.success(enabled ? '监控已开启' : '监控已关闭')
  } catch (e) {
    console.error('Failed to update config:', e)
    message.error('更新配置失败')
  } finally {
    loadingToggle.value = false
  }
}

const handleToggleUsageOnly = async (value: boolean) => {
  const usage_only = !value
  loadingToggle.value = true
  try {
    config.value = await tokenWatcherApi.updateConfig({ usage_only })
    emit('config-change', config.value)
    message.success(usage_only ? '详情记录已关闭' : '详情记录已开启')
    await loadLogs(currentPage.value)
  } catch (e) {
    console.error('Failed to update config:', e)
    message.error('更新配置失败')
  } finally {
    loadingToggle.value = false
  }
}

const handleToggleAutoRefresh = (value: boolean) => {
  autoRefresh.value = value
  if (value) {
    startRefreshTimer()
    message.success('自动刷新已开启')
  } else {
    stopRefreshTimer()
    message.success('自动刷新已关闭')
  }
}

const startRefreshTimer = () => {
  stopRefreshTimer()
  if (visible.value && autoRefresh.value) {
    refreshTimer = setInterval(() => {
      loadSummary()
      loadLogs(currentPage.value)
      loadStats()
    }, refreshInterval)
  }
}

const stopRefreshTimer = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const handleResetStats = async () => {
  try {
    const result = await tokenWatcherApi.resetStats()
    message.success(`已重置统计并清空 ${result.deleted_count} 条记录`)
    showResetStatsConfirm.value = false
    await loadSummary()
    await loadStats()
    await loadLogs(1)
  } catch (e) {
    message.error('重置统计失败')
  }
}

const handleExportLogs = async () => {
  try {
    const data = await tokenWatcherApi.exportLogs({
      provider: filterProvider.value || undefined,
      model: filterModel.value || undefined,
      timeRange: filterTimeRange.value || undefined,
    })

    const json = JSON.stringify(data, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `token-logs-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success(`已导出 ${data.length} 条日志`)
  } catch (e) {
    console.error('Failed to export logs:', e)
    message.error('导出失败')
  }
}

const formatNumber = (num: number): string => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return String(num)
}

watch(visible, (val) => {
  if (val) {
    loadStatus()
    loadLogs(1)
    loadStats()
    loadFilters()
    if (autoRefresh.value) {
      startRefreshTimer()
    }
  } else {
    stopRefreshTimer()
  }
})

watch(autoRefresh, (val) => {
  if (visible.value && val) {
    startRefreshTimer()
  } else {
    stopRefreshTimer()
  }
})
</script>

<style scoped>
.watcher-drawer {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: #f1f5f9;
}

.watcher-header-extra {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: none;
  width: 100%;
}

.watcher-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
  width: 100%;
  align-items: center;
}

.content-section {
  width: 100%;
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.04);
}

.status-label {
  font-size: 13px;
  color: var(--text-color-3);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  width: 100%;
}

.summary-card {
  text-align: center;
  padding: 20px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.summary-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.5px;
}

.summary-label {
  font-size: 13px;
  color: #64748b;
  margin-top: 8px;
  font-weight: 500;
}

.stats-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.stats-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.empty-stats {
  text-align: center;
  padding: 24px 0;
  color: #94a3b8;
}

.stats-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid #f1f5f9;
  transition: all 0.2s ease;
}

.stat-item:hover {
  background: #f1f5f9;
  border-color: #e2e8f0;
}

.stat-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-model {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.stat-values {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  text-align: right;
}

.stat-token {
  color: #2563eb;
  font-weight: 600;
}

.stat-calls {
  color: #64748b;
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.logs-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.logs-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.empty-logs {
  text-align: center;
  padding: 40px 0;
  color: #94a3b8;
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.log-item {
  padding: 14px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s ease;
}

.log-item.log-error {
  border-color: #fecaca;
  background: #fef2f2;
  border-left-width: 4px;
  border-left-color: #ef4444;
}

.log-item.log-danger {
  border-color: #fed7aa;
  background: #fff7ed;
  border-left-width: 4px;
  border-left-color: #f97316;
}

.log-item.log-warning {
  border-color: #fde68a;
  background: #fefce8;
  border-left-width: 4px;
  border-left-color: #eab308;
}

.log-warnings {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.log-model {
  font-weight: 600;
  font-size: 14px;
}

.log-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-color-3);
}

.log-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: var(--text-color-2);
}

.log-error-msg {
  margin-top: 8px;
  padding: 8px;
  background: rgba(208, 48, 80, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: var(--n-error-color);
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
