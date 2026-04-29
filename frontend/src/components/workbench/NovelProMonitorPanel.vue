<template>
  <div class="monitor-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">监控中心</h3>
          <n-tag size="small" round :bordered="false" :type="healthType">
            {{ healthLabel }}
          </n-tag>
        </div>
        <p class="panel-lead">
          自动汇总 Obsidian 主记忆、关系图、连续性巡检和战力风险。这里先看红黄灯，再决定去哪个面板修。
        </p>
      </div>
      <n-button size="small" type="primary" secondary :loading="loading" @click="loadOverview">
        刷新
      </n-button>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <n-alert v-if="loadError" type="error" :show-icon="true" class="section-alert">
          {{ loadError }}
        </n-alert>

        <template v-else-if="overview">
          <n-space vertical :size="14">
            <section class="score-card" :class="`score-card--${overview.health.status}`">
              <div>
                <span class="score-label">NovelPro 健康分</span>
                <strong>{{ overview.health.score }}</strong>
              </div>
              <n-space :size="6" wrap>
                <n-tag size="small" round :type="overview.health.error_count ? 'error' : 'success'">
                  严重 {{ overview.health.error_count }}
                </n-tag>
                <n-tag size="small" round :type="overview.health.warning_count ? 'warning' : 'success'">
                  提醒 {{ overview.health.warning_count }}
                </n-tag>
                <n-tag size="small" round>
                  共 {{ overview.health.alert_count }} 条
                </n-tag>
              </n-space>
            </section>

            <n-grid :cols="2" :x-gap="10" :y-gap="10" responsive="screen">
              <n-grid-item>
                <n-card size="small" :bordered="false" title="Obsidian 主记忆">
                  <n-space vertical :size="8">
                    <n-space :size="6" wrap>
                      <n-tag round size="small" :type="overview.obsidian.primary_memory ? 'success' : 'warning'">
                        {{ overview.obsidian.primary_memory ? '已接管' : '待建立' }}
                      </n-tag>
                      <n-tag round size="small" :type="overview.obsidian.obsidian_app_installed ? 'success' : 'default'">
                        {{ overview.obsidian.obsidian_app_installed ? '已检测到 Obsidian' : '未检测到 Obsidian' }}
                      </n-tag>
                      <n-tag round size="small" :type="overview.obsidian.vault_configured ? 'info' : 'default'">
                        {{ overview.obsidian.vault_configured ? '自定义 Vault' : '默认 Vault' }}
                      </n-tag>
                    </n-space>
                    <n-text depth="3" style="font-size: 12px">
                      章节 {{ overview.obsidian.chapter_count }} · 事实 {{ overview.obsidian.fact_count }} ·
                      {{ overview.obsidian.premise_locked ? '基调已锁定' : '基调待锁定' }}
                    </n-text>
                    <n-alert
                      v-if="!overview.obsidian.primary_memory"
                      type="warning"
                      :show-icon="false"
                      class="mini-alert"
                    >
                      保存章节或采纳候选稿后，会自动生成 Obsidian Markdown 主记忆；仅生成但未保存不会写入。
                    </n-alert>
                    <n-alert
                      v-if="!overview.obsidian.obsidian_app_installed"
                      type="default"
                      :show-icon="false"
                      class="mini-alert"
                    >
                      未安装 Obsidian 也能写入 Markdown。安装后可在 Obsidian 中打开下方 Vault 路径查看图谱。
                    </n-alert>
                    <n-text v-if="overview.obsidian.vault_path" depth="3" class="path-text">
                      Vault：{{ overview.obsidian.vault_path }}
                    </n-text>
                    <n-text v-if="overview.obsidian.relationship_graph_path" depth="3" class="path-text">
                      关系图：{{ overview.obsidian.relationship_graph_path }}
                    </n-text>
                    <n-text depth="3" class="config-text">
                      自定义路径：在后端 `.env` 添加 `PLOTPILOT_OBSIDIAN_VAULT=/你的/Obsidian/Vault/路径`，然后重启后端。
                    </n-text>
                    <n-space :size="8" wrap>
                      <n-button size="tiny" secondary :disabled="!overview.obsidian.vault_path" @click="copyVaultPath">
                        复制 Vault 路径
                      </n-button>
                      <n-button
                        size="tiny"
                        type="primary"
                        secondary
                        :loading="syncingObsidian"
                        :disabled="!currentChapter"
                        @click="syncCurrentChapter"
                      >
                        同步当前章
                      </n-button>
                    </n-space>
                  </n-space>
                </n-card>
              </n-grid-item>

              <n-grid-item>
                <n-card size="small" :bordered="false" title="知识关系图">
                  <n-space vertical :size="8">
                    <n-tag round size="small" :type="overview.knowledge_graph.relationship_count ? 'success' : 'warning'">
                      关系 {{ overview.knowledge_graph.relationship_count }}
                    </n-tag>
                    <n-text depth="3" style="font-size: 12px">
                      实体 {{ overview.knowledge_graph.entity_count }} · 三元组 {{ overview.knowledge_graph.fact_count }}
                    </n-text>
                  </n-space>
                </n-card>
              </n-grid-item>

              <n-grid-item>
                <n-card size="small" :bordered="false" title="连续性监控">
                  <n-space :size="6" wrap>
                    <n-tag round size="small" :type="overview.continuity.dropout_count ? 'warning' : 'success'">
                      掉线 {{ overview.continuity.dropout_count }}
                    </n-tag>
                    <n-tag round size="small" :type="overview.continuity.stale_relationship_count ? 'warning' : 'success'">
                      沉默关系 {{ overview.continuity.stale_relationship_count }}
                    </n-tag>
                    <n-tag round size="small" :type="overview.continuity.timeline_conflict_count ? 'error' : 'success'">
                      时间冲突 {{ overview.continuity.timeline_conflict_count }}
                    </n-tag>
                    <n-tag round size="small" :type="outlineType(overview.continuity.outline_status)">
                      大纲 {{ outlineLabel(overview.continuity.outline_status) }}
                    </n-tag>
                  </n-space>
                </n-card>
              </n-grid-item>

              <n-grid-item>
                <n-card size="small" :bordered="false" title="战力守恒">
                  <n-space vertical :size="8">
                    <n-tag round size="small" :type="overview.power.warning_count ? 'warning' : 'success'">
                      战力提醒 {{ overview.power.warning_count }}
                    </n-tag>
                    <n-text depth="3" style="font-size: 12px">
                      已登记角色战力档案 {{ overview.power.profile_count }} 个
                    </n-text>
                  </n-space>
                </n-card>
              </n-grid-item>
            </n-grid>

            <n-card size="small" :bordered="false" title="自动提醒">
              <n-empty v-if="overview.alerts.length === 0" description="当前没有明显风险" size="small" />
              <n-space v-else vertical :size="10">
                <n-alert
                  v-for="alert in overview.alerts"
                  :key="`${alert.source}-${alert.title}-${alert.message}`"
                  :type="alertType(alert.severity)"
                  :title="alert.title"
                  class="section-alert"
                >
                  <n-space vertical :size="6">
                    <span>{{ alert.message }}</span>
                    <n-text depth="3" style="font-size: 12px">
                      建议：{{ alert.action }}
                    </n-text>
                  </n-space>
                </n-alert>
              </n-space>
            </n-card>
          </n-space>
        </template>

        <n-empty v-else description="暂无监控数据" size="small" />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { novelproMonitorApi, type NovelProMonitorOverview } from '@/api/novelproMonitor'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const loading = ref(false)
const syncingObsidian = ref(false)
const loadError = ref('')
const overview = ref<NovelProMonitorOverview | null>(null)
const message = useMessage()

const healthType = computed(() => alertType(overview.value?.health.status || 'info'))
const healthLabel = computed(() => {
  const status = overview.value?.health.status
  if (status === 'error') return '需要处理'
  if (status === 'warning') return '有提醒'
  if (status === 'ok') return '稳定'
  return '巡检'
})

async function loadOverview() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await novelproMonitorApi.getOverview(props.slug, props.currentChapter ?? undefined)
  } catch (error: any) {
    loadError.value = error?.message || '监控中心加载失败'
  } finally {
    loading.value = false
  }
}

async function copyVaultPath() {
  const path = overview.value?.obsidian.vault_path || ''
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    message.success('已复制 Obsidian Vault 路径')
  } catch {
    message.warning('复制失败，请手动选中路径复制')
  }
}

async function syncCurrentChapter() {
  if (!props.currentChapter) {
    message.warning('先选择具体章节再同步 Obsidian')
    return
  }
  syncingObsidian.value = true
  try {
    const result = await novelproMonitorApi.syncObsidianChapter(props.slug, props.currentChapter)
    if (result.synced) {
      message.success('当前章已同步到 Obsidian 主记忆')
      await loadOverview()
    } else {
      message.warning(result.reason || '当前章暂未生成可同步的章后记忆')
    }
  } catch {
    message.error('同步 Obsidian 失败，请先保存章节并确认章后管线已完成')
  } finally {
    syncingObsidian.value = false
  }
}

function alertType(value: string) {
  if (value === 'error') return 'error'
  if (value === 'warning') return 'warning'
  if (value === 'success' || value === 'ok') return 'success'
  return 'info'
}

function outlineType(value: string) {
  if (value === 'warning') return 'warning'
  if (value === 'watch') return 'info'
  if (value === 'aligned') return 'success'
  return 'default'
}

function outlineLabel(value: string) {
  if (value === 'warning') return '偏离'
  if (value === 'watch') return '观察'
  if (value === 'aligned') return '稳定'
  return '待判断'
}

watch(() => [props.slug, props.currentChapter], loadOverview)
onMounted(loadOverview)
</script>

<style scoped>
.monitor-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--aitext-panel-muted);
}

.panel-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--aitext-split-border);
  background:
    radial-gradient(circle at 12% 0%, rgba(34, 197, 94, 0.14), transparent 30%),
    var(--app-surface);
}

.header-main {
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  line-height: 1.3;
  color: var(--app-text-primary);
}

.panel-lead {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-muted);
}

.panel-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.section-alert {
  border-radius: 12px;
}

.mini-alert {
  border-radius: 10px;
  font-size: 12px;
}

.score-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(34, 197, 94, 0.22);
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.13), rgba(20, 184, 166, 0.06));
}

.score-card--warning {
  border-color: rgba(245, 158, 11, 0.28);
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.14), rgba(251, 191, 36, 0.05));
}

.score-card--error {
  border-color: rgba(239, 68, 68, 0.28);
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(248, 113, 113, 0.05));
}

.score-label {
  display: block;
  font-size: 12px;
  color: var(--app-text-muted);
}

.score-card strong {
  display: block;
  margin-top: 2px;
  font-size: 32px;
  line-height: 1;
  color: var(--app-text-primary);
}

.path-text {
  display: block;
  overflow-wrap: anywhere;
  font-size: 11px;
}

.config-text {
  display: block;
  font-size: 11px;
  line-height: 1.5;
}
</style>
