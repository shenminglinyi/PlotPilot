<template>
  <div class="work-area">
    <header class="work-header">
      <div class="work-title-wrap">
        <h2 class="work-title">{{ bookTitle || slug }}</h2>
        <n-text depth="3" class="work-sub">{{ slug }}</n-text>
      </div>
      <div class="work-mode-switch" role="group" aria-label="创作模式">
        <n-switch
          v-model:value="workMode"
          checked-value="managed"
          unchecked-value="assisted"
          size="large"
        >
          <template #unchecked>辅助撰稿</template>
          <template #checked>托管撰稿</template>
        </n-switch>
      </div>
    </header>

    <div class="work-body">
      <!--
        辅助撰稿与托管撰稿须同时保留在 DOM（v-show，勿用 v-if）：
        切到辅助撰稿时若卸载 AutopilotPanel，其 onUnmounted 会 stopChapterStream()，
        章节 SSE 断开会导致全托管写作异常/重连后重复写。
      -->
      <div v-show="workMode === 'assisted'" class="assisted-stack">
        <n-alert
          v-if="isAssistedReadOnly"
          type="warning"
          :show-icon="true"
          class="assisted-readonly-banner"
        >
          <strong>全托管运行中</strong>：本侧仅只读；不能保存、改稿、快速生成或改章节元素。
          请切换到「<strong>托管撰稿</strong>」看驾驶舱与监控，或停止托管后再编辑。
        </n-alert>
        <ChapterWorkbenchShell
          class="chapter-desk-shell"
          :stacked="desk.stacked"
          v-model:rail-expanded="desk.railExpanded"
          :deep-drawer-open="desk.deepDrawerOpen"
          :deep-drawer-title="desk.deepDrawerTitle"
          rail-drawer-title="本章任务与状态"
          @update:deep-drawer-open="onDeepDrawerOpenUpdate"
        >
          <template #manuscript-toolbar>
            <div class="desk-toolbar">
              <n-space align="center" :size="8" wrap>
                <template v-if="signalStrip">
                  <n-tag size="small" round type="info">张力 {{ signalStrip.tension }}/10</n-tag>
                  <n-tag v-if="!signalStrip.sync" size="small" round type="warning">叙事未同步</n-tag>
                </template>
                <n-text v-else depth="3" style="font-size: 12px">本章信号在侧栏与生成完成后更新</n-text>
              </n-space>
              <n-space align="center" :size="6" wrap justify="end">
                <n-button size="tiny" secondary @click="desk.toggleRail()">
                  {{ desk.railExpanded ? '收起侧栏' : '任务与状态' }}
                </n-button>
                <n-dropdown
                  trigger="click"
                  :options="deepDrawerDropdownOptions"
                  @select="onDeepDrawerDropdownSelect"
                >
                  <n-button size="tiny" quaternary>深度工具 ▾</n-button>
                </n-dropdown>
              </n-space>
            </div>
          </template>

          <template #primary>
            <div class="work-main">
              <div v-if="currentChapter" class="chapter-editor">
                <div class="editor-header">
                  <div class="editor-title">
                    <h3>{{ currentChapter.title || `第${currentChapter.number}章` }}</h3>
                    <n-tag size="small" :type="currentChapter.word_count > 0 ? 'success' : 'default'" round>
                      {{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}
                    </n-tag>
                    <n-tag v-if="isAutopilotRunning && streamingChapterNumber === currentChapter.number" size="small" type="info" round>
                      生成中...
                    </n-tag>
                  </div>
                  <div v-if="autopilotStatus?.current_act_title" class="act-info-header">
                    <span class="act-info-title">第 {{ (autopilotStatus.current_act || 0) + 1 }} 幕 · {{ autopilotStatus.current_act_title }}</span>
                    <span v-if="autopilotStatus.current_act_description" class="act-info-desc">{{ autopilotStatus.current_act_description }}</span>
                  </div>
                  <n-space :size="8">
                    <n-button size="small" @click="handleReload" :disabled="loading">重新加载</n-button>
                    <n-button
                      size="small"
                      type="primary"
                      @click="handleSave"
                      :disabled="!hasChanges || isAssistedReadOnly"
                      :loading="saving"
                    >
                      保存
                    </n-button>
                  </n-space>
                </div>

                <div class="editor-body">
                  <div
                    class="editor-input-wrapper"
                    :class="{ 'is-streaming': isAutopilotRunning && streamingChapterNumber === currentChapter.number && streamingContent }"
                  >
                    <n-input
                      v-model:value="editorDisplayContent"
                      type="textarea"
                      placeholder="章节内容..."
                      :autosize="false"
                      :readonly="isAssistedReadOnly || (isAutopilotRunning && streamingChapterNumber === currentChapter.number)"
                      @update:value="handleContentChange"
                    />
                    <div
                      v-if="isAutopilotRunning && streamingChapterNumber === currentChapter.number && streamingContent"
                      class="streaming-cursor-overlay"
                    >
                      <span class="streaming-cursor">▋</span>
                      <span class="streaming-badge">生成中</span>
                    </div>
                  </div>
                </div>

                <div class="editor-footer">
                  <n-space :size="8" align="center" justify="space-between" style="width: 100%">
                    <n-text depth="3" class="editor-wordcount-line">
                      <template
                        v-if="
                          isAutopilotRunning &&
                          streamingChapterNumber === currentChapter?.number &&
                          streamingContent &&
                          streamingWordCountHint
                        "
                      >
                        <span :class="{ 'streaming-word-count': true }">{{ streamingWordCountHint }}</span>
                        <n-tooltip trigger="hover" placement="top">
                          <template #trigger>
                            <span class="wordcount-help">?</span>
                          </template>
                          流式阶段模型常会写出超过单章目标的缓冲，系统在每节拍末会收束；落稿字数会贴近你在书目里设的「每章目标字数」。
                        </n-tooltip>
                        <span class="streaming-indicator">生成中</span>
                      </template>
                      <template v-else>
                        字数:
                        <span :class="{ 'streaming-word-count': isAutopilotRunning && streamingChapterNumber === currentChapter?.number && streamingContent }">
                          {{ wordCount }}
                        </span>
                        <span v-if="isAutopilotRunning && streamingChapterNumber === currentChapter?.number && streamingContent" class="streaming-indicator">生成中▋</span>
                      </template>
                    </n-text>
                    <n-space :size="8">
                      <n-tooltip trigger="hover" :disabled="!isAutopilotRunning && !isAssistedReadOnly">
                        <template #trigger>
                          <n-button
                            size="small"
                            secondary
                            @click="handleGenerateChapter"
                            :loading="generating"
                            :disabled="isAutopilotRunning || isAssistedReadOnly"
                          >
                            ⚡ 快速生成
                          </n-button>
                        </template>
                        <span>{{ isAssistedReadOnly ? '托管运行中不可手动生成' : 'Autopilot 运行时禁用手动生成' }}</span>
                      </n-tooltip>
                      <n-button size="small" secondary :disabled="isAssistedReadOnly" @click="openTensionModal" title="诊断当前章节张力缺口">
                        🔍 张力诊断
                      </n-button>
                    </n-space>
                  </n-space>
                </div>
              </div>

              <n-empty v-else description="请从左侧选择章节" class="work-empty" />
            </div>
          </template>

          <template #rail>
            <div class="rail-column">
            <div class="rail-head">
              <n-text strong style="font-size: 13px">本章任务与状态</n-text>
              <n-button v-if="!desk.stacked" quaternary circle size="small" @click="desk.toggleRail()" title="收起侧栏">
                <template #icon>
                  <ChevronForwardOutline />
                </template>
              </n-button>
            </div>
            <n-scrollbar class="rail-scroll">
              <div class="rail-scroll-pad">
                <ChapterContentPanel
                  :slug="slug"
                  :current-chapter-number="currentChapter?.number ?? null"
                  :read-only="isAssistedReadOnly"
                  :autopilot-chapter-review="autopilotChapterReview"
                />
                <ChapterStatusPanel
                  :slug="slug"
                  :chapter="currentChapter"
                  :read-only="isAssistedReadOnly"
                  :last-workflow-result="lastWorkflowResult"
                  :qc-chapter-number="lastQcChapterNumber"
                  :autopilot-chapter-review="autopilotChapterReview"
                  @clear-qc="clearWorkflowQc"
                  @go-editor="desk.focusManuscript()"
                />
              </div>
            </n-scrollbar>
            </div>
          </template>

          <template #rail-collapsed-actions>
            <n-tooltip v-for="id in CHAPTER_DESK_DEEP_ORDER" :key="id" placement="left" trigger="hover">
              <template #trigger>
                <n-button quaternary size="small" class="rail-icon-btn" @click="desk.openDeepDrawer(id)">
                  <template #icon>
                    <component :is="deepSurfaceIcon(id)" />
                  </template>
                </n-button>
              </template>
              {{ desk.deepMeta[id].label }}
            </n-tooltip>
          </template>

          <template #deep-drawer>
            <div class="elements-tab-wrap deep-drawer-body">
              <ChapterElementPanel
                v-if="desk.deepDrawerSurface === 'elements'"
                :slug="slug"
                :current-chapter-number="currentChapter?.number ?? null"
                :read-only="isAssistedReadOnly"
                :last-workflow-result="lastWorkflowResult"
                :qc-chapter-number="lastQcChapterNumber"
                :autopilot-chapter-review="autopilotChapterReview"
              />
              <QualityGuardrailPanel
                v-else-if="desk.deepDrawerSurface === 'guardrail'"
                :slug="slug"
                :chapter="currentChapter"
                :read-only="isAssistedReadOnly"
              />
              <TraceRecordPanel v-else-if="desk.deepDrawerSurface === 'trace'" :slug="slug" />
            </div>
          </template>
        </ChapterWorkbenchShell>
      </div>

      <!-- 托管撰稿：驾驶舱 + 监控大盘（点击左侧章节会显示辅助撰稿面板，托管组件仍挂载以保持 SSE） -->
      <div v-show="workMode === 'managed'" class="managed-stack">
        <n-alert type="success" :show-icon="true" class="managed-daemon-hint">
          <strong>全托管模式</strong>：后端已自动启动守护进程线程，点击「启动全托管」即可开始自动写作。
          系统将自动进行宏观规划、幕级规划、章节撰写和审计。
        </n-alert>
        <div class="autopilot-container managed-autopilot">
          <AutopilotPanel
            :novel-id="slug"
            @status-change="handleAutopilotStatusChange"
            @chapter-content-update="handleChapterContentUpdate"
            @chapter-chunk="handleChapterChunkStream"
            @desk-refresh="handleAutopilotDeskRefreshFromStream"
          />
        </div>
        <div class="managed-monitor">
          <AutopilotDashboard
            :novel-id="slug"
            @desk-refresh="handleAutopilotDeskRefreshFromStream"
          />
        </div>
      </div>
    </div>

    <!-- AI 生成本章弹窗（流式 + 质检结果在「章节状态」） -->
    <n-modal
      v-model:show="showGenerateModal"
      preset="card"
      title="AI 生成本章（含一致性检查）"
      style="width: min(820px, 96vw); max-height: min(92vh, 900px)"
      :segmented="{ content: true, footer: 'soft' }"
      :mask-closable="!generateInProgress"
    >
      <template #header-extra>
        <n-text depth="3" style="font-size: 12px">同一流式接口；报告在本章侧栏</n-text>
      </template>

      <n-scrollbar style="max-height: min(78vh, 760px)">
        <n-space vertical :size="20">
          <n-alert type="info" :show-icon="true">
            选择目标章节与大纲后流式生成。一致性报告与俗套句式命中会出现在右侧「本章任务与状态」侧栏；此处可审阅正文并保存到所选章节。
          </n-alert>

          <n-card title="配置" size="small" :bordered="false">
            <n-space vertical :size="16">
              <n-form-item label="目标章节" label-placement="left" label-width="80">
                <n-select
                  v-model:value="generateTargetChapterId"
                  :options="chapterSelectOptions"
                  placeholder="选择要生成的章节"
                  :disabled="generateInProgress"
                  filterable
                />
              </n-form-item>

              <n-form-item label-placement="left" label-width="80" :show-feedback="false">
                <template #label>
                  <n-space :size="6" align="center">
                    <span>大纲</span>
                    <n-tag v-if="outlineBlurAnalyzing" size="tiny" type="info" round>
                      场景预分析中…
                    </n-tag>
                    <n-tag v-else-if="blurSceneCache" size="tiny" type="success" round>
                      已预分析
                    </n-tag>
                  </n-space>
                </template>
                <n-input
                  v-model:value="generateOutline"
                  type="textarea"
                  placeholder="输入大纲（可选，留空则使用默认）；失焦后自动预分析场景（供生成时复用）"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :disabled="generateInProgress"
                  @blur="onOutlineBlurAnalyze"
                />
              </n-form-item>

              <n-form-item label="场记分析" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-switch v-model:value="useSceneDirector" :disabled="generateInProgress" size="small" />
                  <n-text depth="3" style="font-size: 12px">
                    若失焦未预分析，则在点击生成时再分析场景（与预分析二选一即可）
                  </n-text>
                </n-space>
              </n-form-item>

              <n-alert v-if="sceneDirectorError" type="warning" :show-icon="true" style="font-size: 12px">
                场记分析失败（不影响生成）：{{ sceneDirectorError }}
              </n-alert>

              <n-button
                type="primary"
                @click="handleStartGenerate"
                :loading="generateInProgress"
                :disabled="generateInProgress || isAssistedReadOnly || generateTargetChapterId == null"
                size="medium"
                block
              >
                {{
                  generateInProgress
                    ? analyzingScene
                      ? '分析场景中...'
                      : '生成中...'
                    : '开始生成'
                }}
              </n-button>
            </n-space>
          </n-card>

          <!-- 上下文预览 -->
          <n-card size="small" :bordered="false">
            <template #header>
              <n-space align="center" justify="space-between" style="width:100%">
                <n-space align="center" :size="6">
                  <span style="font-size:13px;font-weight:600">上下文预览</span>
                  <n-text depth="3" style="font-size:11px">AI 实际接收到的三层信息</n-text>
                </n-space>
                <n-button
                  size="tiny"
                  secondary
                  :loading="loadingContext"
                  @click="previewContext"
                >
                  {{ contextPreview ? '重新获取' : '预览' }}
                </n-button>
              </n-space>
            </template>
            <template v-if="contextPreview && modalTargetChapter">
              <!-- Token 分布 -->
              <n-space vertical :size="8">
                <n-space :size="6" wrap>
                  <n-tag size="small" type="info" round>
                    L1 核心 {{ contextPreview.token_usage.layer1 }} tok
                  </n-tag>
                  <n-tag size="small" type="success" round>
                    L2 检索 {{ contextPreview.token_usage.layer2 }} tok
                  </n-tag>
                  <n-tag size="small" type="warning" round>
                    L3 近期 {{ contextPreview.token_usage.layer3 }} tok
                  </n-tag>
                  <n-tag size="small" round>
                    合计 {{ contextPreview.token_usage.total }} / {{ contextPreview.token_usage.limit }}
                  </n-tag>
                </n-space>
                <n-progress
                  v-if="contextPreview.token_usage.limit > 0"
                  type="line"
                  :percentage="Math.min(100, Math.round(contextPreview.token_usage.total / contextPreview.token_usage.limit * 100))"
                  :height="6"
                  :border-radius="4"
                  :show-indicator="false"
                  :color="contextPreview.token_usage.total / contextPreview.token_usage.limit > 0.9 ? '#f0a020' : '#18a058'"
                />
                <n-collapse>
                  <n-collapse-item title="Layer 1 · 核心设定（Bible + 伏笔）" name="l1">
                    <n-code :code="contextPreview.layer1.content" word-wrap style="font-size:11px;max-height:200px;overflow:auto" />
                  </n-collapse-item>
                  <n-collapse-item title="Layer 2 · 智能检索（向量相关段落）" name="l2">
                    <n-code :code="contextPreview.layer2.content || '（向量检索未启用或无匹配）'" word-wrap style="font-size:11px;max-height:200px;overflow:auto" />
                  </n-collapse-item>
                  <n-collapse-item title="Layer 3 · 近期章节（滑动窗口）" name="l3">
                    <n-code :code="contextPreview.layer3.content" word-wrap style="font-size:11px;max-height:200px;overflow:auto" />
                  </n-collapse-item>
                </n-collapse>
              </n-space>
            </template>
            <n-text v-else depth="3" style="font-size:12px">
              点击「预览」查看 AI 生成时实际使用的上下文内容及 token 分布。
            </n-text>
          </n-card>

          <n-card
            v-if="generateInProgress || generatedContent"
            title="生成内容"
            size="small"
            :bordered="false"
          >
            <template #header-extra>
              <n-space :size="8">
                <n-button
                  v-if="generatedContent && !generateInProgress"
                  size="tiny"
                  type="primary"
                  :disabled="isAssistedReadOnly"
                  @click="handleSaveGenerated"
                  :loading="saving"
                >
                  保存到所选章节
                </n-button>
                <n-button
                  size="tiny"
                  @click="clearGeneratedDraft"
                  :disabled="generateInProgress"
                >
                  清空
                </n-button>
              </n-space>
            </template>
            <n-space v-if="generateInProgress" vertical :size="8" style="width: 100%">
              <n-progress
                type="line"
                :percentage="streamProgressPct"
                :processing="streamProgressPct < 100"
                :height="8"
                indicator-placement="inside"
              />
              <n-space justify="space-between" style="width: 100%">
                <n-text depth="3" style="font-size: 12px">{{ streamPhaseLabel || '准备中…' }}</n-text>
                <n-text depth="3" style="font-size: 12px">
                  {{ streamStats.chars }} 字 · ~{{ streamStats.estimated_tokens }} tokens
                </n-text>
              </n-space>
            </n-space>
            <n-scrollbar style="max-height: 500px">
              <n-input
                v-model:value="generatedContent"
                type="textarea"
                :autosize="{ minRows: 15, maxRows: 30 }"
                :readonly="generateInProgress"
                placeholder="生成的内容将在此显示..."
              />
            </n-scrollbar>
          </n-card>
        </n-space>
      </n-scrollbar>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showGenerateModal = false" :disabled="generateInProgress">关闭</n-button>
          <n-button v-if="generateInProgress" secondary @click="stopGenerate">停止</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 张力诊断弹窗 -->
    <n-modal
      v-model:show="showTensionModal"
      preset="card"
      title="🔍 张力诊断"
      style="width: min(560px, 96vw)"
    >
      <n-space vertical :size="16">
        <n-alert type="info" :show-icon="false" style="font-size:13px">
          诊断当前章节张力缺口，识别缺失元素并给出突破建议。
        </n-alert>

        <n-form-item label="问题描述（可选）" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="tensionStuckReason"
            type="textarea"
            placeholder="例：人物对话没有冲突，场景推进感觉平淡……（留空也可分析）"
            :autosize="{ minRows: 2, maxRows: 5 }"
          />
        </n-form-item>

        <n-button type="primary" block :loading="tensionLoading" @click="runTensionSlingshot">
          开始分析
        </n-button>

        <template v-if="tensionResult">
          <n-divider style="margin:4px 0" />
          <n-space vertical :size="10">
            <n-space align="center" :size="8">
              <n-text strong>张力等级</n-text>
              <n-tag
                :type="tensionResult.tension_level === 'high' ? 'success' : tensionResult.tension_level === 'medium' ? 'warning' : 'error'"
                round
              >
                {{ tensionResult.tension_level === 'high' ? '高张力' : tensionResult.tension_level === 'medium' ? '中等' : '低张力 ⚠' }}
              </n-tag>
            </n-space>

            <div>
              <n-text strong style="display:block;margin-bottom:6px">诊断</n-text>
              <n-text style="font-size:13px;line-height:1.7">{{ tensionResult.diagnosis }}</n-text>
            </div>

            <div v-if="tensionResult.missing_elements.length">
              <n-text strong style="display:block;margin-bottom:6px">缺失元素</n-text>
              <n-space wrap :size="6">
                <n-tag v-for="el in tensionResult.missing_elements" :key="el" type="warning" size="small" round>
                  {{ el }}
                </n-tag>
              </n-space>
            </div>

            <div v-if="tensionResult.suggestions.length">
              <n-text strong style="display:block;margin-bottom:6px">突破建议</n-text>
              <n-space vertical :size="6">
                <n-card
                  v-for="(s, i) in tensionResult.suggestions"
                  :key="i"
                  size="small"
                  :bordered="true"
                  style="font-size:13px;line-height:1.7"
                >
                  {{ i + 1 }}. {{ s }}
                </n-card>
              </n-space>
            </div>
          </n-space>
        </template>
      </n-space>
      <template #action>
        <n-space justify="end">
          <n-button @click="showTensionModal = false">关闭</n-button>
        </n-space>
      </template>
    </n-modal>

  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, type Component } from 'vue'
import { useMessage } from 'naive-ui'
import { resolveHttpUrl } from '../../api/config'
import {
  consumeGenerateChapterStream,
  analyzeScene,
  retrieveContext,
} from '../../api/workflow'
import type { ContextPreviewResult, GenerateChapterWorkflowResponse } from '../../api/workflow'
import { chapterApi } from '../../api/chapter'
import { tensionApi } from '../../api/tools'
import type { TensionDiagnosis } from '../../api/tools'
import ChapterElementPanel from './ChapterElementPanel.vue'
import ChapterContentPanel from './ChapterContentPanel.vue'
import ChapterStatusPanel from './ChapterStatusPanel.vue'
import ChapterWorkbenchShell from './ChapterWorkbenchShell.vue'
import QualityGuardrailPanel from './QualityGuardrailPanel.vue'
import TraceRecordPanel from './TraceRecordPanel.vue'
import AutopilotPanel from '../autopilot/AutopilotPanel.vue'
import AutopilotDashboard from '../autopilot/AutopilotDashboard.vue'
import { useChapterDeskLayout } from '../../composables/useChapterDeskLayout'
import {
  CHAPTER_DESK_DEEP_ORDER,
  isChapterDeskDeepSurface,
  type ChapterDeskDeepSurfaceId,
} from '../../workbench/chapterDeskSurface'
import { AppsOutline, ChevronForwardOutline, PulseOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
  content?: string
}

interface WorkAreaProps {
  slug: string
  bookTitle?: string
  chapters: Chapter[]
  currentChapterId?: number | null
  chapterContent?: string
  chapterLoading?: boolean
}

const props = withDefaults(defineProps<WorkAreaProps>(), {
  chapters: () => [],
  currentChapterId: null,
  chapterContent: '',
  chapterLoading: false
})

const emit = defineEmits<{
  setRightPanel: [panel: string]
  startWrite: []
  chapterUpdated: []
}>()

const message = useMessage()

const desk = useChapterDeskLayout()

function deepSurfaceIcon(id: ChapterDeskDeepSurfaceId): Component {
  const map: Record<ChapterDeskDeepSurfaceId, Component> = {
    elements: AppsOutline,
    guardrail: ShieldCheckmarkOutline,
    trace: PulseOutline,
  }
  return map[id]
}

const deepDrawerDropdownOptions = computed(() =>
  CHAPTER_DESK_DEEP_ORDER.map((id) => ({
    label: desk.deepMeta[id].label,
    key: id,
  }))
)

function onDeepDrawerDropdownSelect(key: string) {
  if (isChapterDeskDeepSurface(key)) {
    desk.openDeepDrawer(key)
  }
}

function onDeepDrawerOpenUpdate(v: boolean) {
  desk.deepDrawerOpen = v
  if (!v) {
    desk.deepDrawerSurface = null
  }
}

/** 辅助撰稿：编辑与章级工具；托管撰稿：驾驶舱 + 监控大盘 */
const workMode = ref<'assisted' | 'managed'>('managed')

const showGenerateModal = ref(false)
const generateOutline = ref('')
const generatedContent = ref('')
/** 弹窗内选中的目标章节（与 useWorkbench 映射一致：id === number） */
const generateTargetChapterId = ref<number | null>(null)
const generateInProgress = ref(false)
const lastWorkflowResult = ref<GenerateChapterWorkflowResponse | null>(null)
const lastQcChapterNumber = ref<number | null>(null)
const blurSceneCache = ref<Record<string, unknown> | undefined>(undefined)
const outlineBlurAnalyzing = ref(false)
const streamPhaseLabel = ref('')
const streamProgressPct = ref(0)
const streamStats = ref({ chars: 0, estimated_tokens: 0, chunks: 0 })

// Autopilot 状态
const autopilotStatus = ref<any>(null)
const isAutopilotRunning = computed(() => autopilotStatus.value?.autopilot_status === 'running')
/** 守护进程章末审阅快照（与 /autopilot/status 同源） */
const autopilotChapterReview = computed(() => autopilotStatus.value?.last_chapter_audit ?? null)

/** 在辅助撰稿且全托管运行中：只读，不可改稿与生成 */
const isAssistedReadOnly = computed(
  () => workMode.value === 'assisted' && isAutopilotRunning.value
)

/** 与左侧章节「已收稿」、结构树同步：全托管推进时刷新 desk（首次快照只记录不 emit，避免与进入页重复请求） */
const lastAutopilotDeskSnap = ref<string | null>(null)

function deskSnapFromAutopilot(status: Record<string, unknown> | null | undefined): string {
  if (!status) return ''
  const s = status
  return [
    s.completed_chapters ?? 0,
    s.manuscript_chapters ?? 0,
    s.total_words ?? 0,
    s.current_stage ?? '',
    s.current_act ?? 0,
    s.current_chapter_in_act ?? 0,
    s.current_chapter_number ?? '',
    s.current_beat_index ?? 0,
    s.needs_review === true ? '1' : '0',
  ].join('|')
}

/** 🔥 去抖 desk 刷新：300ms 内多次调用只执行一次 emit，避免 SSE 事件 + 轮询同时触发时重复 loadDesk */
let deskRefreshDebounce: ReturnType<typeof setTimeout> | null = null
function emitDeskRefreshDebounced() {
  if (deskRefreshDebounce) return  // 已有待执行的，跳过
  deskRefreshDebounce = setTimeout(() => {
    deskRefreshDebounce = null
    emit('chapterUpdated')
  }, 300)
}

function maybeEmitDeskRefresh(status: Record<string, unknown> | null | undefined) {
  const next = deskSnapFromAutopilot(status)
  if (next === '') return
  if (lastAutopilotDeskSnap.value === null) {
    lastAutopilotDeskSnap.value = next
    return
  }
  if (lastAutopilotDeskSnap.value === next) return
  lastAutopilotDeskSnap.value = next
  emitDeskRefreshDebounced()
}

const handleAutopilotStatusChange = (status: any) => {
  autopilotStatus.value = status
  maybeEmitDeskRefresh(status)
}

/** SSE 已广播刷新信号时去抖触发 desk 刷新（与 maybeEmitDeskRefresh 共用去抖逻辑） */
function handleAutopilotDeskRefreshFromStream() {
  emitDeskRefreshDebounced()
}

/** 自动驾驶章节内容流更新：实时显示正在写作的内容 */
const streamingChapterNumber = ref<number | null>(null)
const streamingContent = ref('')

function handleChapterContentUpdate(data: { chapterNumber: number; content: string; wordCount: number }) {
  streamingChapterNumber.value = data.chapterNumber
  streamingContent.value = data.content

  // 如果当前正在查看的章节就是正在写作的章节，实时更新编辑框内容
  if (currentChapter.value && currentChapter.value.number === data.chapterNumber) {
    chapterContent.value = data.content
  }
}

/** SSE 增量 chunk：驱动编辑区与托管预览同步打字机式更新（整章快照事件较少，仅靠 snapshot 会卡顿） */
function handleChapterChunkStream(data: {
  chunk: string
  beatIndex: number
  content: string
  chapterNumber: number
}) {
  const n = data.chapterNumber
  if (!n) return
  streamingChapterNumber.value = n
  streamingContent.value = data.content
  if (currentChapter.value && currentChapter.value.number === n) {
    chapterContent.value = data.content
  }
}

/** 辅助撰稿下不挂载驾驶舱，需独立轮询托管状态以支持「运行中只读」 */
let assistedAutopilotPollTimer: ReturnType<typeof setTimeout> | null = null
/** 该书在库中不存在(404)时不再轮询 /autopilot/.../status */
let assistedAutopilot404 = false
let assistAutopilotPollFailures = 0

function assistedAutopilotPollDelayMs(): number {
  const base = 4000
  const mult = Math.min(2 ** Math.min(assistAutopilotPollFailures, 8), 128)
  return Math.min(base * mult, 60_000)
}

function clearAssistedAutopilotPoll() {
  if (assistedAutopilotPollTimer != null) {
    clearTimeout(assistedAutopilotPollTimer)
    assistedAutopilotPollTimer = null
  }
}

function scheduleAssistedAutopilotPoll() {
  clearAssistedAutopilotPoll()
  if (assistedAutopilot404 || workMode.value !== 'assisted' || document.hidden) {
    return
  }
  assistedAutopilotPollTimer = window.setTimeout(() => {
    void pollAutopilotStatusWhileAssisted().finally(() => {
      scheduleAssistedAutopilotPoll()
    })
  }, assistedAutopilotPollDelayMs())
}

function handleVisibilityChange() {
  if (document.hidden) {
    clearAssistedAutopilotPoll()
  } else if (workMode.value === 'assisted') {
    assistAutopilotPollFailures = 0
    void pollAutopilotStatusWhileAssisted().finally(() => scheduleAssistedAutopilotPoll())
  }
}

async function pollAutopilotStatusWhileAssisted() {
  if (assistedAutopilot404) return
  try {
    const res = await fetch(resolveHttpUrl(`/api/v1/autopilot/${props.slug}/status`))
    if (res.status === 404) {
      assistedAutopilot404 = true
      clearAssistedAutopilotPoll()
      assistAutopilotPollFailures = 0
      return
    }
    if (res.ok) {
      assistAutopilotPollFailures = 0
      const json = await res.json()
      autopilotStatus.value = json
      maybeEmitDeskRefresh(json)
    } else {
      assistAutopilotPollFailures += 1
    }
  } catch {
    assistAutopilotPollFailures += 1
  }
}

watch(
  () => props.slug,
  () => {
    lastAutopilotDeskSnap.value = null
    assistedAutopilot404 = false
    assistAutopilotPollFailures = 0
    clearAssistedAutopilotPoll()
    if (workMode.value === 'assisted') {
      void pollAutopilotStatusWhileAssisted().finally(() => scheduleAssistedAutopilotPoll())
    }
  }
)

watch(
  () => workMode.value,
  (mode) => {
    clearAssistedAutopilotPoll()
    assistAutopilotPollFailures = 0
    if (mode === 'assisted') {
      void pollAutopilotStatusWhileAssisted().finally(() => scheduleAssistedAutopilotPoll())
    }
  },
  { immediate: true }
)

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  clearAssistedAutopilotPoll()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

/** 左侧切换章节（或路由）导致章 id 变化时回到辅助撰稿 */
watch(
  () => props.currentChapterId,
  (id, prev) => {
    if (id != null && id !== prev) {
      workMode.value = 'assisted'
    }
  }
)

// 章节编辑
const chapterContent = ref('')
const originalContent = ref('')
const loading = computed(() => props.chapterLoading)
const saving = ref(false)

// Scene Director 开关
const useSceneDirector = ref(false)
const analyzingScene = ref(false)
const sceneDirectorError = ref('')

// 张力诊断
const showTensionModal = ref(false)
const tensionLoading = ref(false)
const tensionStuckReason = ref('')
const tensionResult = ref<TensionDiagnosis | null>(null)

const openTensionModal = () => {
  tensionResult.value = null
  tensionStuckReason.value = ''
  showTensionModal.value = true
}

const runTensionSlingshot = async () => {
  if (!currentChapter.value) return
  if (isAssistedReadOnly.value) {
    message.warning('托管运行中不可使用张力诊断')
    return
  }
  tensionLoading.value = true
  try {
    tensionResult.value = await tensionApi.slingshot(props.slug, {
      novel_id: props.slug,
      chapter_number: currentChapter.value.number,
      stuck_reason: tensionStuckReason.value || undefined,
    })
  } catch {
    message.error('分析失败，请稍后重试')
  } finally {
    tensionLoading.value = false
  }
}

// 上下文预览
const contextPreview = ref<ContextPreviewResult | null>(null)
const loadingContext = ref(false)

const chapterSelectOptions = computed(() =>
  props.chapters.map(ch => ({
    label: `第 ${ch.number} 章${ch.title ? ` · ${ch.title.slice(0, 22)}` : ''}`,
    value: ch.id,
  }))
)

const modalTargetChapter = computed(() => {
  const id = generateTargetChapterId.value
  if (id == null) return null
  return props.chapters.find(ch => ch.id === id) ?? null
})

const previewContext = async () => {
  const chNum = modalTargetChapter.value?.number
  if (!chNum) return
  loadingContext.value = true
  try {
    contextPreview.value = await retrieveContext(
      props.slug,
      chNum,
      generateOutline.value || `第${chNum}章：承接前情，推进主线`,
    )
  } catch {
    contextPreview.value = null
  } finally {
    loadingContext.value = false
  }
}

async function onOutlineBlurAnalyze() {
  const ch = modalTargetChapter.value
  const outline = generateOutline.value.trim()
  if (!ch || !outline || outlineBlurAnalyzing.value || generateInProgress.value) {
    return
  }
  outlineBlurAnalyzing.value = true
  try {
    const analysis = await analyzeScene(props.slug, ch.number, outline)
    blurSceneCache.value = analysis as Record<string, unknown>
  } catch {
    blurSceneCache.value = undefined
  } finally {
    outlineBlurAnalyzing.value = false
  }
}

function clearWorkflowQc() {
  lastWorkflowResult.value = null
  lastQcChapterNumber.value = null
}

function clearGeneratedDraft() {
  generatedContent.value = ''
  clearWorkflowQc()
}

watch(generateTargetChapterId, () => {
  blurSceneCache.value = undefined
  contextPreview.value = null
})

// AbortController：点「停止」时真正取消后端 SSE 流
const generateAbortCtrl = ref<AbortController | null>(null)

// 正在生成的章节 ID（null = 不在生成中）
// 与 currentChapterId 解耦：用户可以切换章节，生成仍在后台继续
const generatingChapterId = ref<number | null>(null)

/** 当前视图是否正处于生成中（快速生成按钮 loading） */
const generating = computed(
  () =>
    generateInProgress.value &&
    generatingChapterId.value !== null &&
    generatingChapterId.value === props.currentChapterId
)

const currentChapter = computed(() => {
  if (!props.currentChapterId) return null
  return props.chapters.find(ch => ch.id === props.currentChapterId) || null
})

const signalStrip = computed(() => {
  const r = autopilotChapterReview.value
  const ch = currentChapter.value
  if (!r || !ch || r.chapter_number !== ch.number) return null
  return {
    tension: r.tension ?? 0,
    sync: !!r.narrative_sync_ok,
  }
})

const hasChanges = computed(() => {
  return chapterContent.value !== originalContent.value
})

const wordCount = computed(() => {
  // 🔥 流式写作时取流式内容长度，否则取编辑框内容长度
  if (isAutopilotRunning.value && streamingChapterNumber.value === currentChapter.value?.number && streamingContent.value) {
    return streamingContent.value.length
  }
  return chapterContent.value.length
})

/** 托管流式：用 /status 的已定稿字数与单章目标拆分展示，避免只显示「三千多字」误解为终稿 */
const streamingWordCountHint = computed((): string | null => {
  if (!isAutopilotRunning.value || streamingChapterNumber.value !== currentChapter.value?.number || !streamingContent.value) {
    return null
  }
  const st = autopilotStatus.value
  const tgt = Math.max(
    0,
    Number(st?.chapter_target_words ?? st?.target_words_per_chapter ?? 0)
  )
  if (!tgt) return null
  const acc = Math.max(0, Number(st?.accumulated_words ?? 0))
  const live = streamingContent.value.length
  const over = Math.max(0, live - acc)
  if (over > 0) {
    return `已定 ${acc}/${tgt} · 流式 +${over}`
  }
  return `已定 ${live}/${tgt}`
})

/** 🔥 编辑框显示内容：流式时显示流式内容，否则显示普通内容 */
const editorDisplayContent = computed({
  get: () => {
    if (isAutopilotRunning.value && streamingChapterNumber.value === currentChapter.value?.number && streamingContent.value) {
      return streamingContent.value
    }
    return chapterContent.value
  },
  set: (val: string) => {
    chapterContent.value = val
  }
})

// 监听传入的章节内容变化
watch(() => props.chapterContent, (newContent) => {
  chapterContent.value = newContent
  originalContent.value = newContent
}, { immediate: true })

// 切换回正在生成的章节时，自动打开生成弹窗（让用户看到进度）
watch(() => props.currentChapterId, (id) => {
  if (id !== null && id === generatingChapterId.value) {
    showGenerateModal.value = true
  }
})

const handleContentChange = () => {
  // 内容变化
}

const handleSave = async () => {
  if (!currentChapter.value) return
  if (isAssistedReadOnly.value) {
    message.warning('托管运行中不可保存，请先停止托管或仅阅读正文')
    return
  }

  saving.value = true
  try {
    await chapterApi.updateChapter(props.slug, currentChapter.value.id, { content: chapterContent.value })
    originalContent.value = chapterContent.value
    message.success('保存成功')
    emit('chapterUpdated')
  } catch (error) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleReload = async () => {
  if (!currentChapter.value) return
  try {
    const fresh = await chapterApi.getChapter(props.slug, currentChapter.value.number)
    chapterContent.value = fresh.content ?? ''
    originalContent.value = fresh.content ?? ''
    message.success('已重新加载')
  } catch {
    message.error('加载失败，请稍后重试')
  }
}

const handleGenerateChapter = async () => {
  if (!currentChapter.value) return
  if (isAssistedReadOnly.value) {
    message.warning('托管运行中不可使用快速生成')
    return
  }

  generateTargetChapterId.value = currentChapter.value.id
  generateOutline.value = `第${currentChapter.value.number}章：${currentChapter.value.title || ''}

承接前情，推进主线与人物节拍；保持人设与叙事节奏一致。`
  generatedContent.value = ''
  contextPreview.value = null
  blurSceneCache.value = undefined
  showGenerateModal.value = true
}

function streamPhaseToProgress(phase: string): number {
  const map: Record<string, number> = {
    planning: 18,
    context: 40,
    llm: 72,
    post: 92,
  }
  return map[phase] ?? 12
}

function streamPhaseToLabel(phase: string): string {
  const map: Record<string, string> = {
    planning: '规划节拍…',
    context: '组装上下文…',
    llm: '撰写正文…',
    post: '质检与收尾…',
  }
  return map[phase] ?? phase
}

const handleStartGenerate = async () => {
  const target = modalTargetChapter.value
  if (!target) {
    message.warning('请选择目标章节')
    return
  }
  if (isAssistedReadOnly.value) {
    message.warning('托管运行中不可手动生成')
    return
  }

  const targetChapterId = target.id
  const targetChapterNumber = target.number
  generatingChapterId.value = targetChapterId
  generateInProgress.value = true
  generatedContent.value = ''
  sceneDirectorError.value = ''
  lastWorkflowResult.value = null
  lastQcChapterNumber.value = null
  streamPhaseLabel.value = '连接中…'
  streamProgressPct.value = 8
  streamStats.value = { chars: 0, estimated_tokens: 0, chunks: 0 }

  const ctrl = new AbortController()
  generateAbortCtrl.value = ctrl

  let sceneDirectorResult: Record<string, unknown> | undefined = blurSceneCache.value
  if (useSceneDirector.value && !sceneDirectorResult) {
    analyzingScene.value = true
    try {
      const outline = generateOutline.value || `第${targetChapterNumber}章：承接前情，推进主线`
      const analysis = await analyzeScene(props.slug, targetChapterNumber, outline)
      sceneDirectorResult = analysis as Record<string, unknown>
    } catch (e: unknown) {
      sceneDirectorError.value = e instanceof Error ? e.message : '分析失败'
    } finally {
      analyzingScene.value = false
    }
  }

  const defaultOutline = `第${targetChapterNumber}章：承接前情，推进主线`

  try {
    await consumeGenerateChapterStream(
      props.slug,
      {
        chapter_number: targetChapterNumber,
        outline: generateOutline.value || defaultOutline,
        scene_director_result: sceneDirectorResult,
      },
      {
        signal: ctrl.signal,
        onPhase: (phase) => {
          streamPhaseLabel.value = streamPhaseToLabel(phase)
          streamProgressPct.value = streamPhaseToProgress(phase)
        },
        onChunk: (text, stats) => {
          generatedContent.value += text
          if (stats) {
            streamStats.value = stats
          }
        },
        onDone: (result) => {
          lastWorkflowResult.value = result
          lastQcChapterNumber.value = targetChapterNumber
          generatedContent.value = result.content
          streamProgressPct.value = 100
          streamPhaseLabel.value = '已完成'
          if (props.currentChapterId === targetChapterId) {
            message.success('生成完成，质检已同步到本章侧栏')
          } else {
            message.success(`第 ${targetChapterNumber} 章生成完成，请在对应章侧栏查看质检`)
          }
          desk.nudgeRailAfterGeneration()
        },
        onError: (err) => {
          if (!ctrl.signal.aborted) {
            message.error(`生成失败: ${err}`)
          }
        },
      }
    )
  } catch {
    if (!ctrl.signal.aborted) {
      message.error('生成失败')
    }
  } finally {
    generateInProgress.value = false
    generatingChapterId.value = null
    generateAbortCtrl.value = null
    if (!ctrl.signal.aborted && streamProgressPct.value < 100) {
      streamPhaseLabel.value = ''
      streamProgressPct.value = 0
    }
  }
}

const handleSaveGenerated = async () => {
  const saveTarget = modalTargetChapter.value
  if (!saveTarget || !generatedContent.value) return
  if (isAssistedReadOnly.value) {
    message.warning('托管运行中不可保存生成结果')
    return
  }

  saving.value = true
  try {
    await chapterApi.updateChapter(props.slug, saveTarget.number, { content: generatedContent.value })
    if (saveTarget.id === props.currentChapterId) {
      chapterContent.value = generatedContent.value
      originalContent.value = generatedContent.value
    }
    message.success(`已保存到第 ${saveTarget.number} 章`)
    emit('chapterUpdated')
    showGenerateModal.value = false
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

const stopGenerate = () => {
  generateAbortCtrl.value?.abort()
  generateAbortCtrl.value = null
  generatingChapterId.value = null
  generateInProgress.value = false
  streamPhaseLabel.value = ''
  streamProgressPct.value = 0
  message.info('已停止生成')
}

/** 左侧每次点选章节时由父组件调用，确保回到辅助撰稿（含重复点击当前章） */
function ensureAssistedMode() {
  workMode.value = 'assisted'
}

defineExpose({ ensureAssistedMode })
</script>

<style scoped>
.work-area {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--app-surface);
}

.work-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.work-mode-switch {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

/* 双语文案轨道略宽，避免挤字 */
.work-mode-switch :deep(.n-switch__rail) {
  min-width: 5.5rem;
}

.assisted-readonly-banner {
  flex-shrink: 0;
  margin: 0 16px 8px;
}

.assisted-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chapter-desk-shell {
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.desk-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.rail-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.rail-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.08));
}

.rail-scroll {
  flex: 1;
  min-height: 0;
}

.rail-scroll-pad {
  padding: 10px 10px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rail-icon-btn {
  max-width: 100%;
}

.deep-drawer-body {
  min-height: min(70vh, 560px);
}

.managed-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.managed-daemon-hint {
  flex-shrink: 0;
  margin: 0 16px 10px;
  font-size: 12px;
  line-height: 1.55;
}

.managed-daemon-hint .inline-code {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.12);
}

.managed-autopilot {
  flex-shrink: 0;
}

.managed-monitor {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--app-surface);
}

.managed-monitor :deep(.autopilot-dashboard) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.work-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--aitext-split-border);
}

.work-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.work-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.work-sub {
  font-size: 13px;
}

.autopilot-container {
  padding: 16px 20px;
  background: linear-gradient(
    to bottom,
    var(--app-surface) 0%,
    color-mix(in srgb, var(--color-success, #22c55e) 3%, var(--app-surface)) 100%
  );
  border-bottom: 1px solid var(--aitext-split-border);
}

.monitor-container {
  height: 100%;
  padding: 20px;
  overflow-y: auto;
  background: var(--app-surface);
}

.elements-tab-wrap {
  height: 100%;
  min-height: 0;
  padding: 12px 16px 16px;
  overflow: hidden;
  background: var(--app-surface);
  display: flex;
  flex-direction: column;
}

.elements-tab-wrap :deep(.ce-panel) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.work-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 20px 20px;
  overflow: hidden;
}

.work-empty {
  margin-top: 80px;
}

.write-modal-body {
  padding-right: 6px;
}

.output-area {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--app-text-secondary);
}

.write-modal-body :deep(.n-card) {
  background: var(--card-color);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.write-modal-body :deep(.n-card__header) {
  padding: 12px 16px;
  font-weight: 600;
  font-size: 14px;
}

.write-modal-body :deep(.n-card__content) {
  padding: 16px;
}

.write-modal-body :deep(.n-form-item) {
  margin-bottom: 0;
}

.chapter-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
  height: 100%;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--app-border);
}

.editor-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.editor-title h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.editor-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}

.editor-body :deep(.n-input) {
  flex: 1;
  min-height: 0;
  height: 100% !important;
  max-height: none !important;
}

.editor-body :deep(.n-input .n-input-wrapper) {
  height: 100% !important;
  max-height: none !important;
  display: flex;
  flex-direction: column;
}

.editor-body :deep(.n-input__textarea-el) {
  flex: 1;
  height: 100% !important;
  min-height: 200px;
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.8;
  overflow-y: auto !important;
  resize: none;
}

.editor-footer {
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

/* 🔥 流式编辑框：编辑框本身就是流式显示 */
.editor-input-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.editor-input-wrapper.is-streaming :deep(.n-input) {
  border-color: rgba(24, 160, 88, 0.3);
  box-shadow: 0 0 0 1px rgba(24, 160, 88, 0.1);
}

.editor-input-wrapper.is-streaming :deep(.n-input__textarea-el) {
  color: rgba(0, 0, 0, 0.85);
}

.streaming-cursor-overlay {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(24, 160, 88, 0.08);
  border-radius: 4px;
  pointer-events: none;
}

.streaming-cursor {
  color: #18a058;
  animation: cursor-blink-anim 1s step-end infinite;
  font-size: 14px;
}

.streaming-badge {
  font-size: 11px;
  color: #18a058;
  font-weight: 500;
}

@keyframes cursor-blink-anim {
  50% { opacity: 0; }
}

/* 🔥 流式字数动画 */
.streaming-word-count {
  color: #18a058;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.streaming-indicator {
  color: #18a058;
  font-size: 12px;
  margin-left: 4px;
  animation: cursor-blink-anim 1s step-end infinite;
}

.editor-wordcount-line {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.wordcount-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  margin-left: 2px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
  color: var(--n-text-color-3);
  border: 1px solid var(--n-border-color);
  cursor: help;
  line-height: 1;
}

/* 🔥 当前幕信息 */
.act-info-header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
}

.act-info-title {
  font-size: 12px;
  color: var(--n-text-color-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.act-info-desc {
  font-size: 11px;
  color: var(--n-text-color-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
