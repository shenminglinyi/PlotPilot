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
              <n-tag
                round
                size="small"
                :type="overview.relationship_tracking.active_signals.length ? 'warning' : 'success'"
              >
                关系信号 {{ overview.relationship_tracking.active_signals.length }}
              </n-tag>
              <n-tag
                round
                size="small"
                :type="outlineTagType(overview.outline_deviation.status)"
              >
                大纲{{ outlineStatusLabel(overview.outline_deviation.status) }}
              </n-tag>
            </n-space>

            <n-alert
              v-if="overview.voice_drift.drift_alert"
              type="warning"
              title="文风漂移告警"
              class="section-alert"
            >
              <n-space vertical :size="8" align="start">
                <span>
                  最近 {{ overview.voice_drift.alert_consecutive }} 章持续低于
                  {{ formatPercent(overview.voice_drift.alert_threshold) }}，建议回看作者样本或做定向修文。
                </span>
                <n-button size="tiny" tertiary @click="queueVoiceRewrite">
                  建候选改稿
                </n-button>
              </n-space>
            </n-alert>

            <n-alert
              v-if="!overview.timeline.current_chapter_has_event && overview.chapter_number > 0"
              type="warning"
              title="当前章节缺少时间锚点"
              class="section-alert"
            >
              第{{ overview.chapter_number }}章还没有进入时间线注册表。若本章涉及明显的时间推进，建议补一个时间事件，避免后续时间线漂移。
            </n-alert>

            <n-alert
              v-if="overview.outline_deviation.status === 'warning'"
              type="warning"
              title="大纲偏离提醒"
              class="section-alert"
            >
              <n-space vertical :size="8" align="start">
                <span>
                  <span v-if="overview.outline_deviation.warning_reasons.length">
                    {{ overview.outline_deviation.warning_reasons.join('；') }}。
                  </span>
                  建议在继续写下一章前回看本章大纲与审阅备注。
                </span>
                <n-button size="tiny" tertiary @click="queueOutlineRewrite">
                  建候选改稿
                </n-button>
              </n-space>
            </n-alert>

            <n-alert
              v-else-if="overview.outline_deviation.status === 'watch'"
              type="info"
              title="大纲覆盖不完整"
              class="section-alert"
            >
              <n-space vertical :size="8" align="start">
                <span>
                  {{ overview.outline_deviation.warning_reasons.join('；') || '当前章节只覆盖了部分大纲节点。' }}
                </span>
                <n-button size="tiny" tertiary @click="queueOutlineRewrite">
                  建候选改稿
                </n-button>
              </n-space>
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
                    <n-space v-if="item.tracked_relationship_count > 0" :size="6" wrap>
                      <n-tag size="small" round :type="dropoutScopeType(item.dropout_scope)">
                        关联关系 {{ item.tracked_relationship_count }}
                      </n-tag>
                      <n-tag
                        v-if="item.stale_relationship_count > 0"
                        size="small"
                        round
                        type="warning"
                      >
                        沉默关系 {{ item.stale_relationship_count }}
                      </n-tag>
                    </n-space>
                    <n-text
                      v-if="item.stale_relationship_targets.length > 0"
                      depth="3"
                      style="font-size: 12px"
                    >
                      受影响关系线：{{ item.stale_relationship_targets.join('、') }}
                    </n-text>
                    <n-space :size="8">
                      <n-button
                        size="tiny"
                        tertiary
                        @click="queueCharacterRewrite(item.character_name, `补写${item.character_name}回到主线的场景，并修复掉线提醒。`, 'continuity-dropout')"
                      >
                        建候选改稿
                      </n-button>
                      <n-button
                        size="tiny"
                        tertiary
                        @click="openVoiceLock(item.character_id, item.character_name)"
                      >
                        去口吻锁定
                      </n-button>
                      <n-button
                        size="tiny"
                        tertiary
                        @click="openSandbox(item.character_id, item.character_name, `请写一段${item.character_name}重新回到主线的对白场景。`)"
                      >
                        去对话沙盒
                      </n-button>
                    </n-space>
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
                <n-card size="small" :bordered="false" title="关系变化追踪">
                  <n-space vertical :size="10">
                    <n-text depth="3" style="font-size: 12px">
                      已跟踪 {{ overview.relationship_tracking.tracked_pairs }} 组 Bible 关系。
                    </n-text>
                    <n-tag size="small" round :type="sourceTagType(overview.relationship_tracking.source)">
                      {{ sourceLabel(overview.relationship_tracking.source) }}
                    </n-tag>

                    <div class="structured-form">
                      <n-text strong style="font-size: 13px">记录关系事件</n-text>
                      <n-space vertical :size="8" style="margin-top: 8px">
                        <n-grid :cols="2" :x-gap="8" :y-gap="8">
                          <n-grid-item>
                            <n-input
                              v-model:value="relationshipEventForm.source_character"
                              size="small"
                              placeholder="角色 A"
                            />
                          </n-grid-item>
                          <n-grid-item>
                            <n-input
                              v-model:value="relationshipEventForm.target_character"
                              size="small"
                              placeholder="角色 B"
                            />
                          </n-grid-item>
                          <n-grid-item>
                            <n-input
                              v-model:value="relationshipEventForm.relation"
                              size="small"
                              placeholder="关系，如盟友/师徒"
                            />
                          </n-grid-item>
                          <n-grid-item>
                            <n-select
                              v-model:value="relationshipEventForm.severity"
                              size="small"
                              :options="relationshipSeverityOptions"
                            />
                          </n-grid-item>
                        </n-grid>
                        <n-input
                          v-model:value="relationshipEventForm.event_type"
                          size="small"
                          placeholder="变化类型，如 trust_break / reconcile / alliance"
                        />
                        <n-input
                          v-model:value="relationshipEventForm.description"
                          type="textarea"
                          size="small"
                          :autosize="{ minRows: 2, maxRows: 3 }"
                          placeholder="这条关系发生了什么变化"
                        />
                        <n-input
                          v-model:value="relationshipEventForm.evidence"
                          size="small"
                          placeholder="证据摘录，可填关键句"
                        />
                        <n-button
                          size="tiny"
                          type="primary"
                          secondary
                          :loading="savingRelationshipEvent"
                          @click="recordRelationshipEvent"
                        >
                          保存关系事件
                        </n-button>
                      </n-space>
                    </div>

                    <div>
                      <n-text strong style="font-size: 13px">本章活跃信号</n-text>
                      <n-empty
                        v-if="overview.relationship_tracking.active_signals.length === 0"
                        description="本章没有明显的关系变化信号"
                        size="small"
                        style="margin-top: 8px"
                      />
                      <n-space v-else vertical :size="8" style="margin-top: 8px">
                        <div
                          v-for="(item, index) in overview.relationship_tracking.active_signals"
                          :key="`${item.source_character}-${item.target_character}-${index}`"
                          class="relationship-row"
                        >
                          <n-space :size="8" align="center">
                            <n-text>
                              <strong>{{ item.source_character }}</strong>
                              <span v-if="item.target_character"> → {{ item.target_character }}</span>
                              ：{{ item.relation }}
                            </n-text>
                            <n-tag size="small" round :type="relationshipSeverityType(item.severity)">
                              {{ item.change_signal }}
                            </n-tag>
                            <n-tag v-if="item.source === 'structured'" size="small" round type="success">
                              结构化
                            </n-tag>
                          </n-space>
                          <n-text depth="3" style="font-size: 12px">
                            最近同章：第{{ item.last_joint_chapter || overview.chapter_number }}章 · 共现 {{ item.joint_appearance_count }} 次
                          </n-text>
                          <n-text v-if="item.signal_excerpt" depth="3" style="font-size: 12px">
                            {{ item.signal_excerpt }}
                          </n-text>
                          <n-space :size="8">
                            <n-button
                              size="tiny"
                              tertiary
                              @click="queueCharacterRewrite(item.source_character, `强化${item.source_character}${item.target_character ? `与${item.target_character}` : ''}的关系推进，重点处理“${item.change_signal}”。`, 'continuity-relationship')"
                            >
                              建候选改稿
                            </n-button>
                            <n-button
                              size="tiny"
                              tertiary
                              @click="openVoiceLock(lookupCharacterId(item.source_character), item.source_character)"
                            >
                              去口吻锁定
                            </n-button>
                            <n-button
                              size="tiny"
                              tertiary
                              @click="openSandbox(lookupCharacterId(item.source_character), item.source_character, buildRelationshipScenePrompt(item.source_character, item.target_character, item.change_signal))"
                            >
                              去对话沙盒
                            </n-button>
                            <n-button
                              size="tiny"
                              tertiary
                              @click="fillRelationshipEventFromSignal(item)"
                            >
                              作为事件编辑
                            </n-button>
                          </n-space>
                        </div>
                      </n-space>
                    </div>

                    <div>
                      <n-text strong style="font-size: 13px">潜在掉线关系</n-text>
                      <n-empty
                        v-if="overview.relationship_tracking.stale_pairs.length === 0"
                        description="当前没有明显掉线的关系线"
                        size="small"
                        style="margin-top: 8px"
                      />
                      <n-space v-else vertical :size="8" style="margin-top: 8px">
                        <div
                          v-for="(item, index) in overview.relationship_tracking.stale_pairs"
                          :key="`${item.source_character}-${item.target_character}-stale-${index}`"
                          class="relationship-row"
                        >
                          <n-space :size="8" align="center">
                            <n-text>
                              <strong>{{ item.source_character }}</strong>
                              <span v-if="item.target_character"> → {{ item.target_character }}</span>
                              ：{{ item.relation }}
                            </n-text>
                            <n-tag size="small" round :type="relationshipSeverityType(item.severity)">
                              已沉默 {{ item.chapters_since_joint }} 章
                            </n-tag>
                          </n-space>
                          <n-text depth="3" style="font-size: 12px">
                            上次同章推进：第{{ item.last_joint_chapter }}章
                          </n-text>
                          <n-space :size="8">
                            <n-button
                              size="tiny"
                              tertiary
                              @click="queueCharacterRewrite(item.source_character, `修复${item.source_character}${item.target_character ? `与${item.target_character}` : ''}的沉默关系线，并给出新的互动推进。`, 'continuity-relationship')"
                            >
                              建候选改稿
                            </n-button>
                            <n-button
                              size="tiny"
                              tertiary
                              @click="openVoiceLock(lookupCharacterId(item.source_character), item.source_character)"
                            >
                              去口吻锁定
                            </n-button>
                            <n-button
                              size="tiny"
                              tertiary
                              @click="openSandbox(lookupCharacterId(item.source_character), item.source_character, buildRelationshipScenePrompt(item.source_character, item.target_character, `修复与${item.target_character}的掉线关系`))"
                            >
                              去对话沙盒
                            </n-button>
                          </n-space>
                        </div>
                      </n-space>
                    </div>

                    <div v-if="overview.relationship_spotlights.length > 0">
                      <n-text strong style="font-size: 13px">Bible 静态关系底稿</n-text>
                      <n-space vertical :size="8" style="margin-top: 8px">
                        <div
                          v-for="(item, index) in overview.relationship_spotlights"
                          :key="`${item.source_character}-${item.target_character}-spotlight-${index}`"
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
                    </div>
                  </n-space>
                </n-card>
              </n-grid-item>
            </n-grid>

            <n-card size="small" :bordered="false" title="大纲偏离提醒">
              <n-space vertical :size="10">
                <n-space :size="8" align="center">
                  <n-tag round size="small" :type="outlineTagType(overview.outline_deviation.status)">
                    {{ outlineStatusLabel(overview.outline_deviation.status) }}
                  </n-tag>
                  <n-tag size="small" round :type="sourceTagType(overview.outline_deviation.source)">
                    {{ sourceLabel(overview.outline_deviation.source) }}
                  </n-tag>
                  <n-text depth="3" style="font-size: 12px">
                    {{
                      overview.outline_deviation.overlap_score == null
                        ? '暂无可比对数据'
                        : `重合度 ${formatPercent(overview.outline_deviation.overlap_score)}`
                    }}
                  </n-text>
                </n-space>

                <n-empty
                  v-if="overview.outline_deviation.status === 'unavailable'"
                  description="当前章节暂时无法做大纲比对"
                  size="small"
                />
                <template v-else>
                  <div class="outline-row">
                    <n-text strong>大纲摘录</n-text>
                    <n-text depth="3" style="font-size: 12px">
                      {{ overview.outline_deviation.outline_excerpt || '暂无' }}
                    </n-text>
                  </div>
                  <div class="outline-row">
                    <n-text strong>正文/摘要摘录</n-text>
                    <n-text depth="3" style="font-size: 12px">
                      {{ overview.outline_deviation.summary_excerpt || '暂无' }}
                    </n-text>
                  </div>
                  <div class="outline-row">
                    <n-text strong>提醒原因</n-text>
                    <n-empty
                      v-if="overview.outline_deviation.warning_reasons.length === 0"
                      description="当前没有明显偏离信号"
                      size="small"
                    />
                    <n-space v-else vertical :size="6">
                      <n-text
                        v-for="(reason, index) in overview.outline_deviation.warning_reasons"
                        :key="`${reason}-${index}`"
                        depth="3"
                        style="font-size: 12px"
                      >
                        {{ index + 1 }}. {{ reason }}
                      </n-text>
                    </n-space>
                  </div>
                  <div
                    v-if="overview.outline_deviation.outline_nodes.length > 0"
                    class="outline-row"
                  >
                    <n-text strong>结构化大纲节点</n-text>
                    <n-space vertical :size="8">
                      <div
                        v-for="node in overview.outline_deviation.outline_nodes"
                        :key="node.node_key"
                        class="outline-node-row"
                      >
                        <n-space :size="8" align="center">
                          <n-tag size="small" round :type="outlineNodeStatusType(node.status)">
                            {{ outlineNodeStatusLabel(node.status) }}
                          </n-tag>
                          <n-text style="font-size: 12px">
                            {{ node.outline_text }}
                          </n-text>
                        </n-space>
                        <n-text v-if="node.note || node.evidence" depth="3" style="font-size: 12px">
                          {{ node.note || node.evidence }}
                        </n-text>
                        <n-button size="tiny" tertiary @click="fillOutlineNodeStatus(node)">
                          编辑状态
                        </n-button>
                      </div>
                    </n-space>
                  </div>
                  <div class="structured-form">
                    <n-text strong style="font-size: 13px">更新大纲节点状态</n-text>
                    <n-space vertical :size="8" style="margin-top: 8px">
                      <n-grid :cols="2" :x-gap="8" :y-gap="8">
                        <n-grid-item>
                          <n-input
                            v-model:value="outlineNodeForm.node_key"
                            size="small"
                            placeholder="节点 key，如 node-1"
                          />
                        </n-grid-item>
                        <n-grid-item>
                          <n-select
                            v-model:value="outlineNodeForm.status"
                            size="small"
                            :options="outlineStatusOptions"
                          />
                        </n-grid-item>
                      </n-grid>
                      <n-input
                        v-model:value="outlineNodeForm.outline_text"
                        size="small"
                        placeholder="大纲节点内容"
                      />
                      <n-input
                        v-model:value="outlineNodeForm.note"
                        size="small"
                        placeholder="处理备注，如已改写/缺失原因"
                      />
                      <n-input
                        v-model:value="outlineNodeForm.evidence"
                        size="small"
                        placeholder="正文证据摘录"
                      />
                      <n-button
                        size="tiny"
                        type="primary"
                        secondary
                        :loading="savingOutlineNode"
                        @click="upsertOutlineNodeStatus"
                      >
                        保存大纲节点状态
                      </n-button>
                    </n-space>
                  </div>
                </template>
              </n-space>
            </n-card>

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
import { computed, ref, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import {
  continuityApi,
  type ContinuityOverviewResponse,
  type OutlineNodeStatusItem,
  type RelationshipSignalItem,
} from '@/api/continuity'
import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const contextStore = useWorkbenchContextStore()
const loading = ref(false)
const loadError = ref('')
const overview = ref<ContinuityOverviewResponse | null>(null)
const characters = ref<CharacterDTO[]>([])
const savingRelationshipEvent = ref(false)
const savingOutlineNode = ref(false)
const relationshipEventForm = ref({
  source_character: '',
  target_character: '',
  relation: '关系',
  event_type: 'update',
  description: '',
  evidence: '',
  severity: 'info',
})
const outlineNodeForm = ref({
  node_key: '',
  outline_text: '',
  status: 'completed',
  note: '',
  evidence: '',
})

const relationshipSeverityOptions = [
  { label: '信息', value: 'info' },
  { label: '升温/修复', value: 'success' },
  { label: '风险', value: 'warning' },
  { label: '严重', value: 'error' },
]

const outlineStatusOptions = [
  { label: '已完成', value: 'completed' },
  { label: '自动命中', value: 'matched' },
  { label: '待确认', value: 'pending' },
  { label: '已变更', value: 'changed' },
  { label: '缺失', value: 'missing' },
  { label: '阻塞', value: 'blocked' },
]

const characterIdByName = computed(() => {
  const entries = characters.value
    .filter(item => item.name && item.id)
    .map(item => [item.name, item.id] as const)
  return new Map(entries)
})

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

function relationshipSeverityType(value: string) {
  if (value === 'error') return 'error'
  if (value === 'warning') return 'warning'
  if (value === 'success') return 'success'
  return 'info'
}

function sourceLabel(value: string) {
  if (value === 'structured') return '结构化记录'
  return '启发式巡检'
}

function sourceTagType(value: string) {
  if (value === 'structured') return 'success'
  return 'default'
}

function outlineNodeStatusLabel(value: string) {
  if (value === 'completed') return '已完成'
  if (value === 'matched') return '自动命中'
  if (value === 'changed') return '已变更'
  if (value === 'missing') return '缺失'
  if (value === 'blocked') return '阻塞'
  return '待确认'
}

function outlineNodeStatusType(value: string) {
  if (value === 'completed' || value === 'matched') return 'success'
  if (value === 'changed' || value === 'blocked') return 'warning'
  if (value === 'missing') return 'error'
  return 'default'
}

function dropoutScopeType(value: string) {
  if (value === 'linked') return 'warning'
  if (value === 'tracked') return 'info'
  return 'default'
}

function timestampTypeLabel(value: string) {
  if (value === 'absolute') return '绝对时间'
  if (value === 'relative') return '相对时间'
  return '模糊时间'
}

function outlineStatusLabel(value: string) {
  if (value === 'warning') return '偏离告警'
  if (value === 'watch') return '需留意'
  if (value === 'aligned') return '基本对齐'
  return '暂不可用'
}

function outlineTagType(value: string) {
  if (value === 'warning') return 'warning'
  if (value === 'watch') return 'info'
  if (value === 'aligned') return 'success'
  return 'default'
}

function buildRelationshipScenePrompt(source: string, target: string, cue: string) {
  if (target) {
    return `请写一段${source}与${target}相关的对白场景，重点处理“${cue}”。`
  }
  return `请写一段${source}的对白场景，重点处理“${cue}”。`
}

function openVoiceLock(characterId: string | null | undefined, characterName: string) {
  if (!characterId) {
    message.warning(`当前还无法定位角色「${characterName}」的口吻页签`)
    return
  }
  contextStore.openVoiceLockForCharacter({
    slug: props.slug,
    characterId,
  })
  message.success(`已切到「${characterName}」的口吻锁定`)
}

function openSandbox(characterId: string | null | undefined, characterName: string, scenePrompt: string) {
  if (!characterId) {
    message.warning(`当前还无法定位角色「${characterName}」去对话沙盒`)
    return
  }
  contextStore.openSandboxWithDraft({
    slug: props.slug,
    characterId,
    scenePrompt,
  })
  message.success(`已带着「${characterName}」上下文切到对话沙盒`)
}

function queueCandidateRewrite(source: string, rationale: string, metadata?: Record<string, unknown>) {
  if (!overview.value) {
    message.warning('当前还没有可用的连续性数据')
    return
  }
  contextStore.openCandidateRewriteSeed({
    slug: props.slug,
    chapterNumber: overview.value.chapter_number,
    source,
    title: `第${overview.value.chapter_number}章 候选改稿`,
    rationale,
    metadata,
  })
  message.success('已把连续性提醒转成候选改稿任务')
}

function queueVoiceRewrite() {
  if (!overview.value) return
  queueCandidateRewrite(
    'continuity-voice',
    `根据连续性巡检修正文风漂移：最近 ${overview.value.voice_drift.alert_consecutive} 章相似度连续偏低，优先统一措辞、句式和角色表达。`,
    {
      rewrite_focus: 'voice-drift',
      alert_consecutive: overview.value.voice_drift.alert_consecutive,
      alert_threshold: overview.value.voice_drift.alert_threshold,
    },
  )
}

function queueOutlineRewrite() {
  if (!overview.value) return
  const reasons = overview.value.outline_deviation.warning_reasons
  queueCandidateRewrite(
    'continuity-outline',
    `根据连续性巡检修复本章与大纲的偏离。${reasons.length ? `重点问题：${reasons.join('；')}。` : ''}请尽量保留现有亮点，只补齐主线、大纲节点与叙事重点。`,
    {
      rewrite_focus: 'outline-deviation',
      outline_status: overview.value.outline_deviation.status,
      warning_reasons: reasons,
    },
  )
}

function queueCharacterRewrite(characterName: string, rationale: string, source: string) {
  queueCandidateRewrite(source, rationale, {
    rewrite_focus: 'character-continuity',
    character_name: characterName,
  })
}

function fillRelationshipEventFromSignal(item: RelationshipSignalItem) {
  relationshipEventForm.value = {
    source_character: item.source_character,
    target_character: item.target_character,
    relation: item.relation || '关系',
    event_type: item.change_signal || 'update',
    description: item.description || '',
    evidence: item.signal_excerpt || '',
    severity: item.severity || 'info',
  }
}

function fillOutlineNodeStatus(item: OutlineNodeStatusItem) {
  outlineNodeForm.value = {
    node_key: item.node_key,
    outline_text: item.outline_text,
    status: item.status || 'pending',
    note: item.note || '',
    evidence: item.evidence || '',
  }
}

async function recordRelationshipEvent() {
  if (!overview.value) return
  if (!relationshipEventForm.value.source_character.trim()) {
    message.warning('请先填写关系事件的主角色')
    return
  }
  savingRelationshipEvent.value = true
  try {
    await continuityApi.recordRelationshipEvent(props.slug, {
      chapter_number: overview.value.chapter_number,
      ...relationshipEventForm.value,
    })
    message.success('关系事件已记录，会优先用于连续性巡检')
    relationshipEventForm.value.description = ''
    relationshipEventForm.value.evidence = ''
    await loadOverview()
  } catch {
    message.error('保存关系事件失败，请稍后重试')
  } finally {
    savingRelationshipEvent.value = false
  }
}

async function upsertOutlineNodeStatus() {
  if (!overview.value) return
  if (!outlineNodeForm.value.node_key.trim() || !outlineNodeForm.value.outline_text.trim()) {
    message.warning('请先填写节点 key 和大纲节点内容')
    return
  }
  savingOutlineNode.value = true
  try {
    await continuityApi.upsertOutlineNodeStatus(props.slug, {
      chapter_number: overview.value.chapter_number,
      ...outlineNodeForm.value,
    })
    message.success('大纲节点状态已更新')
    await loadOverview()
  } catch {
    message.error('保存大纲节点状态失败，请稍后重试')
  } finally {
    savingOutlineNode.value = false
  }
}

function lookupCharacterId(name: string) {
  return characterIdByName.value.get(name) || null
}

async function loadCharacters() {
  if (!props.slug) return
  try {
    characters.value = await bibleApi.listCharacters(props.slug)
  } catch {
    characters.value = []
  }
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
    void loadCharacters()
    void loadOverview()
  },
)

onMounted(() => {
  void loadCharacters()
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

.structured-form,
.outline-node-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 10px;
  background: var(--app-surface);
}

.dropout-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.outline-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
