<template>
  <div class="continuity-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">连续性巡检</h3>
          <n-tag size="small" round :bordered="false">P2</n-tag>
        </div>
        <p class="panel-lead">
          聚合角色掉线、时间线覆盖、文风漂移与关系摘要，给作者一个写前/改后都能快速扫一眼的连续性面板。
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
            <n-space :size="8" wrap>
              <n-tag round size="small" type="info">
                当前章节 · 第{{ overview.chapter_number }}章
              </n-tag>
              <n-tag round size="small" :type="overview.voice_drift.drift_alert ? 'warning' : 'success'">
                文风{{ overview.voice_drift.drift_alert ? '告警' : '正常' }}
              </n-tag>
              <n-tag
                round
                size="small"
                :type="overview.timeline.current_chapter_has_event ? 'success' : 'warning'"
              >
                时间线{{ overview.timeline.current_chapter_has_event ? '已覆盖' : '待补锚点' }}
              </n-tag>
              <n-tag
                round
                size="small"
                :type="overview.character_dropouts.length ? 'warning' : 'success'"
              >
                掉线提醒 {{ overview.character_dropouts.length }}
              </n-tag>
            </n-space>

            <n-alert
              v-if="overview.voice_drift.drift_alert"
              type="warning"
              title="文风漂移告警"
              class="section-alert"
            >
              最近 {{ overview.voice_drift.alert_consecutive }} 章持续低于
              {{ formatPercent(overview.voice_drift.alert_threshold) }}，建议回看作者样本或做定向修文。
            </n-alert>

            <n-alert
              v-if="!overview.timeline.current_chapter_has_event && overview.chapter_number > 0"
              type="warning"
              title="当前章节缺少时间锚点"
              class="section-alert"
            >
              第{{ overview.chapter_number }}章还没有进入时间线注册表。若本章涉及明显的时间推进，建议补一个时间事件，避免后续时间线漂移。
            </n-alert>

            <n-card size="small" :bordered="false" title="角色掉线提醒">
              <n-empty
                v-if="overview.character_dropouts.length === 0"
                description="当前没有明显掉线的角色"
                size="small"
              />
              <n-space v-else vertical :size="10">
                <div
                  v-for="item in overview.character_dropouts"
                  :key="item.character_id"
                  class="dropout-row"
                >
                  <div class="dropout-main">
                    <n-space :size="8" align="center">
                      <n-text strong>{{ item.character_name }}</n-text>
                      <n-tag size="small" round :type="severityType(item.severity)">
                        {{ severityLabel(item.severity) }}
                      </n-tag>
                    </n-space>
                    <n-text depth="3" style="font-size: 12px">
                      上次出场：第{{ item.last_appearance_chapter }}章 · 已缺席 {{ item.chapters_absent }} 章 · 总出场 {{ item.appearance_count }} 次
                    </n-text>
                  </div>
                </div>
              </n-space>
            </n-card>

            <n-grid :cols="2" :x-gap="12">
              <n-grid-item>
                <n-card size="small" :bordered="false" title="时间线覆盖">
                  <n-space vertical :size="8">
                    <n-text depth="3" style="font-size: 12px">
                      已登记 {{ overview.timeline.total_events }} 条事件。
                    </n-text>
                    <n-empty
                      v-if="overview.timeline.recent_events.length === 0"
                      description="暂无时间线事件"
                      size="small"
                    />
                    <n-timeline v-else size="small">
                      <n-timeline-item
                        v-for="event in overview.timeline.recent_events"
                        :key="event.id"
                        type="info"
                        :title="event.event"
                        :time="`第${event.chapter_number}章 · ${event.timestamp}`"
                      >
                        <n-text depth="3" style="font-size: 12px">
                          {{ timestampTypeLabel(event.timestamp_type) }}
                        </n-text>
                      </n-timeline-item>
                    </n-timeline>
                  </n-space>
                </n-card>
              </n-grid-item>

              <n-grid-item>
                <n-card size="small" :bordered="false" title="关系聚焦">
                  <n-empty
                    v-if="overview.relationship_spotlights.length === 0"
                    description="Bible 中暂无可用关系摘要"
                    size="small"
                  />
                  <n-space v-else vertical :size="8">
                    <div
                      v-for="(item, index) in overview.relationship_spotlights"
                      :key="`${item.source_character}-${item.target_character}-${index}`"
                      class="relationship-row"
                    >
                      <n-text>
                        <strong>{{ item.source_character }}</strong>
                        <span v-if="item.target_character"> → {{ item.target_character }}</span>
                        ：{{ item.relation }}
                      </n-text>
                      <n-text v-if="item.description" depth="3" style="font-size: 12px">
                        {{ item.description }}
                      </n-text>
                    </div>
                  </n-space>
                </n-card>
              </n-grid-item>
            </n-grid>

            <n-card size="small" :bordered="false" title="文风状态">
              <n-space justify="space-between" align="center" style="width: 100%">
                <n-text depth="3" style="font-size: 12px">
                  已评分章节：{{ overview.voice_drift.scored_chapters }}
                </n-text>
                <n-tag round size="small" :type="overview.voice_drift.drift_alert ? 'warning' : 'success'">
                  {{
                    overview.voice_drift.latest_similarity_score == null
                      ? '样本不足'
                      : `最新相似度 ${formatPercent(overview.voice_drift.latest_similarity_score)}`
                  }}
                </n-tag>
              </n-space>
            </n-card>
          </n-space>
        </template>

        <n-empty v-else description="暂无连续性数据" size="small" />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { continuityApi, type ContinuityOverviewResponse } from '@/api/continuity'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const loading = ref(false)
const loadError = ref('')
const overview = ref<ContinuityOverviewResponse | null>(null)

function formatPercent(value: number | null) {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}

function severityLabel(value: string) {
  if (value === 'high') return '高风险'
  if (value === 'medium') return '中风险'
  return '低风险'
}

function severityType(value: string) {
  if (value === 'high') return 'error'
  if (value === 'medium') return 'warning'
  return 'info'
}

function timestampTypeLabel(value: string) {
  if (value === 'absolute') return '绝对时间'
  if (value === 'relative') return '相对时间'
  return '模糊时间'
}

async function loadOverview() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await continuityApi.getOverview(props.slug, props.currentChapter)
  } catch {
    overview.value = null
    loadError.value = '加载连续性总览失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.slug, props.currentChapter] as const,
  () => {
    void loadOverview()
  },
)

onMounted(() => {
  void loadOverview()
})
</script>

<style scoped>
.continuity-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--aitext-panel-muted);
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.header-main {
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-1);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-3);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.section-alert {
  margin: 0;
}

.dropout-row,
.relationship-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dropout-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
