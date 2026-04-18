<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="Token 监控"
    style="width: 800px; max-width: 95vw"
    :bordered="false"
    :segmented="{ content: 'soft', footer: 'soft' }"
  >
    <template #header-extra>
      <n-space align="center" :size="16">
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
          开启后会记录请求和响应的详细内容，便于调试和分析
        </n-tooltip>
      </n-space>
    </template>

    <n-spin :show="loading">
      <div class="watcher-content">
        <div class="summary-cards">
          <div class="summary-card">
            <div class="summary-value">{{ formatNumber(summary.total_tokens) }}</div>
            <div class="summary-label">总 Token</div>
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
            <div class="summary-value">{{ summary.total_calls }}</div>
            <div class="summary-label">调用次数</div>
          </div>
          <div class="summary-card">
            <div class="summary-value">{{ Math.round(summary.avg_latency_ms) }}ms</div>
            <div class="summary-label">平均延迟</div>
          </div>
        </div>

        <n-divider style="margin: 16px 0" />

        <div class="logs-header">
          <span class="logs-title">调用日志</span>
          <n-button size="small" quaternary type="error" @click="showClearConfirm = true">
            清空日志
          </n-button>
        </div>

        <n-scrollbar style="max-height: 400px">
          <div v-if="logs.length === 0" class="empty-logs">
            暂无调用记录
          </div>
          <div v-else class="logs-list">
            <div
              v-for="log in logs"
              :key="log.id"
              class="log-item"
              :class="{ 'log-error': !log.success }"
            >
              <div class="log-header" @click="toggleLogExpand(log.id)" style="cursor: pointer">
                <span class="log-model">{{ log.model }}</span>
                <n-tag size="small" :type="log.success ? 'success' : 'error'">
                  {{ log.provider }}
                </n-tag>
                <span class="log-time">{{ formatTime(log.timestamp) }}</span>
                <n-popconfirm @positive-click="handleDeleteLog(log.id)">
                  <template #trigger>
                    <n-button size="tiny" quaternary type="error" style="margin-left: 8px" @click.stop>
                      删除
                    </n-button>
                  </template>
                  确定要删除这条日志记录吗？
                </n-popconfirm>
              </div>
              <div class="log-stats">
                <span>输入: {{ log.input_tokens }}</span>
                <span>输出: {{ log.output_tokens }}</span>
                <span>总计: {{ log.total_tokens }}</span>
                <span>延迟: {{ log.latency_ms }}ms</span>
              </div>
              <div v-if="log.error_message" class="log-error-msg">
                {{ log.error_message }}
              </div>
              <n-collapse v-if="!config.usage_only && (log.request_preview || log.response_preview)">
                <n-collapse-item :name="log.id" :show="isLogExpanded(log.id)">
                  <div class="log-preview-controls">
                    <n-button-group size="tiny">
                      <n-button 
                        :quaternary="getLogViewMode(log.id) !== 'pretty'" 
                        :type="getLogViewMode(log.id) === 'pretty' ? 'primary' : 'default'"
                        @click="setLogViewMode(log.id, 'pretty')"
                      >
                        美化
                      </n-button>
                      <n-button 
                        :quaternary="getLogViewMode(log.id) !== 'raw'" 
                        :type="getLogViewMode(log.id) === 'raw' ? 'primary' : 'default'"
                        @click="setLogViewMode(log.id, 'raw')"
                      >
                        源文
                      </n-button>
                    </n-button-group>
                  </div>
                  <n-tabs v-if="log.request_preview && log.response_preview" type="line" size="small">
                    <n-tab-pane name="request" tab="请求">
                      <div class="log-preview">
                        <pre class="log-json">{{ getLogViewMode(log.id) === 'pretty' ? formatJsonPretty(log.request_preview) : formatJsonRaw(log.request_preview) }}</pre>
                      </div>
                    </n-tab-pane>
                    <n-tab-pane name="response" tab="响应">
                      <div class="log-preview">
                        <pre class="log-json">{{ getLogViewMode(log.id) === 'pretty' ? formatJsonPretty(log.response_preview) : formatJsonRaw(log.response_preview) }}</pre>
                      </div>
                    </n-tab-pane>
                  </n-tabs>
                  <div v-else-if="log.request_preview">
                    <div class="log-preview-label">请求:</div>
                    <div class="log-preview">
                      <pre class="log-json">{{ getLogViewMode(log.id) === 'pretty' ? formatJsonPretty(log.request_preview) : formatJsonRaw(log.request_preview) }}</pre>
                    </div>
                  </div>
                  <div v-else-if="log.response_preview">
                    <div class="log-preview-label">响应:</div>
                    <div class="log-preview">
                      <pre class="log-json">{{ getLogViewMode(log.id) === 'pretty' ? formatJsonPretty(log.response_preview) : formatJsonRaw(log.response_preview) }}</pre>
                    </div>
                  </div>
                </n-collapse-item>
              </n-collapse>
            </div>
          </div>
        </n-scrollbar>

        <div v-if="pagination.totalPages > 1" class="pagination-wrapper">
          <n-pagination
            v-model:page="currentPage"
            :page-count="pagination.totalPages"
            :page-size="pagination.pageSize"
            @update:page="loadLogs"
          />
        </div>
      </div>
    </n-spin>
  </n-modal>

  <n-modal
    v-model:show="showClearConfirm"
    preset="confirm"
    title="确认清空"
    type="error"
    content="确定要清空所有日志记录吗？此操作不可撤销。"
    positive-text="确定"
    negative-text="取消"
    @positive-click="handleClearLogs"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useMessage, NAlert } from 'naive-ui'
import {
  tokenWatcherApi,
  type TokenLogItem,
  type TokenSummary,
  type TokenWatcherConfig,
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
const loadingToggle = ref(false)
const showClearConfirm = ref(false)
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
  success_count: 0,
  error_count: 0,
  avg_latency_ms: 0,
})
const logs = ref<TokenLogItem[]>([])
const currentPage = ref(1)
const pagination = ref({
  total: 0,
  totalPages: 0,
  pageSize: 20,
})

const expandedLogs = ref<Set<number>>(new Set())
const logViewModes = ref<Map<number, 'pretty' | 'raw'>>(new Map())

const toggleLogExpand = (logId: number) => {
  if (expandedLogs.value.has(logId)) {
    expandedLogs.value.delete(logId)
  } else {
    expandedLogs.value.add(logId)
  }
}

const isLogExpanded = (logId: number): boolean => {
  return expandedLogs.value.has(logId)
}

const getLogViewMode = (logId: number): 'pretty' | 'raw' => {
  return logViewModes.value.get(logId) || 'pretty'
}

const setLogViewMode = (logId: number, mode: 'pretty' | 'raw') => {
  logViewModes.value.set(logId, mode)
}

const formatJsonPretty = (jsonStr: string): string => {
  try {
    const parsed = JSON.parse(jsonStr)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return jsonStr
  }
}

const formatJsonRaw = (jsonStr: string): string => {
  try {
    JSON.parse(jsonStr)
    return jsonStr
  } catch {
    return jsonStr
  }
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
  try {
    const result = await tokenWatcherApi.getLogs(page, config.value.paginate)
    logs.value = result.logs
    pagination.value = {
      total: result.total,
      totalPages: result.total_pages,
      pageSize: result.page_size,
    }
    currentPage.value = result.page
  } catch (e) {
    console.error('Failed to load logs:', e)
  }
}

const loadSummary = async () => {
  try {
    summary.value = await tokenWatcherApi.getSummary()
  } catch (e) {
    console.error('Failed to load summary:', e)
  }
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
    // 当关闭详情记录时，自动收起所有已展开的日志
    if (usage_only) {
      expandedLogs.value.clear()
    }
    await loadLogs(currentPage.value)
  } catch (e) {
    console.error('Failed to update config:', e)
    message.error('更新配置失败')
  } finally {
    loadingToggle.value = false
  }
}

const handleDeleteLog = async (logId: number) => {
  try {
    await tokenWatcherApi.deleteLog(logId)
    message.success('已删除日志记录')
    await loadLogs(currentPage.value)
    await loadSummary()
  } catch (e) {
    message.error('删除日志失败')
  }
}

const handleClearLogs = async () => {
  try {
    const result = await tokenWatcherApi.clearLogs()
    message.success(`已清空 ${result.deleted_count} 条日志`)
    showClearConfirm.value = false
    await loadLogs(1)
    await loadSummary()
  } catch (e) {
    message.error('清空日志失败')
  }
}

const formatNumber = (num: number): string => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return String(num)
}

const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

watch(visible, (val) => {
  if (val) {
    loadStatus()
    loadLogs(1)
  }
})

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.watcher-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-label {
  font-size: 13px;
  color: var(--text-color-3);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.summary-card {
  text-align: center;
  padding: 12px 8px;
  background: var(--n-color-modal);
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
}

.summary-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-color-1);
}

.summary-label {
  font-size: 12px;
  color: var(--text-color-3);
  margin-top: 4px;
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.logs-title {
  font-size: 14px;
  font-weight: 500;
}

.empty-logs {
  text-align: center;
  padding: 40px 0;
  color: var(--text-color-3);
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-item {
  padding: 12px;
  background: var(--n-color-modal);
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
}

.log-item.log-error {
  border-color: var(--n-error-color);
  background: rgba(208, 48, 80, 0.05);
}

.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.log-model {
  font-weight: 500;
  font-size: 13px;
}

.log-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-color-3);
}

.log-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
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

.log-preview {
  margin-top: 8px;
  padding: 8px;
  background: rgba(0, 128, 255, 0.05);
  border-radius: 4px;
  border: 1px solid rgba(0, 128, 255, 0.1);
}

.log-preview-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-color-2);
  margin-bottom: 4px;
}

.log-preview-controls {
  margin-bottom: 8px;
  display: flex;
  justify-content: flex-start;
}

.log-json {
  margin: 0;
  padding: 8px;
  background: #1e1e1e;
  border-radius: 4px;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: #d4d4d4;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-preview-content {
  font-size: 12px;
  color: var(--text-color-3);
  word-break: break-all;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

@media (max-width: 600px) {
  .summary-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
