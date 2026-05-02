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
      <!-- 辅助撰稿：编辑区 + 章节状态 + 章节元素（无全托管驾驶、无监控大盘） -->
      <template v-if="workMode === 'assisted'">
        <n-alert
          v-if="isAssistedReadOnly"
          type="warning"
          :show-icon="true"
          class="assisted-readonly-banner"
        >
          <strong>全托管运行中</strong>：本侧仅只读；不能保存、改稿、快速生成或改章节元素。
          请切换到「<strong>托管撰稿</strong>」看驾驶舱与监控，或停止托管后再编辑。
        </n-alert>
        <n-tabs v-model:value="activeTab" type="line" animated class="work-tabs assisted-tabs">
          <n-tab-pane name="editor" tab="📝 章节编辑">
            <div class="work-main">
              <div v-if="currentChapter" class="chapter-editor">
                <div class="editor-header">
                  <div class="editor-title">
                    <h3>{{ currentChapter.title || `第${currentChapter.number}章` }}</h3>
                    <n-tag size="small" :type="currentChapter.word_count > 0 ? 'success' : 'default'" round>
                      {{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}
                    </n-tag>
                  </div>
                  <n-space :size="8">
                    <n-button size="small" @click="handleReload" :disabled="loading">
                      重新加载
                    </n-button>
                    <n-button
                      size="small"
                      secondary
                      @click="openCandidateDrafts"
                      :disabled="!currentChapter"
                    >
                      候选稿
                      <template v-if="candidateDrafts.length">
                        （{{ candidateDrafts.length }}）
                      </template>
                    </n-button>
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
                  <n-input
                    v-model:value="chapterContent"
                    type="textarea"
                    placeholder="章节内容..."
                    :autosize="false"
                    :readonly="isAssistedReadOnly"
                    @update:value="handleContentChange"
                  />
                </div>

                <div class="editor-footer">
                  <n-space :size="8" align="center" justify="space-between" style="width: 100%">
                    <n-text depth="3">字数: {{ wordCount }}</n-text>
                    <n-space :size="8">
                      <n-button
                        size="small"
                        secondary
                        @click="showGenerationStyleModal = true"
                        :disabled="generateInProgress"
                        title="编辑章节生成提示词"
                      >
                        生成风格
                      </n-button>
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
                      <n-button
                        size="small"
                        secondary
                        :disabled="isAssistedReadOnly"
                        @click="openPrecisionRewriteModal"
                        title="创建精细改稿任务"
                      >
                        精细改稿
                      </n-button>
                      <n-button
                        size="small"
                        secondary
                        :disabled="isAssistedReadOnly"
                        @click="openTensionModal"
                        title="诊断当前章节张力缺口"
                      >
                        🔍 张力诊断
                      </n-button>
                    </n-space>
                  </n-space>
                </div>
              </div>

              <n-empty v-else description="请从左侧选择章节" class="work-empty" />
            </div>
          </n-tab-pane>

          <n-tab-pane name="chapter-status" tab="📋 章节状态">
            <ChapterStatusPanel
              :slug="slug"
              :chapter="currentChapter"
              :read-only="isAssistedReadOnly"
              :last-workflow-result="lastWorkflowResult"
              :qc-chapter-number="lastQcChapterNumber"
              :autopilot-chapter-review="autopilotChapterReview"
              @clear-qc="clearWorkflowQc"
              @go-editor="activeTab = 'editor'"
            />
          </n-tab-pane>

          <n-tab-pane name="chapter-content" tab="📄 章节内容">
            <div class="elements-tab-wrap">
              <ChapterContentPanel
                :slug="slug"
                :current-chapter-number="currentChapter?.number ?? null"
                :read-only="isAssistedReadOnly"
                :autopilot-chapter-review="autopilotChapterReview"
              />
            </div>
          </n-tab-pane>

          <n-tab-pane name="chapter-elements" tab="🧩 章节元素">
            <div class="elements-tab-wrap">
              <ChapterElementPanel
                :slug="slug"
                :current-chapter-number="currentChapter?.number ?? null"
                :read-only="isAssistedReadOnly"
                :last-workflow-result="lastWorkflowResult"
                :qc-chapter-number="lastQcChapterNumber"
                :autopilot-chapter-review="autopilotChapterReview"
              />
            </div>
          </n-tab-pane>
        </n-tabs>
      </template>

      <!-- 托管撰稿：驾驶舱 + 监控大盘（点击左侧章节会切回辅助撰稿） -->
      <div v-else class="managed-stack">
        <n-alert type="success" :show-icon="true" class="managed-daemon-hint">
          <strong>全托管模式</strong>：后端已自动启动守护进程线程，点击「启动全托管」即可开始自动写作。
          系统将自动进行宏观规划、幕级规划、章节撰写和审计。
        </n-alert>
        <div class="autopilot-container managed-autopilot">
          <AutopilotPanel
            :novel-id="slug"
            @status-change="handleAutopilotStatusChange"
            @chapter-content-update="handleChapterContentUpdate"
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
        <n-text depth="3" style="font-size: 12px">同一流式接口；报告在章节状态</n-text>
      </template>

      <n-scrollbar style="max-height: min(78vh, 760px)">
        <n-space vertical :size="20">
          <n-alert type="info" :show-icon="true">
            选择目标章节与大纲后流式生成。一致性报告与俗套句式命中会出现在「章节状态」；此处可审阅正文并保存到所选章节。
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
                <n-space vertical :size="8" style="width: 100%">
                  <n-space :size="8">
                    <n-button
                      size="tiny"
                      secondary
                      type="info"
                      :disabled="generateInProgress"
                      @click="applyCocManualStructureTemplate"
                    >
                      套用CoC结构模板
                    </n-button>
                    <n-text depth="3" style="font-size: 12px">
                      手动规划会随生成一起读取 Bible、正典、线索和道具账本。
                    </n-text>
                  </n-space>
                  <n-input
                    v-model:value="generateOutline"
                    type="textarea"
                    placeholder="输入大纲（可选，留空则使用默认）；失焦后自动预分析场景（供生成时复用）"
                    :autosize="{ minRows: 3, maxRows: 12 }"
                    :disabled="generateInProgress"
                    @blur="onOutlineBlurAnalyze"
                  />
                </n-space>
              </n-form-item>

              <n-card size="small" :bordered="false" class="coc-precheck-card">
                <n-space vertical :size="8">
                  <n-space justify="space-between" align="center" style="width: 100%">
                    <n-space align="center" :size="8">
                      <n-text strong style="font-size: 13px">CoC 认知预检</n-text>
                      <n-tag
                        size="tiny"
                        round
                        :type="
                          cocPrecheckResult?.risk_level === 'block'
                            ? 'error'
                            : cocPrecheckResult?.risk_level === 'warning'
                              ? 'warning'
                              : cocPrecheckResult?.checked
                                ? 'success'
                                : 'default'
                        "
                      >
                        {{
                          cocPrecheckResult?.risk_level === 'block'
                            ? '阻断'
                            : cocPrecheckResult?.risk_level === 'warning'
                              ? '提醒'
                              : cocPrecheckResult?.checked
                                ? '通过'
                                : '未检查'
                        }}
                      </n-tag>
                    </n-space>
                    <n-space :size="8">
                      <n-select
                        v-model:value="cocRewriteMode"
                        :options="cocRewriteModeOptions"
                        size="tiny"
                        style="width: 112px"
                        :disabled="generateInProgress || cocRewriteLoading"
                      />
                      <n-select
                        v-model:value="cocRewriteStyle"
                        :options="cocRewriteStyleOptions"
                        size="tiny"
                        style="width: 92px"
                        :disabled="generateInProgress || cocRewriteLoading"
                      />
                      <n-button
                        size="tiny"
                        secondary
                        :loading="cocPrecheckLoading"
                        :disabled="generateInProgress || generateTargetChapterId == null"
                        @click="runCocPrecheckForModal()"
                      >
                        立即预检
                      </n-button>
                      <n-button
                        size="tiny"
                        type="warning"
                        secondary
                        :loading="cocRewriteLoading"
                        :disabled="generateInProgress || generateTargetChapterId == null"
                        @click="rewriteOutlineForCocBoundaryForModal"
                      >
                        一键安全改写
                      </n-button>
                    </n-space>
                  </n-space>

                  <n-text depth="3" style="font-size: 12px">
                    生成前检查是否越过“读者已知 / 角色已知 / 作者真相”边界，命中阻断项会默认禁止生成。
                  </n-text>

                  <n-alert
                    v-if="cocPrecheckResult?.blocking_issues?.length"
                    type="error"
                    :show-icon="true"
                    style="font-size: 12px"
                  >
                    <n-space vertical :size="4">
                      <n-text v-for="(item, idx) in cocPrecheckResult.blocking_issues" :key="`precheck-block-${idx}`" depth="3">
                        - {{ item }}
                      </n-text>
                    </n-space>
                  </n-alert>
                  <n-alert
                    v-else-if="cocPrecheckResult?.warnings?.length"
                    type="warning"
                    :show-icon="true"
                    style="font-size: 12px"
                  >
                    <n-space vertical :size="4">
                      <n-text v-for="(item, idx) in cocPrecheckResult.warnings" :key="`precheck-warn-${idx}`" depth="3">
                        - {{ item }}
                      </n-text>
                    </n-space>
                  </n-alert>

                  <n-form-item
                    v-if="cocPrecheckResult?.blocking_issues?.length"
                    label="强制继续"
                    label-placement="left"
                    label-width="80"
                    :show-feedback="false"
                  >
                    <n-space align="center" :size="8">
                      <n-switch
                        v-model:value="ignoreCocPrecheckBlockOnce"
                        :disabled="generateInProgress"
                        size="small"
                      />
                      <n-text depth="3" style="font-size: 12px">
                        仅本次生成忽略阻断（建议仅用于实验）
                      </n-text>
                    </n-space>
                  </n-form-item>

                  <n-alert
                    v-if="cocRewriteResult?.applied_rules?.length"
                    type="info"
                    :show-icon="true"
                    style="font-size: 12px"
                  >
                    <n-space vertical :size="4">
                      <n-space :size="6" align="center">
                        <n-text depth="3">本次改写模式</n-text>
                        <n-tag size="tiny" round :type="cocRewriteResult.rewrite_mode === 'aggressive' ? 'warning' : 'info'">
                          {{ cocRewriteResult.rewrite_mode === 'aggressive' ? '激进' : '保守' }}
                        </n-tag>
                        <n-tag size="tiny" round type="default">
                          {{
                            cocRewriteResult.rewrite_style === 'coc'
                              ? 'CoC向'
                              : cocRewriteResult.rewrite_style === 'suspense'
                                ? '悬疑向'
                                : '通用'
                          }}
                        </n-tag>
                      </n-space>
                      <n-text v-for="(item, idx) in cocRewriteResult.applied_rules" :key="`precheck-rewrite-${idx}`" depth="3">
                        - {{ item }}
                      </n-text>
                    </n-space>
                  </n-alert>
                </n-space>
              </n-card>

              <n-form-item label="场记分析" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-switch v-model:value="useSceneDirector" :disabled="generateInProgress" size="small" />
                  <n-text depth="3" style="font-size: 12px">
                    若失焦未预分析，则在点击生成时再分析场景（与预分析二选一即可）
                  </n-text>
                </n-space>
              </n-form-item>

              <n-form-item label="慢写过程" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-switch
                    v-model:value="avoidCompressedExpression"
                    :disabled="generateInProgress"
                    size="small"
                  />
                  <n-text depth="3" style="font-size: 12px">
                    避免把对话、动作和心理转折压成一句概括
                  </n-text>
                </n-space>
              </n-form-item>

              <n-form-item label="目标字数" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-input-number
                    v-model:value="targetWordCount"
                    :min="800"
                    :max="12000"
                    :step="100"
                    :disabled="generateInProgress"
                    size="small"
                    style="width: 140px"
                  />
                  <n-input-number
                    v-model:value="wordTolerancePercent"
                    :min="2"
                    :max="20"
                    :step="1"
                    :disabled="generateInProgress"
                    size="small"
                    style="width: 100px"
                  >
                    <template #suffix>%</template>
                  </n-input-number>
                  <n-text depth="3" style="font-size: 12px">
                    {{ targetWordRangeHint }}
                  </n-text>
                </n-space>
              </n-form-item>

              <n-form-item label="长稿母本" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-switch
                    v-model:value="longDraftMode"
                    :disabled="generateInProgress"
                    size="small"
                  />
                  <n-input-number
                    v-if="longDraftMode"
                    v-model:value="longDraftSplitCount"
                    :min="2"
                    :max="4"
                    :step="1"
                    :disabled="generateInProgress"
                    size="small"
                    style="width: 96px"
                  />
                  <n-text depth="3" style="font-size: 12px">
                    {{ longDraftMode ? `先写连续母稿，预计拆成 ${longDraftSplitCount || 2} 章` : '灰度功能：先写长稿再拆章（默认关闭）' }}
                  </n-text>
                </n-space>
              </n-form-item>

              <n-form-item label="直接写作" label-placement="left" label-width="80" :show-feedback="false">
                <n-space align="center" :size="8">
                  <n-switch
                    v-model:value="directWritingMode"
                    :disabled="generateInProgress"
                    size="small"
                  />
                  <n-text depth="3" style="font-size: 12px">
                    对照测试：跳过节拍拆分、AI味后处理和章后质检，只让模型按上下文直接写一版
                  </n-text>
                </n-space>
              </n-form-item>

              <n-alert v-if="directWritingMode" type="warning" :show-icon="true" style="font-size: 12px">
                直接写作模式不会自动生成一致性报告，也不会套用手法档案后处理；适合拿去检测，判断 PP 流程是否影响正文质感。
              </n-alert>

              <n-form-item
                v-if="directWritingMode"
                label="轻修"
                label-placement="left"
                label-width="80"
                :show-feedback="false"
              >
                <n-space align="center" :size="8">
                  <n-switch
                    v-model:value="directLightPolish"
                    :disabled="generateInProgress"
                    size="small"
                  />
                  <n-text depth="3" style="font-size: 12px">
                    直接写完后只做 10%-20% 局部编辑，压低 AI 特征但不进入完整 PP 后处理
                  </n-text>
                </n-space>
              </n-form-item>

              <n-form-item label="手法档案" label-placement="left" label-width="80" :show-feedback="false">
                <n-space vertical :size="8" style="width: 100%">
                  <n-select
                    v-model:value="generateStyleProfileId"
                    :options="styleProfileOptions"
                    placeholder="可选：选择写作手法库档案"
                    clearable
                    filterable
                    :loading="loadingStyleProfiles"
                    :disabled="generateInProgress"
                  />
                  <n-input
                    v-model:value="generateSceneType"
                    size="small"
                    placeholder="可选：场景类型，如悬疑/情感，用于优先匹配技法卡"
                    :disabled="generateInProgress"
                  />
                </n-space>
              </n-form-item>

              <n-alert v-if="sceneDirectorError" type="warning" :show-icon="true" style="font-size: 12px">
                场记分析失败（不影响生成）：{{ sceneDirectorError }}
              </n-alert>

              <n-space vertical :size="8" style="width: 100%">
                <n-space justify="space-between" align="center" style="width: 100%">
                  <n-space align="center" :size="8">
                    <n-text strong style="font-size: 13px">本章写作策略</n-text>
                    <n-tag v-if="chapterStrategy" size="tiny" type="success" round>已预览</n-tag>
                  </n-space>
                  <n-space :size="8">
                    <n-button
                      size="tiny"
                      secondary
                      :loading="loadingChapterStrategy"
                      :disabled="generateInProgress || generateTargetChapterId == null"
                      @click="previewChapterStrategyForModal"
                    >
                      {{ chapterStrategy ? '重新生成策略' : '生成策略预览' }}
                    </n-button>
                    <n-button
                      v-if="chapterStrategy"
                      size="tiny"
                      quaternary
                      :disabled="generateInProgress"
                      @click="clearChapterStrategy"
                    >
                      清空策略
                    </n-button>
                  </n-space>
                </n-space>
                <div v-if="chapterStrategy" class="generate-strategy-preview">
                  <n-alert
                    v-if="chapterStrategy.chapter_contract"
                    type="info"
                    title="章节合同"
                    :bordered="false"
                    class="chapter-contract-card"
                  >
                    <n-space vertical :size="6">
                      <n-text depth="3">本章问题：{{ chapterStrategy.chapter_contract.chapter_question }}</n-text>
                      <n-text depth="3">主角想要：{{ chapterStrategy.chapter_contract.protagonist_want }}</n-text>
                      <n-text depth="3">阻力来源：{{ chapterStrategy.chapter_contract.opposition }}</n-text>
                      <n-text depth="3">信息变化：{{ chapterStrategy.chapter_contract.required_information_change }}</n-text>
                      <n-text depth="3">章末追问：{{ chapterStrategy.chapter_contract.ending_question }}</n-text>
                      <n-space vertical :size="2">
                        <n-text strong depth="2">展示优先</n-text>
                        <n-text
                          v-for="(rule, index) in chapterStrategy.chapter_contract.show_dont_tell_rules"
                          :key="`show-rule-${index}`"
                          depth="3"
                        >
                          - {{ rule }}
                        </n-text>
                      </n-space>
                    </n-space>
                  </n-alert>
                  <div class="generate-strategy-grid">
                    <div class="strategy-chip">
                      <span class="strategy-chip__label">角色想要</span>
                      <strong>{{ chapterStrategy.dramatic_task.goal }}</strong>
                    </div>
                    <div class="strategy-chip">
                      <span class="strategy-chip__label">主要阻碍</span>
                      <strong>{{ chapterStrategy.dramatic_task.obstacle }}</strong>
                    </div>
                    <div class="strategy-chip">
                      <span class="strategy-chip__label">读者期待</span>
                      <strong>{{ chapterStrategy.dramatic_task.reader_expectation }}</strong>
                    </div>
                    <div class="strategy-chip">
                      <span class="strategy-chip__label">章末钩子</span>
                      <strong>{{ chapterStrategy.dramatic_task.ending_hook }}</strong>
                    </div>
                  </div>
                  <n-space vertical :size="8">
                    <div
                      v-for="(scene, index) in chapterStrategy.scene_plan"
                      :key="`${scene.label}-${index}`"
                      class="strategy-scene-row"
                    >
                      <n-space justify="space-between" align="center" style="width: 100%">
                        <strong>{{ index + 1 }}. {{ scene.label }}</strong>
                        <n-tag size="tiny" round>{{ scene.target_words }} 字</n-tag>
                      </n-space>
                      <n-text depth="3">任务：{{ scene.task }}</n-text>
                      <n-text depth="3">阻力：{{ scene.resistance }}</n-text>
                      <n-text depth="3">变化：{{ scene.info_shift }}</n-text>
                      <n-text depth="3">关系：{{ scene.relationship_shift }}</n-text>
                      <n-text depth="3">锚点：{{ scene.anchor }}</n-text>
                      <n-text v-if="scene.visible_action" depth="3">动作：{{ scene.visible_action }}</n-text>
                      <n-text v-if="scene.subtext_dialogue" depth="3">潜台词：{{ scene.subtext_dialogue }}</n-text>
                      <n-text v-if="scene.unspoken_emotion" depth="3">不直说：{{ scene.unspoken_emotion }}</n-text>
                      <n-text v-if="scene.object_or_clue_change" depth="3">线索/道具：{{ scene.object_or_clue_change }}</n-text>
                      <n-text depth="3">钩子：{{ scene.hook }}</n-text>
                    </div>
                  </n-space>
                </div>
                <n-text v-else depth="3" style="font-size: 12px">
                  先生成一份可见策略，再让正文按“戏剧任务 + 场景推进”写，会比只丢大纲更稳。
                </n-text>
              </n-space>

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
                    secondary
                    :loading="savingCandidateDraft"
                    :disabled="isAssistedReadOnly"
                    @click="handleSaveGeneratedAsCandidate"
                  >
                    保存为候选稿
                  </n-button>
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
            <n-alert
              v-if="styleMatchLoading || styleMatchReport"
              :type="styleMatchReport && styleMatchReport.score < 78 ? 'warning' : 'success'"
              :show-icon="true"
              style="margin: 10px 0; font-size: 12px"
            >
              <template v-if="styleMatchLoading">
                正在评估手法匹配度…
              </template>
              <template v-else-if="styleMatchReport">
                <n-space vertical :size="4">
                  <n-space align="center" :size="8">
                    <strong>手法匹配 {{ styleMatchReport.score.toFixed(1) }} 分</strong>
                    <n-tag size="tiny" :type="styleMatchReport.score >= 85 ? 'success' : styleMatchReport.score >= 78 ? 'warning' : 'error'" round>
                      {{ styleMatchReport.score >= 85 ? '贴合' : styleMatchReport.score >= 78 ? '需微调' : '偏离明显' }}
                    </n-tag>
                  </n-space>
                  <n-text v-if="styleMatchIssueText" depth="3" style="font-size: 12px">
                    {{ styleMatchIssueText }}
                  </n-text>
                </n-space>
              </template>
            </n-alert>
            <n-scrollbar style="max-height: 500px">
              <n-input
                v-model:value="generatedContent"
                type="textarea"
                :autosize="{ minRows: 15, maxRows: 30 }"
                :readonly="generateInProgress"
                placeholder="生成的内容将在此显示..."
              />
            </n-scrollbar>
            <div v-if="loadingEditorialReview || editorialReview" class="editorial-review-card">
              <n-space vertical :size="8">
                <n-space align="center" justify="space-between" style="width: 100%">
                  <n-space align="center" :size="8">
                    <strong>主编审稿</strong>
                    <n-tag
                      v-if="editorialReview"
                      size="tiny"
                      round
                      :type="editorialReview.verdict === '保留' ? 'success' : editorialReview.verdict === '建议重写' ? 'error' : 'warning'"
                    >
                      {{ editorialReview.verdict }}
                    </n-tag>
                  </n-space>
                  <n-button
                    v-if="generatedContent && !generateInProgress"
                    size="tiny"
                    secondary
                    :loading="loadingEditorialReview"
                    @click="rerunEditorialReview"
                  >
                    重新审稿
                  </n-button>
                  <n-button
                    v-if="editorialReview && generatedContent && !generateInProgress"
                    size="tiny"
                    type="primary"
                    secondary
                    :loading="generatingEditorialPolishCandidate"
                    :disabled="isAssistedReadOnly"
                    @click="generateEditorialPolishCandidate"
                  >
                    按审稿精修候选稿
                  </n-button>
                </n-space>
                <n-text v-if="loadingEditorialReview" depth="3" style="font-size: 12px">
                  正在按开篇、冲突、人物、对白、追读、节奏做主编审稿…
                </n-text>
                <template v-else-if="editorialReview">
                  <n-text depth="3">{{ editorialReview.summary }}</n-text>
                  <div class="editorial-score-grid">
                    <div
                      v-for="(value, key) in editorialReview.scores"
                      :key="key"
                      class="editorial-score-item"
                    >
                      <span>{{ editorialScoreLabel(String(key)) }}</span>
                      <strong>{{ value }}</strong>
                    </div>
                  </div>
                  <n-space vertical :size="4">
                    <n-text strong>亮点</n-text>
                    <n-text v-for="(item, index) in editorialReview.strengths" :key="`strength-${index}`" depth="3">
                      - {{ item }}
                    </n-text>
                  </n-space>
                  <n-space vertical :size="4">
                    <n-text strong>问题</n-text>
                    <n-text v-for="(item, index) in editorialReview.problems" :key="`problem-${index}`" depth="3">
                      - {{ item }}
                    </n-text>
                  </n-space>
                  <n-space vertical :size="4">
                    <n-text strong>修改动作</n-text>
                    <n-text v-for="(item, index) in editorialReview.actions" :key="`action-${index}`" depth="3">
                      - {{ item }}
                    </n-text>
                  </n-space>
                </template>
              </n-space>
            </div>
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

    <!-- 章节生成风格配置：直接打开提示词广场中的工作流生成节点 -->
    <n-modal
      v-model:show="showGenerationStyleModal"
      preset="card"
      title="生成风格 / AI味抑制"
      style="width: min(1080px, 96vw); max-height: min(94vh, 960px)"
      :segmented="{ content: true }"
      display-directive="if"
    >
      <n-scrollbar style="max-height: min(82vh, 820px)">
        <PromptDetailPanel
          node-key="workflow-chapter-generation"
          @updated="message.success('生成风格配置已保存')"
          @close="showGenerationStyleModal = false"
        />
      </n-scrollbar>
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

    <n-modal
      v-model:show="showPrecisionRewriteModal"
      preset="card"
      title="精细改稿任务"
      style="width: min(680px, 96vw)"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <n-space vertical :size="16">
        <n-alert type="info" :show-icon="true" style="font-size:13px">
          精修任务会先进入候选稿区；生成和采纳仍复用现有候选稿、快照和章后记忆更新流程。
        </n-alert>

        <n-form-item label="改稿目标" label-placement="top" :show-feedback="false">
          <n-select
            v-model:value="precisionRewriteObjective"
            :options="precisionRewriteObjectiveOptions"
            filterable
            tag
          />
        </n-form-item>

        <n-form-item label="重点片段（可选）" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="precisionRewriteTargetExcerpt"
            type="textarea"
            placeholder="粘贴需要重点处理的段落；留空表示以整章为改稿范围"
            :autosize="{ minRows: 4, maxRows: 8 }"
          />
        </n-form-item>

        <n-form-item label="作者要求（可选）" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="precisionRewriteInstruction"
            type="textarea"
            placeholder="例：保留事件顺序，增强角色压抑感，降低解释性句子"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </n-form-item>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showPrecisionRewriteModal = false">取消</n-button>
          <n-button
            secondary
            :loading="suggestingPrecisionRewriteTask"
            :disabled="!currentChapter || !chapterContent.trim()"
            @click="suggestPrecisionRewriteTask"
          >
            AI 生成建议
          </n-button>
          <n-button
            type="primary"
            :loading="savingPrecisionRewriteTask"
            :disabled="!currentChapter || !chapterContent.trim()"
            @click="createPrecisionRewriteTask"
          >
            创建任务
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showCandidateDraftsModal"
      preset="card"
      title="章节候选稿"
      style="width: min(960px, 96vw)"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <n-space vertical :size="16">
        <n-alert type="info" :show-icon="true" style="font-size: 13px">
          候选稿不会直接改写主稿。点击“采纳为主稿”后，才会复用现有章节保存、快照和章后记忆更新链路。
        </n-alert>

        <n-space justify="space-between" align="center">
          <n-space vertical :size="4">
            <n-text depth="3" style="font-size: 12px">
              当前章节：{{ currentChapter ? `第${currentChapter.number}章` : '未选择章节' }}
            </n-text>
            <n-text depth="3" style="font-size: 11px">
              候选稿分支与全局切换保持同步；留空表示查看全部，新建时会回落到 `main`。
            </n-text>
          </n-space>
          <n-space :size="8" align="center">
            <CandidateDraftBranchSwitcher :slug="slug" width="180px" />
            <n-button
              size="small"
              secondary
              :loading="generatingDirectCandidate"
              :disabled="!currentChapter"
              @click="generateDirectCandidateDraft"
            >
              PP AI 生成候选稿
            </n-button>
            <n-button
              size="small"
              secondary
              :disabled="!currentChapter"
              @click="openWebWritingModal"
            >
              Web 写作
            </n-button>
            <n-button
              size="small"
              secondary
              :loading="mergingBranch"
              :disabled="!candidateBranchFilter.trim() || candidateBranchFilter.trim() === 'main'"
              @click="mergeCurrentBranchToMain"
            >
              合并到 main
            </n-button>
            <n-button size="small" secondary :loading="loadingCandidateDrafts" @click="loadCandidateDrafts">
              刷新
            </n-button>
          </n-space>
        </n-space>

        <n-card size="small" :bordered="false" class="candidate-ops-card">
          <n-space vertical :size="8">
            <n-space :size="6" wrap>
              <n-tag
                v-for="branch in candidateBranches"
                :key="`${branch.branch_name}-${branch.updated_at}`"
                size="small"
                round
                :type="branch.branch_name === candidateBranchFilter ? 'success' : 'default'"
              >
                {{ branch.branch_name }} · {{ branch.draft_count }}稿 / 已采纳{{ branch.accepted_count }}
              </n-tag>
              <n-tag size="small" round type="info">
                模型任务台账 {{ externalModelTasks.length }} 条
              </n-tag>
            </n-space>
            <n-space v-if="branchMemoryDiff" :size="6" wrap>
              <n-tag size="small" round type="warning">
                分支记忆差异：相似度 {{ Math.round(branchMemoryDiff.similarity * 100) }}%
              </n-tag>
              <n-tag
                v-for="item in branchMemoryDiff.memory_impacts"
                :key="`${item.label}-${item.detail}`"
                size="small"
                round
                :type="item.level === 'warning' ? 'warning' : item.level === 'error' ? 'error' : 'info'"
                :title="item.detail"
              >
                {{ item.label }}
              </n-tag>
            </n-space>
          </n-space>
        </n-card>

        <n-empty
          v-if="!loadingCandidateDrafts && candidateDrafts.length === 0"
          description="当前章节还没有候选稿"
        />

        <n-grid v-else :cols="2" :x-gap="16">
          <n-grid-item>
            <n-scrollbar style="max-height: 460px">
              <n-space vertical :size="12">
                <n-card
                  v-for="draft in candidateDrafts"
                  :key="draft.id"
                  size="small"
                  :bordered="true"
                  :class="{ 'candidate-card--active': selectedCandidateDraftId === draft.id }"
                >
                  <n-space vertical :size="8">
                    <n-space justify="space-between" align="center">
                      <n-space :size="6" align="center">
                        <n-tag size="small" round :type="candidateDraftSourceType(draft.source)">
                          {{ candidateDraftSourceLabel(draft.source) }}
                        </n-tag>
                        <n-tag size="small" round type="default">{{ draft.branch_name }}</n-tag>
                        <n-tag
                          size="small"
                          round
                          :type="draft.status === 'accepted' ? 'success' : draft.status === 'rejected' ? 'error' : 'warning'"
                        >
                          {{ draft.status }}
                        </n-tag>
                      </n-space>
                      <n-text depth="3" style="font-size: 11px">{{ formatDraftTime(draft.created_at) }}</n-text>
                    </n-space>
                    <n-text strong>{{ draft.title || `第${draft.chapter_number}章候选稿` }}</n-text>
                    <n-space v-if="candidateDraftFocusTags(draft).length" :size="6" wrap>
                      <n-tag
                        v-for="tag in candidateDraftFocusTags(draft)"
                        :key="`${draft.id}-${tag}`"
                        size="small"
                        round
                        type="info"
                      >
                        {{ tag }}
                      </n-tag>
                    </n-space>
                    <n-space v-if="candidateDraftLineageTags(draft).length" :size="6" wrap>
                      <n-tag
                        v-for="tag in candidateDraftLineageTags(draft)"
                        :key="`${draft.id}-lineage-${tag}`"
                        size="small"
                        round
                        type="success"
                      >
                        {{ tag }}
                      </n-tag>
                    </n-space>
                    <n-text depth="3" style="font-size: 12px; line-height: 1.6">
                      {{ draft.rationale || '无说明' }}
                    </n-text>
                    <n-space :size="8">
                      <n-button size="tiny" secondary @click="selectedCandidateDraftId = draft.id">
                        预览
                      </n-button>
                      <n-button
                        v-if="isCandidateRewriteTask(draft)"
                        size="tiny"
                        secondary
                        @click="handleGenerateFromCandidateTask(draft)"
                      >
                        按任务生成
                      </n-button>
                      <n-button
                        size="tiny"
                        type="primary"
                        :loading="acceptingCandidateDraftId === draft.id"
                        :disabled="draft.status === 'accepted'"
                        @click="handleAcceptCandidateDraft(draft.id)"
                      >
                        采纳为主稿
                      </n-button>
                      <n-button
                        size="tiny"
                        type="error"
                        secondary
                        :disabled="draft.status === 'rejected'"
                        @click="handleRejectCandidateDraft(draft.id)"
                      >
                        拒绝
                      </n-button>
                    </n-space>
                  </n-space>
                </n-card>
              </n-space>
            </n-scrollbar>
          </n-grid-item>

          <n-grid-item>
            <n-space vertical :size="10">
              <n-space justify="space-between" align="center">
                <n-text strong>候选稿预览</n-text>
                <n-button
                  v-if="selectedCandidateDraft"
                  size="tiny"
                  secondary
                  :loading="reviewingCandidateDraft"
                  @click="reviewSelectedCandidateDraft"
                >
                  审稿/记忆检查
                </n-button>
              </n-space>
              <n-alert
                v-if="selectedCandidateDraft && selectedCandidateDiffSummary"
                :type="selectedCandidateDiffSummary.changed ? 'info' : 'default'"
                :show-icon="false"
                style="font-size:12px"
              >
                与当前主稿对比：候选稿 {{ selectedCandidateDiffSummary.candidateWordCount }} 字，
                {{ selectedCandidateDiffSummary.wordDelta >= 0 ? '增加' : '减少' }}
                {{ Math.abs(selectedCandidateDiffSummary.wordDelta) }} 字，
                相似度 {{ selectedCandidateDiffSummary.similarityPercent }}%。
              </n-alert>
              <n-alert
                v-if="selectedCandidateDraft"
                type="success"
                :show-icon="false"
                style="font-size:12px"
              >
                采纳影响：{{ candidateDraftMemoryImpactHints(selectedCandidateDraft).join('；') }}。
              </n-alert>
              <n-space v-if="selectedCandidateDraft" :size="6" wrap>
                <n-tag
                  v-for="item in candidateDraftMemoryImpactPreview(selectedCandidateDraft)"
                  :key="`${selectedCandidateDraft.id}-impact-${item.label}`"
                  size="small"
                  round
                  :type="item.type"
                  :title="item.detail"
                >
                  {{ item.label }}
                </n-tag>
              </n-space>
              <n-alert
                v-if="selectedCandidateSupervisorReview && selectedCandidateSupervisorReview.draft_id === selectedCandidateDraft?.id"
                type="warning"
                :show-icon="false"
                style="font-size:12px;white-space:pre-wrap"
              >
                PP AI 检查：
                {{ selectedCandidateSupervisorReview.review }}
              </n-alert>
              <n-card v-if="selectedCandidateDraft && selectedCandidateParagraphDiff.length" size="small" title="段落级 diff">
                <n-space vertical :size="8">
                  <n-alert v-if="selectedCandidateCompare" type="info" :show-icon="false" style="font-size:12px">
                    A/B 对照：主稿 {{ selectedCandidateCompare.primary_word_count }} 字，
                    候选 {{ selectedCandidateCompare.candidate_word_count }} 字，
                    相似度 {{ Math.round(selectedCandidateCompare.similarity * 100) }}%。
                  </n-alert>
                  <n-space justify="space-between" align="center">
                    <n-text depth="3" style="font-size: 12px">
                      勾选候选段落后，可生成一版“部分采纳候选稿”，再走原采纳链路。
                    </n-text>
                    <n-button
                      size="tiny"
                      type="primary"
                      secondary
                      :disabled="selectedPartialParagraphIndexes.length === 0"
                      :loading="savingPartialCandidateDraft"
                      @click="savePartialCandidateDraft"
                    >
                      保存所选段落为候选稿
                    </n-button>
                  </n-space>
                  <n-scrollbar style="max-height: 320px">
                    <n-space vertical :size="8">
                      <div
                        v-for="item in selectedCandidateParagraphDiff"
                        :key="`${selectedCandidateDraft.id}-${item.index}`"
                        class="paragraph-diff-row"
                      >
                        <n-space justify="space-between" align="center">
                          <n-space :size="6" align="center">
                            <n-checkbox
                              :checked="selectedPartialParagraphIndexes.includes(item.index)"
                              :disabled="item.type === 'unchanged'"
                              @update:checked="togglePartialParagraph(item.index, $event)"
                            />
                            <n-tag size="small" round :type="paragraphDiffTagType(item.type)">
                              {{ paragraphDiffLabel(item.type) }}
                            </n-tag>
                            <n-text depth="3" style="font-size: 11px">
                              第 {{ item.index + 1 }} 段 · 相似度 {{ item.similarityPercent }}%
                            </n-text>
                          </n-space>
                        </n-space>
                        <n-grid :cols="2" :x-gap="8">
                          <n-grid-item>
                            <n-text depth="3" style="font-size: 11px">主稿</n-text>
                            <p class="paragraph-diff-text paragraph-diff-text--base">
                              {{ item.baseParagraph || '（无）' }}
                            </p>
                          </n-grid-item>
                          <n-grid-item>
                            <n-text depth="3" style="font-size: 11px">候选</n-text>
                            <p class="paragraph-diff-text paragraph-diff-text--candidate">
                              {{ item.candidateParagraph || '（删除该段）' }}
                            </p>
                          </n-grid-item>
                        </n-grid>
                      </div>
                    </n-space>
                  </n-scrollbar>
                </n-space>
              </n-card>
              <n-input
                :value="selectedCandidateDraft?.content || ''"
                type="textarea"
                readonly
                :autosize="{ minRows: 12, maxRows: 18 }"
                placeholder="选择左侧候选稿查看正文"
              />
            </n-space>
          </n-grid-item>
        </n-grid>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showCandidateDraftsModal = false">关闭</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showWebWritingModal"
      preset="card"
      title="Web 写作模式"
      style="width: min(920px, 96vw)"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <n-space vertical :size="14">
        <n-alert type="info" :show-icon="true" style="font-size: 13px">
          PP 只生成提示词和管理候选稿，不调用写作 API。你把提示词复制到 ChatGPT / Kimi / DeepSeek 网页，生成后把正文粘回这里保存为候选稿。
        </n-alert>

        <n-grid :cols="2" :x-gap="12">
          <n-grid-item>
            <n-form-item label="Web 模型标记" label-placement="top" :show-feedback="false">
              <n-input v-model:value="webWritingModelLabel" placeholder="例如 ChatGPT Web / Kimi Web / DeepSeek Web" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="候选分支" label-placement="top" :show-feedback="false">
              <n-input v-model:value="candidateBranchFilter" placeholder="main" />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <n-form-item label="给网页模型的额外要求" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="webWritingTaskPrompt"
            type="textarea"
            placeholder="例：按 2500 字左右写完整章节，保持 CoC 限制视角，少解释，多用物证推进。"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </n-form-item>

        <n-space justify="space-between" align="center">
          <n-text depth="3" style="font-size: 12px">
            当前章节：{{ currentChapter ? `第${currentChapter.number}章 ${currentChapter.title || ''}` : '未选择章节' }}
          </n-text>
          <n-space :size="8">
            <n-button
              secondary
              :loading="creatingWebWritingPrompt"
              :disabled="!currentChapter"
              @click="createWebWritingPrompt"
            >
              生成提示词
            </n-button>
            <n-button
              secondary
              :disabled="!webWritingPrompt.trim()"
              @click="copyWebWritingPrompt"
            >
              复制提示词
            </n-button>
          </n-space>
        </n-space>

        <n-form-item label="网页提示词" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="webWritingPrompt"
            type="textarea"
            readonly
            placeholder="点击“生成提示词”后出现，可复制到网页模型。"
            :autosize="{ minRows: 8, maxRows: 14 }"
          />
        </n-form-item>

        <n-form-item label="网页回稿正文" label-placement="top" :show-feedback="false">
          <n-input
            v-model:value="webWritingResponse"
            type="textarea"
            placeholder="把网页模型生成的完整章节正文粘贴到这里，再保存为候选稿。"
            :autosize="{ minRows: 8, maxRows: 16 }"
          />
        </n-form-item>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showWebWritingModal = false">关闭</n-button>
          <n-button
            type="primary"
            :loading="importingWebWritingDraft"
            :disabled="!currentChapter || !webWritingResponse.trim()"
            @click="importWebWritingResponseAsCandidate"
          >
            保存回稿为候选稿
          </n-button>
        </n-space>
      </template>
    </n-modal>

  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { resolveHttpUrl } from '../../api/config'
import {
  consumeGenerateChapterStream,
  analyzeScene,
  retrieveContext,
  previewChapterStrategy,
  reviewGeneratedChapterEditorially,
  precheckCocCognitionBoundary,
  rewriteOutlineByCocBoundary,
} from '../../api/workflow'
import type {
  CocCognitionPrecheckDTO,
  CocCognitionRewriteResultDTO,
  ChapterEditorialReviewDTO,
  ChapterStrategyPreviewDTO,
  ContextPreviewResult,
  GenerateChapterWorkflowResponse,
} from '../../api/workflow'
import { chapterApi } from '../../api/chapter'
import { novelproSuggestionsApi } from '../../api/novelproSuggestions'
import { styleBibleApi, type StyleProfileDetail, type StyleProfileMatchReportDTO } from '../../api/styleBible'
import type {
  BranchMemoryDiffResponse,
  CandidateBranchSummary,
  CandidateDraftCompareResponse,
  ChapterCandidateDraftDTO,
  ExternalModelTaskDTO,
  SupervisorReviewCandidateDraftResponse,
} from '../../api/chapter'
import { tensionApi } from '../../api/tools'
import type { TensionDiagnosis } from '../../api/tools'
import { useCandidateDraftBranchStore } from '../../stores/candidateDraftBranchStore'
import { useWorkbenchContextStore } from '../../stores/workbenchContextStore'
import {
  candidateDraftFocusTags,
  candidateDraftLineageTags,
  candidateDraftMemoryImpactHints,
  candidateDraftMemoryImpactPreview,
  candidateDraftRewritePrompt,
  candidateDraftSourceLabel,
  candidateDraftSourceType,
  isCandidateRewriteTask,
} from '../../utils/candidateDraftDisplay'
import {
  buildCandidateDraftDiffSummary,
  buildCandidateDraftParagraphDiff,
  buildPartialCandidateContent,
  type CandidateDraftParagraphDiffType,
} from '../../utils/candidateDraftDiff'
import { markExternalModelTaskAccepted } from '../../utils/externalModelTaskLedger'
import {
  buildPrecisionRewriteRationale,
  PRECISION_REWRITE_SOURCE,
} from '../../utils/precisionRewriteTask'
import CandidateDraftBranchSwitcher from './CandidateDraftBranchSwitcher.vue'
import ChapterElementPanel from './ChapterElementPanel.vue'
import ChapterContentPanel from './ChapterContentPanel.vue'
import ChapterStatusPanel from './ChapterStatusPanel.vue'
import PromptDetailPanel from './promptPlaza/PromptDetailPanel.vue'
const AutopilotPanel = defineAsyncComponent(() => import('../autopilot/AutopilotPanel.vue'))
const AutopilotDashboard = defineAsyncComponent(() => import('../autopilot/AutopilotDashboard.vue'))

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
const candidateDraftBranchStore = useCandidateDraftBranchStore()
const workbenchContextStore = useWorkbenchContextStore()

/** 辅助撰稿：编辑与章级工具；托管撰稿：驾驶舱 + 监控大盘 */
const workMode = ref<'assisted' | 'managed'>('managed')

// Tab 状态（仅辅助撰稿）
const activeTab = ref('editor')
const showGenerateModal = ref(false)
const showGenerationStyleModal = ref(false)
const showPrecisionRewriteModal = ref(false)
const showCandidateDraftsModal = ref(false)
const showWebWritingModal = ref(false)
const generateOutline = ref('')
const generatedContent = ref('')
/** 弹窗内选中的目标章节（与 useWorkbench 映射一致：id === number） */
const generateTargetChapterId = ref<number | null>(null)
const generateStyleProfileId = ref<string | null>(null)
const generateSceneType = ref('')
const styleProfiles = ref<StyleProfileDetail[]>([])
const loadingStyleProfiles = ref(false)
const styleMatchReport = ref<StyleProfileMatchReportDTO | null>(null)
const styleMatchLoading = ref(false)
const generateInProgress = ref(false)
const lastWorkflowResult = ref<GenerateChapterWorkflowResponse | null>(null)
const lastQcChapterNumber = ref<number | null>(null)
const chapterStrategy = ref<ChapterStrategyPreviewDTO | null>(null)
const loadingChapterStrategy = ref(false)
const cocPrecheckLoading = ref(false)
const cocRewriteLoading = ref(false)
const cocPrecheckResult = ref<CocCognitionPrecheckDTO | null>(null)
const cocRewriteResult = ref<CocCognitionRewriteResultDTO | null>(null)
const cocRewriteMode = ref<'conservative' | 'aggressive'>('conservative')
const cocRewriteStyle = ref<'generic' | 'suspense' | 'coc'>('generic')
const ignoreCocPrecheckBlockOnce = ref(false)
const editorialReview = ref<ChapterEditorialReviewDTO | null>(null)
const loadingEditorialReview = ref(false)
const blurSceneCache = ref<Record<string, unknown> | undefined>(undefined)
const outlineBlurAnalyzing = ref(false)
const streamPhaseLabel = ref('')
const streamProgressPct = ref(0)
const streamStats = ref({ chars: 0, estimated_tokens: 0, chunks: 0 })
const targetWordCount = ref(2500)
const wordTolerancePercent = ref(5)
const longDraftMode = ref(false)
const longDraftSplitCount = ref(2)
const directWritingMode = ref(false)
const directLightPolish = ref(false)
const candidateDrafts = ref<ChapterCandidateDraftDTO[]>([])
const loadingCandidateDrafts = ref(false)
const candidateBranches = ref<CandidateBranchSummary[]>([])
const selectedCandidateCompare = ref<CandidateDraftCompareResponse | null>(null)
const selectedCandidateSupervisorReview = ref<SupervisorReviewCandidateDraftResponse | null>(null)
const branchMemoryDiff = ref<BranchMemoryDiffResponse | null>(null)
const externalModelTasks = ref<ExternalModelTaskDTO[]>([])
const webWritingModelLabel = ref('ChatGPT Web')
const webWritingTaskPrompt = ref('')
const webWritingPrompt = ref('')
const webWritingResponse = ref('')
const webWritingTask = ref<ExternalModelTaskDTO | null>(null)
const savingCandidateDraft = ref(false)
const savingPrecisionRewriteTask = ref(false)
const suggestingPrecisionRewriteTask = ref(false)
const savingPartialCandidateDraft = ref(false)
const mergingBranch = ref(false)
const generatingDirectCandidate = ref(false)
const generatingEditorialPolishCandidate = ref(false)
const creatingWebWritingPrompt = ref(false)
const importingWebWritingDraft = ref(false)
const reviewingCandidateDraft = ref(false)
const acceptingCandidateDraftId = ref<string | null>(null)
const selectedCandidateDraftId = ref<string | null>(null)
const selectedPartialParagraphIndexes = ref<number[]>([])
const lastConsumedCandidateRewriteVersion = ref(0)
const lastConsumedCandidateExecutionVersion = ref(0)
const activeCandidateRewriteTask = ref<ChapterCandidateDraftDTO | null>(null)
const candidateBranchFilter = computed({
  get: () => candidateDraftBranchStore.getActiveBranch(props.slug),
  set: (value: string) => candidateDraftBranchStore.setActiveBranch(props.slug, value),
})
const precisionRewriteObjective = ref('降低 AI 味')
const precisionRewriteTargetExcerpt = ref('')
const precisionRewriteInstruction = ref('')
const precisionRewriteObjectiveOptions = [
  { label: '降低 AI 味', value: '降低 AI 味' },
  { label: '更像角色本人', value: '更像角色本人' },
  { label: '增强张力', value: '增强张力' },
  { label: '更克制', value: '更克制' },
  { label: '更暧昧', value: '更暧昧' },
  { label: '保留事件只改表达', value: '保留事件只改表达' },
]
const cocRewriteModeOptions = [
  { label: '保守改写', value: 'conservative' },
  { label: '激进改写', value: 'aggressive' },
]
const cocRewriteStyleOptions = [
  { label: '通用', value: 'generic' },
  { label: '悬疑向', value: 'suspense' },
  { label: 'CoC向', value: 'coc' },
]
const targetWordRangeHint = computed(() => {
  const target = Math.max(800, Math.min(12000, Number(targetWordCount.value || 2500)))
  const tolerance = Math.max(2, Math.min(20, Number(wordTolerancePercent.value || 5)))
  const delta = Math.max(80, Math.floor(target * (tolerance / 100)))
  return `容差 ${tolerance}%：约 ${Math.max(500, target - delta)}-${target + delta} 字`
})
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

function maybeEmitDeskRefresh(status: Record<string, unknown> | null | undefined) {
  const next = deskSnapFromAutopilot(status)
  if (next === '') return
  if (lastAutopilotDeskSnap.value === null) {
    lastAutopilotDeskSnap.value = next
    return
  }
  if (lastAutopilotDeskSnap.value === next) return
  lastAutopilotDeskSnap.value = next
  emit('chapterUpdated')
}

const handleAutopilotStatusChange = (status: any) => {
  autopilotStatus.value = status
  maybeEmitDeskRefresh(status)
}

/** SSE 已广播「进入待审阅」时立即拉 desk/结构树；与 /status 轮询并行，避免日志先变、侧栏仍旧 */
let autopilotStreamDeskDebounce: ReturnType<typeof setTimeout> | null = null
function handleAutopilotDeskRefreshFromStream() {
  if (autopilotStreamDeskDebounce) clearTimeout(autopilotStreamDeskDebounce)
  autopilotStreamDeskDebounce = setTimeout(() => {
    autopilotStreamDeskDebounce = null
    emit('chapterUpdated')
  }, 400)
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

/** 辅助撰稿下不挂载驾驶舱，需独立轮询托管状态以支持「运行中只读」 */
let assistedAutopilotPollTimer: ReturnType<typeof setInterval> | null = null
/** 该书在库中不存在(404)时不再轮询 /autopilot/.../status */
let assistedAutopilot404 = false

function clearAssistedAutopilotPoll() {
  if (assistedAutopilotPollTimer != null) {
    clearInterval(assistedAutopilotPollTimer)
    assistedAutopilotPollTimer = null
  }
}

function handleVisibilityChange() {
  if (document.hidden) {
    clearAssistedAutopilotPoll()
  } else if (workMode.value === 'assisted') {
    void pollAutopilotStatusWhileAssisted()
    assistedAutopilotPollTimer = setInterval(
      () => void pollAutopilotStatusWhileAssisted(),
      4000
    )
  }
}

async function pollAutopilotStatusWhileAssisted() {
  if (assistedAutopilot404) return
  try {
    const res = await fetch(resolveHttpUrl(`/api/v1/autopilot/${props.slug}/status`))
    if (res.status === 404) {
      assistedAutopilot404 = true
      clearAssistedAutopilotPoll()
      return
    }
    if (res.ok) {
      const json = await res.json()
      autopilotStatus.value = json
      maybeEmitDeskRefresh(json)
    }
  } catch {
    /* 忽略 */
  }
}

watch(
  () => props.slug,
  () => {
    lastAutopilotDeskSnap.value = null
    assistedAutopilot404 = false
    if (workMode.value === 'assisted') {
      clearAssistedAutopilotPoll()
      void pollAutopilotStatusWhileAssisted()
      assistedAutopilotPollTimer = setInterval(
        () => void pollAutopilotStatusWhileAssisted(),
        4000
      )
    }
  }
)

watch(
  () => workMode.value,
  (mode) => {
    clearAssistedAutopilotPoll()
    if (mode === 'assisted') {
      void pollAutopilotStatusWhileAssisted()
      assistedAutopilotPollTimer = setInterval(
        () => void pollAutopilotStatusWhileAssisted(),
        4000
      )
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
const avoidCompressedExpression = ref(true)
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

const openPrecisionRewriteModal = () => {
  if (!currentChapter.value) return
  precisionRewriteObjective.value = '降低 AI 味'
  precisionRewriteTargetExcerpt.value = ''
  precisionRewriteInstruction.value = ''
  showPrecisionRewriteModal.value = true
}

const createPrecisionRewriteTask = async () => {
  const chapter = currentChapter.value
  if (!chapter) return
  if (!chapterContent.value.trim()) {
    message.warning('当前章节正文为空，无法创建精修任务')
    return
  }

  savingPrecisionRewriteTask.value = true
  try {
    const rationale = buildPrecisionRewriteRationale({
      objective: precisionRewriteObjective.value,
      instruction: precisionRewriteInstruction.value,
      targetExcerpt: precisionRewriteTargetExcerpt.value,
    })
    const draft = await chapterApi.createCandidateDraft(props.slug, chapter.number, {
      source: PRECISION_REWRITE_SOURCE,
      title: `${chapter.title || `第${chapter.number}章`} 精细改稿任务`,
      content: chapterContent.value,
      rationale,
      branch_name: candidateBranchFilter.value.trim() || 'main',
      metadata: {
        rewrite_focus: 'precision-rewrite',
        precision_objective: precisionRewriteObjective.value,
        target_excerpt: precisionRewriteTargetExcerpt.value,
        instruction: precisionRewriteInstruction.value,
        triggered_by: 'precision-rewrite-modal',
      },
    })
    showPrecisionRewriteModal.value = false
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = draft.id
    showCandidateDraftsModal.value = true
    message.success('已创建精细改稿任务')
  } catch {
    message.error('创建精细改稿任务失败')
  } finally {
    savingPrecisionRewriteTask.value = false
  }
}

function suggestionText(fields: Record<string, unknown>, key: string) {
  const value = fields[key]
  if (value == null) return ''
  return String(value)
}

const suggestPrecisionRewriteTask = async () => {
  const chapter = currentChapter.value
  if (!chapter || !chapterContent.value.trim()) return
  suggestingPrecisionRewriteTask.value = true
  try {
    const result = await novelproSuggestionsApi.suggestFields(props.slug, {
      suggestion_type: 'precision_rewrite',
      chapter_number: chapter.number,
      fields: ['objective', 'target_excerpt', 'instruction'],
      target: {
        chapter_title: chapter.title,
        current_word_count: chapterContent.value.length,
      },
      current_values: {
        objective: precisionRewriteObjective.value,
        target_excerpt: precisionRewriteTargetExcerpt.value,
        instruction: precisionRewriteInstruction.value,
      },
      instruction: '根据当前章节、连续性提醒、OOC 风险和战力提醒，生成精细改稿任务建议。不要改正文，只生成任务表单。',
    })
    precisionRewriteObjective.value = suggestionText(result.fields, 'objective') || precisionRewriteObjective.value
    precisionRewriteTargetExcerpt.value = suggestionText(result.fields, 'target_excerpt') || precisionRewriteTargetExcerpt.value
    precisionRewriteInstruction.value = suggestionText(result.fields, 'instruction') || precisionRewriteInstruction.value
    message.success(result.rationale || '已生成精修任务建议')
  } catch {
    message.error('生成精修任务建议失败')
  } finally {
    suggestingPrecisionRewriteTask.value = false
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

const styleProfileOptions = computed(() =>
  styleProfiles.value.map(item => ({
    label: `${item.profile.name} · ${item.cards.filter(card => card.enabled).length}卡`,
    value: item.profile.id,
  }))
)

const styleMatchIssueText = computed(() => {
  const issues = styleMatchReport.value?.issues ?? []
  return issues.slice(0, 3).join('；')
})

const modalTargetChapter = computed(() => {
  const id = generateTargetChapterId.value
  if (id == null) return null
  return props.chapters.find(ch => ch.id === id) ?? null
})

async function loadStyleProfilesForGeneration() {
  loadingStyleProfiles.value = true
  try {
    styleProfiles.value = await styleBibleApi.listProfiles({ novel_id: props.slug, status: 'active' })
  } catch {
    styleProfiles.value = []
  } finally {
    loadingStyleProfiles.value = false
  }
}

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

function applyCocManualStructureTemplate() {
  const chapter = modalTargetChapter.value || currentChapter.value
  const chapterNumber = chapter?.number || 1
  const chapterTitle = chapter?.title || '未命名章节'
  generateOutline.value = [
    `第${chapterNumber}章：${chapterTitle}`,
    '',
    '【Bible一致性核对（写作前必须遵守）】',
    '- 只使用 Bible 中已存在的主角团、地点、世界规则与人物关系；如果需要新增人物/地点，先写成临时角色/临时地点，不直接改主角团固定席位。',
    '- 白雨翔、许照、周闻笙、陈泊舟为固定主角团；可失联、受伤、互疑或遗忘关系，但不能无铺垫替换成员。',
    '- 每名主角的固定核心道具必须保持当前持有人、状态与代价规则；非核心道具只能在本任务内使用，带出前必须转为证物。',
    '',
    '【本章戏剧任务】',
    '- 角色目标：',
    '- 主要阻碍：',
    '- 读者期待：',
    '- 本章结尾钩子：',
    '',
    '【场景推进表】',
    '1. 场景一：',
    '   - 目标：',
    '   - 阻力：',
    '   - 信息变化：',
    '   - 人物关系变化：',
    '   - 道具变化：',
    '   - 钩子：',
    '2. 场景二：',
    '   - 目标：',
    '   - 阻力：',
    '   - 信息变化：',
    '   - 人物关系变化：',
    '   - 道具变化：',
    '   - 钩子：',
    '',
    '【CoC线索与认知边界】',
    '- 本章新增线索候选：',
    '- 读者可知道：',
    '- 角色可知道：',
    '- 作者真相/禁止直出：',
    '- 误导点：',
    '- 需要章后确认是否登记到 CoC线索/正典：',
    '',
    '【理智/认知代价】',
    '- 谁受到影响：',
    '- 具体表现：记忆缺口 / 感官错位 / 熟人陌生化 / 时间感错误 / 判断偏移',
    '- 是否影响下章：',
    '',
    '【写作限制】',
    '- 限制视角，不全知解释。',
    '- 不直接说出作者真相，只写角色能看见、听见、推断或误解的证据。',
    '- 正文必须服务于冲突、线索、人物关系和结尾追读。',
  ].join('\n')
  cocPrecheckResult.value = null
  cocRewriteResult.value = null
  blurSceneCache.value = undefined
  message.success('已套用 CoC 手动结构规划模板')
}

function editorialScoreLabel(key: string) {
  const map: Record<string, string> = {
    opening: '开头',
    conflict: '冲突',
    character: '人物',
    dialogue: '对白',
    hook: '追读',
    pacing: '节奏',
    showing: '展示',
  }
  return map[key] || key
}

async function resolveSceneDirectorResultForModal(chapterNumber: number) {
  let sceneDirectorResult: Record<string, unknown> | undefined = blurSceneCache.value
  if (useSceneDirector.value && !sceneDirectorResult) {
    analyzingScene.value = true
    try {
      const outline = generateOutline.value || `第${chapterNumber}章：承接前情，推进主线`
      const analysis = await analyzeScene(props.slug, chapterNumber, outline)
      sceneDirectorResult = analysis as Record<string, unknown>
      blurSceneCache.value = sceneDirectorResult
    } catch (e: unknown) {
      sceneDirectorError.value = e instanceof Error ? e.message : '分析失败'
    } finally {
      analyzingScene.value = false
    }
  }
  return sceneDirectorResult
}

async function runCocPrecheckForModal(options?: { silent?: boolean }) {
  const target = modalTargetChapter.value
  if (!target) return null
  const outline = generateOutline.value.trim() || `第${target.number}章：承接前情，推进主线`
  cocPrecheckLoading.value = true
  try {
    const result = await precheckCocCognitionBoundary(props.slug, target.number, outline)
    cocPrecheckResult.value = result
    if (!options?.silent) {
      if (result.checked && result.allow_generate === false) {
        const detail = result.blocking_issues?.[0] || '命中认知边界阻断规则'
        message.error(`预检阻断：${detail}`)
      } else if (result.checked && (result.warnings?.length || 0) > 0) {
        message.warning(`预检提醒：${result.warnings[0]}`)
      } else {
        message.success('预检通过')
      }
    }
    return result
  } catch {
    cocPrecheckResult.value = null
    if (!options?.silent) {
      message.warning('预检失败，已跳过')
    }
    return null
  } finally {
    cocPrecheckLoading.value = false
  }
}

async function rewriteOutlineForCocBoundaryForModal() {
  const target = modalTargetChapter.value
  if (!target) return
  const outline = generateOutline.value.trim() || `第${target.number}章：承接前情，推进主线`
  cocRewriteLoading.value = true
  try {
    const result = await rewriteOutlineByCocBoundary(
      props.slug,
      target.number,
      outline,
      cocRewriteMode.value,
      cocRewriteStyle.value,
    )
    cocRewriteResult.value = result
    if (result.changed) {
      generateOutline.value = result.rewritten_outline
      cocPrecheckResult.value = result.precheck_after
      ignoreCocPrecheckBlockOnce.value = false
      message.success(`已完成${result.rewrite_mode === 'aggressive' ? '激进' : '保守'}安全改写，并复检通过`)
    } else {
      cocPrecheckResult.value = result.precheck_after
      message.success('当前大纲无需改写')
    }
  } catch {
    message.error('安全改写失败，请稍后重试')
  } finally {
    cocRewriteLoading.value = false
  }
}

async function previewChapterStrategyForModal() {
  const target = modalTargetChapter.value
  if (!target) {
    message.warning('请选择目标章节')
    return
  }
  loadingChapterStrategy.value = true
  try {
    const sceneDirectorResult = await resolveSceneDirectorResultForModal(target.number)
    const defaultOutline = `第${target.number}章：承接前情，推进主线`
    chapterStrategy.value = await previewChapterStrategy(props.slug, target.number, {
      outline: generateOutline.value || defaultOutline,
      scene_director_result: sceneDirectorResult,
      style_profile_id: generateStyleProfileId.value || '',
      scene_type: generateSceneType.value.trim(),
      target_word_count: targetWordCount.value || undefined,
      word_tolerance_percent: wordTolerancePercent.value || 5,
    })
    message.success('本章写作策略已生成')
  } catch {
    message.error('生成写作策略失败，请检查模型配置')
  } finally {
    loadingChapterStrategy.value = false
  }
}

async function runEditorialReviewForModal(chapterNumber: number, outline: string, content: string) {
  if (!content.trim()) return
  loadingEditorialReview.value = true
  try {
    editorialReview.value = await reviewGeneratedChapterEditorially(props.slug, chapterNumber, {
      outline,
      content,
      chapter_strategy: chapterStrategy.value,
    })
  } catch {
    editorialReview.value = null
    message.warning('主编审稿失败，请稍后重试')
  } finally {
    loadingEditorialReview.value = false
  }
}

async function rerunEditorialReview() {
  const target = modalTargetChapter.value
  if (!target || !generatedContent.value.trim()) return
  const defaultOutline = `第${target.number}章：承接前情，推进主线`
  await runEditorialReviewForModal(target.number, generateOutline.value || defaultOutline, generatedContent.value)
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
  void runCocPrecheckForModal({ silent: true })
}

function clearWorkflowQc() {
  lastWorkflowResult.value = null
  lastQcChapterNumber.value = null
}

function clearChapterStrategy() {
  chapterStrategy.value = null
}

function clearGeneratedDraft() {
  generatedContent.value = ''
  styleMatchReport.value = null
  editorialReview.value = null
  clearWorkflowQc()
}

watch(generateTargetChapterId, () => {
  blurSceneCache.value = undefined
  contextPreview.value = null
  chapterStrategy.value = null
  editorialReview.value = null
  cocPrecheckResult.value = null
  cocRewriteResult.value = null
  cocRewriteMode.value = 'conservative'
  cocRewriteStyle.value = 'generic'
  ignoreCocPrecheckBlockOnce.value = false
})

watch(
  () =>
    [
      generateOutline.value,
      generateSceneType.value,
      generateStyleProfileId.value,
      targetWordCount.value,
      wordTolerancePercent.value,
      longDraftMode.value,
      longDraftSplitCount.value,
    ] as const,
  () => {
    chapterStrategy.value = null
    editorialReview.value = null
    cocPrecheckResult.value = null
    cocRewriteResult.value = null
    ignoreCocPrecheckBlockOnce.value = false
  }
)

watch(showGenerateModal, (shown) => {
  if (shown) {
    void loadStyleProfilesForGeneration()
    cocPrecheckResult.value = null
    cocRewriteResult.value = null
    cocRewriteMode.value = 'conservative'
    cocRewriteStyle.value = 'generic'
    ignoreCocPrecheckBlockOnce.value = false
  }
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

const selectedCandidateDraft = computed(() => {
  if (!selectedCandidateDraftId.value) return null
  return candidateDrafts.value.find(draft => draft.id === selectedCandidateDraftId.value) || null
})

const selectedCandidateDiffSummary = computed(() => {
  if (!selectedCandidateDraft.value) return null
  return buildCandidateDraftDiffSummary(
    chapterContent.value,
    selectedCandidateDraft.value.content || '',
  )
})

const selectedCandidateParagraphDiff = computed(() => {
  if (!selectedCandidateDraft.value) return []
  return buildCandidateDraftParagraphDiff(
    chapterContent.value,
    selectedCandidateDraft.value.content || '',
  )
})

function paragraphDiffLabel(type: CandidateDraftParagraphDiffType) {
  if (type === 'added') return '新增'
  if (type === 'removed') return '删除'
  if (type === 'modified') return '改写'
  return '未变'
}

function paragraphDiffTagType(type: CandidateDraftParagraphDiffType) {
  if (type === 'added') return 'success'
  if (type === 'removed') return 'error'
  if (type === 'modified') return 'warning'
  return 'default'
}

function togglePartialParagraph(index: number, checked: boolean) {
  if (checked) {
    selectedPartialParagraphIndexes.value = Array.from(
      new Set([...selectedPartialParagraphIndexes.value, index]),
    ).sort((a, b) => a - b)
    return
  }
  selectedPartialParagraphIndexes.value = selectedPartialParagraphIndexes.value.filter(
    item => item !== index,
  )
}

const hasChanges = computed(() => {
  return chapterContent.value !== originalContent.value
})

const wordCount = computed(() => {
  return chapterContent.value.length
})

// 监听传入的章节内容变化
watch(() => props.chapterContent, (newContent) => {
  chapterContent.value = newContent
  originalContent.value = newContent
}, { immediate: true })

watch(currentChapter, (chapter) => {
  candidateDrafts.value = []
  selectedCandidateDraftId.value = null
  if (chapter) {
    void loadCandidateDrafts()
  }
}, { immediate: true })

watch(candidateBranchFilter, () => {
  if (!currentChapter.value) return
  void loadCandidateDrafts()
})

watch(selectedCandidateDraftId, () => {
  selectedPartialParagraphIndexes.value = []
  void loadSelectedCandidateCompare()
})

watch(
  () => [workbenchContextStore.candidateRewriteSeedVersion, props.currentChapterId] as const,
  () => {
    void applyCandidateRewriteSeed()
  },
)

watch(
  () => [workbenchContextStore.candidateRewriteExecutionVersion, props.currentChapterId] as const,
  () => {
    applyCandidateRewriteExecution()
  },
)

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
  chapterStrategy.value = null
  editorialReview.value = null
  cocPrecheckResult.value = null
  cocRewriteResult.value = null
  cocRewriteMode.value = 'conservative'
  cocRewriteStyle.value = 'generic'
  ignoreCocPrecheckBlockOnce.value = false
  activeCandidateRewriteTask.value = null
  contextPreview.value = null
  blurSceneCache.value = undefined
  showGenerateModal.value = true
}

const formatDraftTime = (value: string) => {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const loadCandidateDrafts = async () => {
  if (!currentChapter.value) return
  loadingCandidateDrafts.value = true
  try {
    const drafts = await chapterApi.listCandidateDrafts(
      props.slug,
      currentChapter.value.number,
      candidateBranchFilter.value.trim() || undefined,
    )
    candidateDrafts.value = drafts
    candidateBranches.value = await chapterApi.listCandidateBranches(
      props.slug,
      currentChapter.value.number,
    ).catch(() => [])
    externalModelTasks.value = await chapterApi.listExternalModelTasks(
      props.slug,
      currentChapter.value.number,
    ).catch(() => [])
    branchMemoryDiff.value = await chapterApi.getBranchMemoryDiff(
      props.slug,
      currentChapter.value.number,
      candidateBranchFilter.value.trim() || 'main',
      'main',
    ).catch(() => null)
    if (!selectedCandidateDraftId.value || !drafts.some(d => d.id === selectedCandidateDraftId.value)) {
      selectedCandidateDraftId.value = drafts[0]?.id ?? null
    }
  } catch {
    candidateDrafts.value = []
    candidateBranches.value = []
    externalModelTasks.value = []
    branchMemoryDiff.value = null
    selectedCandidateDraftId.value = null
    message.error('加载候选稿失败')
  } finally {
    loadingCandidateDrafts.value = false
  }
}

const openCandidateDrafts = async () => {
  if (!currentChapter.value) return
  showCandidateDraftsModal.value = true
  await loadCandidateDrafts()
}

const loadSelectedCandidateCompare = async () => {
  const chapter = currentChapter.value
  const draft = selectedCandidateDraft.value
  if (!chapter || !draft) {
    selectedCandidateCompare.value = null
    return
  }
  selectedCandidateCompare.value = await chapterApi.compareCandidateDraft(
    props.slug,
    chapter.number,
    draft.id,
  ).catch(() => null)
}

const mergeCurrentBranchToMain = async () => {
  const chapter = currentChapter.value
  const sourceBranch = candidateBranchFilter.value.trim()
  if (!chapter || !sourceBranch || sourceBranch === 'main') {
    message.warning('请先切到非 main 分支再合并')
    return
  }
  mergingBranch.value = true
  try {
    const draft = await chapterApi.mergeCandidateBranch(
      props.slug,
      chapter.number,
      sourceBranch,
      'main',
      'latest_candidate',
    )
    candidateBranchFilter.value = 'main'
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = draft.id
    message.success('已生成合并候选稿，请审阅后再采纳')
  } catch {
    message.error('分支合并失败')
  } finally {
    mergingBranch.value = false
  }
}

const generateDirectCandidateDraft = async () => {
  const chapter = currentChapter.value
  if (!chapter) return
  const outline = generateOutline.value.trim() || `第${chapter.number}章：${chapter.title || '承接前情，推进主线'}`
  generatingDirectCandidate.value = true
  try {
    const result = await chapterApi.generateCandidateDraft(props.slug, {
      chapter_number: chapter.number,
      outline,
      current_content: chapterContent.value,
      branch_name: candidateBranchFilter.value.trim() || 'main',
      title: `${chapter.title || `第${chapter.number}章`} PP AI 候选稿`,
      source: 'direct-model',
      model_label: 'PP 当前 AI',
      llm_profile_id: '',
      task_prompt: activeCandidateRewriteTask.value
        ? candidateDraftRewritePrompt(activeCandidateRewriteTask.value)
        : outline,
    })
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = result.draft.id
    showCandidateDraftsModal.value = true
    message.success('PP AI 已生成候选稿')
  } catch {
    message.error('PP AI 生成候选稿失败，请检查 LLM 控制面板配置')
  } finally {
    generatingDirectCandidate.value = false
  }
}

const generateEditorialPolishCandidate = async () => {
  const target = modalTargetChapter.value
  if (!target || !generatedContent.value.trim() || !editorialReview.value) {
    message.warning('需要先完成正文生成和主编审稿')
    return
  }

  const outline = generateOutline.value.trim() || `第${target.number}章：${target.title || '承接前情，推进主线'}`
  generatingEditorialPolishCandidate.value = true
  try {
    const result = await chapterApi.generateEditorialPolishCandidate(props.slug, {
      chapter_number: target.number,
      outline,
      current_content: generatedContent.value,
      editorial_review: editorialReview.value,
      target_word_count: targetWordCount.value || 2500,
      branch_name: candidateBranchFilter.value.trim() || 'main',
      title: `${target.title || `第${target.number}章`} 主编精修候选稿`,
      model_label: 'PP 写作 AI',
      max_tokens: Math.min(4096, Math.max(1800, Math.ceil((targetWordCount.value || 2500) * 1.6))),
    })
    message.success('已按主编审稿生成精修候选稿')
    if (currentChapter.value?.number === target.number) {
      await loadCandidateDrafts()
      selectedCandidateDraftId.value = result.draft.id
      showCandidateDraftsModal.value = true
    }
  } catch {
    message.error('生成精修候选稿失败，请检查写作模型配置')
  } finally {
    generatingEditorialPolishCandidate.value = false
  }
}

const openWebWritingModal = () => {
  const chapter = currentChapter.value
  if (!chapter) {
    message.warning('请先选择章节')
    return
  }
  if (!webWritingTaskPrompt.value.trim()) {
    webWritingTaskPrompt.value = `生成一版约 ${targetWordCount.value || 2500} 字的完整章节正文；保留既有设定、角色口吻、伏笔和道具状态。`
  }
  webWritingPrompt.value = ''
  webWritingResponse.value = ''
  webWritingTask.value = null
  showWebWritingModal.value = true
}

const createWebWritingPrompt = async () => {
  const chapter = currentChapter.value
  if (!chapter) return
  const outline = generateOutline.value.trim() || `第${chapter.number}章：${chapter.title || '承接前情，推进主线'}`
  creatingWebWritingPrompt.value = true
  try {
    const result = await chapterApi.createWebWritingPrompt(props.slug, {
      chapter_number: chapter.number,
      outline,
      current_content: chapterContent.value,
      model_label: webWritingModelLabel.value.trim() || 'Web 写作',
      task_prompt: webWritingTaskPrompt.value.trim(),
    })
    webWritingPrompt.value = result.prompt
    webWritingTask.value = result.task
    externalModelTasks.value = await chapterApi.listExternalModelTasks(
      props.slug,
      chapter.number,
    ).catch(() => externalModelTasks.value)
    message.success('Web 写作提示词已生成')
  } catch {
    message.error('生成 Web 写作提示词失败')
  } finally {
    creatingWebWritingPrompt.value = false
  }
}

const copyWebWritingPrompt = async () => {
  if (!webWritingPrompt.value.trim()) return
  try {
    await navigator.clipboard.writeText(webWritingPrompt.value)
    message.success('提示词已复制')
  } catch {
    message.error('复制失败，请手动选中复制')
  }
}

const importWebWritingResponseAsCandidate = async () => {
  const chapter = currentChapter.value
  if (!chapter || !webWritingResponse.value.trim()) return

  importingWebWritingDraft.value = true
  try {
    const draft = await chapterApi.createCandidateDraft(props.slug, chapter.number, {
      source: 'external-model',
      title: `${chapter.title || `第${chapter.number}章`} ${webWritingModelLabel.value || 'Web'} 回稿`,
      content: webWritingResponse.value.trim(),
      rationale: `Web 写作回稿：${webWritingModelLabel.value || 'Web 写作'}`,
      branch_name: candidateBranchFilter.value.trim() || 'main',
      metadata: {
        external_model: webWritingModelLabel.value || 'Web 写作',
        web_writing_task_id: webWritingTask.value?.id || '',
        prompt: webWritingPrompt.value,
      },
    })
    if (webWritingTask.value?.id) {
      await chapterApi.upsertExternalModelTask(props.slug, {
        id: webWritingTask.value.id,
        chapter_number: chapter.number,
        model: webWritingModelLabel.value || webWritingTask.value.model || 'Web 写作',
        prompt: webWritingPrompt.value || webWritingTask.value.prompt,
        instruction: webWritingTaskPrompt.value || webWritingTask.value.instruction,
        candidate_draft_id: draft.id,
        response_preview: draft.content.slice(0, 160),
        status: 'imported',
        execution_mode: 'web_copy_paste',
      })
    }
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = draft.id
    showWebWritingModal.value = false
    showCandidateDraftsModal.value = true
    message.success('Web 回稿已保存为候选稿')
  } catch {
    message.error('保存 Web 回稿失败')
  } finally {
    importingWebWritingDraft.value = false
  }
}

const reviewSelectedCandidateDraft = async () => {
  const chapter = currentChapter.value
  const draft = selectedCandidateDraft.value
  if (!chapter || !draft) return

  reviewingCandidateDraft.value = true
  try {
    const result = await chapterApi.reviewCandidateDraft(props.slug, chapter.number, draft.id, {
      model_label: 'PP 当前 AI',
      llm_profile_id: '',
      focus: '检查记忆影响、连续性风险、战力崩坏风险、必须保留事实和采纳建议。',
    })
    selectedCandidateSupervisorReview.value = result
    externalModelTasks.value = await chapterApi.listExternalModelTasks(
      props.slug,
      chapter.number,
    ).catch(() => externalModelTasks.value)
    message.success('PP AI 检查完成')
  } catch {
    message.error('PP AI 检查失败，请检查 LLM 控制面板配置')
  } finally {
    reviewingCandidateDraft.value = false
  }
}

const applyCandidateRewriteSeed = async () => {
  const version = workbenchContextStore.candidateRewriteSeedVersion
  const seed = workbenchContextStore.candidateRewriteSeed
  const chapter = currentChapter.value
  if (!seed || !chapter) return
  if (seed.slug !== props.slug || seed.chapterNumber !== chapter.number) return
  if (version <= lastConsumedCandidateRewriteVersion.value) return

  lastConsumedCandidateRewriteVersion.value = version

  const baseContent = (seed.content ?? chapterContent.value).trim()
  if (!baseContent) {
    message.warning('当前章节正文为空，暂时无法创建候选改稿')
    return
  }

  savingCandidateDraft.value = true
  try {
    const draft = await chapterApi.createCandidateDraft(props.slug, chapter.number, {
      source: seed.source,
      title: seed.title || `${chapter.title || `第${chapter.number}章`} 候选改稿`,
      content: baseContent,
      rationale: seed.rationale,
      branch_name: candidateBranchFilter.value.trim() || 'main',
      metadata: {
        ...(seed.metadata || {}),
        triggered_by: 'continuity-panel',
      },
    })
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = draft.id
    showCandidateDraftsModal.value = true
    activeTab.value = 'editor'
    message.success('已根据连续性提醒创建候选改稿')
  } catch {
    message.error('创建候选改稿失败')
  } finally {
    savingCandidateDraft.value = false
  }
}

const handleSaveGeneratedAsCandidate = async () => {
  const target = modalTargetChapter.value
  if (!target || !generatedContent.value.trim()) {
    message.warning('没有可保存的候选正文')
    return
  }
  savingCandidateDraft.value = true
  try {
    const rewriteTask = activeCandidateRewriteTask.value
    const draft = await chapterApi.createCandidateDraft(props.slug, target.number, {
      source: rewriteTask?.source || 'workbench-generate',
      title: rewriteTask
        ? `${target.title || `第${target.number}章`} 改稿候选`
        : `${target.title || `第${target.number}章`} 候选稿`,
      content: generatedContent.value,
      rationale: rewriteTask
        ? `按候选改稿任务生成：${rewriteTask.rationale || candidateDraftSourceLabel(rewriteTask.source)}`
        : generateOutline.value.trim() ? `生成大纲：${generateOutline.value.trim()}` : '来自工作台快速生成',
      branch_name: candidateBranchFilter.value.trim() || 'main',
      metadata: {
        outline: generateOutline.value,
        sceneDirectorUsed: useSceneDirector.value,
        ...(rewriteTask?.metadata || {}),
        rewrite_task_id: rewriteTask?.id,
      },
    })
    message.success('已保存为候选稿')
    if (currentChapter.value?.number === target.number) {
      await loadCandidateDrafts()
      selectedCandidateDraftId.value = draft.id
      showCandidateDraftsModal.value = true
    }
  } catch {
    message.error('保存候选稿失败')
  } finally {
    savingCandidateDraft.value = false
  }
}

const handleAcceptCandidateDraft = async (draftId: string) => {
  if (!currentChapter.value) return
  acceptingCandidateDraftId.value = draftId
  try {
    const result = await chapterApi.acceptCandidateDraft(props.slug, currentChapter.value.number, draftId)
    markExternalModelTaskAccepted(props.slug, draftId)
    chapterContent.value = result.chapter.content
    originalContent.value = result.chapter.content
    message.success('候选稿已采纳为主稿')
    await loadCandidateDrafts()
    emit('chapterUpdated')
  } catch {
    message.error('采纳候选稿失败')
  } finally {
    acceptingCandidateDraftId.value = null
  }
}

const handleRejectCandidateDraft = async (draftId: string) => {
  if (!currentChapter.value) return
  try {
    await chapterApi.rejectCandidateDraft(props.slug, currentChapter.value.number, draftId)
    message.success('候选稿已标记为拒绝')
    await loadCandidateDrafts()
  } catch {
    message.error('拒绝候选稿失败')
  }
}

const savePartialCandidateDraft = async () => {
  const chapter = currentChapter.value
  const draft = selectedCandidateDraft.value
  if (!chapter || !draft) return
  if (selectedPartialParagraphIndexes.value.length === 0) {
    message.warning('请先勾选至少一个候选段落')
    return
  }

  savingPartialCandidateDraft.value = true
  try {
    const content = buildPartialCandidateContent(
      chapterContent.value,
      selectedCandidateParagraphDiff.value,
      selectedPartialParagraphIndexes.value,
    )
    const partialDraft = await chapterApi.createCandidateDraft(props.slug, chapter.number, {
      source: 'partial-accept',
      title: `${draft.title || `第${chapter.number}章候选稿`} · 部分采纳`,
      content,
      rationale: `从候选稿「${draft.title || draft.id}」中部分采纳第 ${selectedPartialParagraphIndexes.value.map(i => i + 1).join('、')} 段。`,
      branch_name: draft.branch_name || candidateBranchFilter.value.trim() || 'main',
      metadata: {
        ...(draft.metadata || {}),
        partial_source_draft_id: draft.id,
        partial_paragraph_indexes: selectedPartialParagraphIndexes.value,
      },
    })
    message.success('已保存部分采纳候选稿')
    await loadCandidateDrafts()
    selectedCandidateDraftId.value = partialDraft.id
  } catch {
    message.error('保存部分采纳候选稿失败')
  } finally {
    savingPartialCandidateDraft.value = false
  }
}

const handleGenerateFromCandidateTask = (draft: ChapterCandidateDraftDTO) => {
  const chapter = currentChapter.value
  if (!chapter || draft.chapter_number !== chapter.number) return

  activeCandidateRewriteTask.value = draft
  generateTargetChapterId.value = chapter.id
  generateOutline.value = candidateDraftRewritePrompt(draft)
  generatedContent.value = ''
  chapterStrategy.value = null
  editorialReview.value = null
  contextPreview.value = null
  blurSceneCache.value = undefined
  showCandidateDraftsModal.value = false
  showGenerateModal.value = true
}

const applyCandidateRewriteExecution = () => {
  const version = workbenchContextStore.candidateRewriteExecutionVersion
  const execution = workbenchContextStore.candidateRewriteExecution
  const chapter = currentChapter.value
  if (!execution || !chapter) return
  if (execution.slug !== props.slug || execution.draft.chapter_number !== chapter.number) return
  if (version <= lastConsumedCandidateExecutionVersion.value) return

  lastConsumedCandidateExecutionVersion.value = version
  workMode.value = 'assisted'
  handleGenerateFromCandidateTask(execution.draft)
}

function streamPhaseToProgress(phase: string): number {
  const map: Record<string, number> = {
    planning: 18,
    context: 40,
    llm: 72,
    polish: 86,
    post: 92,
  }
  return map[phase] ?? 12
}

function streamPhaseToLabel(phase: string): string {
  const map: Record<string, string> = {
    planning: '规划节拍…',
    context: '组装上下文…',
    llm: '撰写正文…',
    polish: '轻修正文…',
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

  const defaultOutline = `第${target.number}章：承接前情，推进主线`
  const outlineForGenerate = generateOutline.value || defaultOutline
  const precheck = await runCocPrecheckForModal({ silent: true })
  if (precheck?.checked && precheck.allow_generate === false && !ignoreCocPrecheckBlockOnce.value) {
    const reason = precheck.blocking_issues?.[0] || '命中 CoC 认知边界阻断规则'
    message.error(`预检阻断：${reason}`)
    return
  }
  if (precheck?.checked && (precheck.warnings?.length || 0) > 0) {
    message.warning(`预检提醒：${precheck.warnings[0]}`)
  }

  const targetChapterId = target.id
  const targetChapterNumber = target.number
  ignoreCocPrecheckBlockOnce.value = false
  generatingChapterId.value = targetChapterId
  generateInProgress.value = true
  generatedContent.value = ''
  editorialReview.value = null
  styleMatchReport.value = null
  sceneDirectorError.value = ''
  lastWorkflowResult.value = null
  lastQcChapterNumber.value = null
  streamPhaseLabel.value = '连接中…'
  streamProgressPct.value = 8
  streamStats.value = { chars: 0, estimated_tokens: 0, chunks: 0 }

  const ctrl = new AbortController()
  generateAbortCtrl.value = ctrl

  const sceneDirectorResult = await resolveSceneDirectorResultForModal(targetChapterNumber)

  try {
    await consumeGenerateChapterStream(
      props.slug,
      {
        chapter_number: targetChapterNumber,
        outline: outlineForGenerate,
        scene_director_result: sceneDirectorResult,
        style_profile_id: generateStyleProfileId.value || '',
        scene_type: generateSceneType.value.trim(),
        avoid_compressed_expression: avoidCompressedExpression.value,
        target_word_count: targetWordCount.value || undefined,
        word_tolerance_percent: wordTolerancePercent.value || 5,
        direct_writing_mode: directWritingMode.value,
        direct_light_polish: directWritingMode.value && directLightPolish.value,
        chapter_strategy: chapterStrategy.value || undefined,
        long_draft_mode: longDraftMode.value,
        long_draft_split_count: longDraftMode.value ? (longDraftSplitCount.value || 2) : undefined,
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
          streamStats.value = {
            chars: result.content.length,
            estimated_tokens: Math.floor(result.content.length / 1.5),
            chunks: streamStats.value.chunks || 0,
          }
          streamProgressPct.value = 100
          streamPhaseLabel.value = '已完成'
          void updateStyleMatchReport(result.content)
          void runEditorialReviewForModal(
            targetChapterNumber,
            outlineForGenerate,
            result.content,
          )
          if (result.direct_writing_mode) {
            message.success('直接写作完成，可先复制去检测或保存为候选稿')
          } else if (props.currentChapterId === targetChapterId) {
            message.success('生成完成，质检已同步到「章节状态」')
          } else {
            message.success(`第 ${targetChapterNumber} 章生成完成，质检在对应章的「章节状态」查看`)
          }
          if (!result.direct_writing_mode) {
            activeTab.value = 'chapter-status'
          }
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

async function updateStyleMatchReport(content: string) {
  const profileId = generateStyleProfileId.value
  if (!profileId || !content.trim()) {
    styleMatchReport.value = null
    return
  }

  styleMatchLoading.value = true
  try {
    styleMatchReport.value = await styleBibleApi.matchProfile(profileId, {
      novel_id: props.slug,
      content,
    })
  } catch {
    styleMatchReport.value = null
  } finally {
    styleMatchLoading.value = false
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

.assisted-tabs {
  flex: 1;
  min-height: 0;
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

.work-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.work-tabs :deep(.n-tabs-nav) {
  padding: 0 20px;
  background: var(--app-surface);
}

.work-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.work-tabs :deep(.n-tab-pane) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
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
  flex-wrap: wrap;
  gap: 12px;
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

.candidate-card--active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 28%, transparent);
  background: color-mix(in srgb, var(--primary-color) 4%, var(--card-color));
}

.candidate-ops-card {
  background:
    linear-gradient(135deg, rgba(31, 129, 255, 0.08), rgba(34, 197, 94, 0.05)),
    var(--app-surface);
  border: 1px solid var(--aitext-split-border);
  border-radius: 12px;
}

.paragraph-diff-row {
  padding: 10px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 10px;
  background: var(--app-surface);
}

.paragraph-diff-text {
  min-height: 44px;
  margin: 4px 0 0;
  padding: 8px;
  border-radius: 8px;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.6;
}

.paragraph-diff-text--base {
  background: rgba(208, 48, 80, 0.08);
}

.paragraph-diff-text--candidate {
  background: rgba(24, 160, 88, 0.08);
}

.generate-strategy-preview,
.editorial-review-card {
  margin-top: 8px;
  padding: 12px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.75), rgba(248, 250, 252, 0.94)),
    var(--app-surface);
}

.chapter-contract-card {
  margin-bottom: 12px;
}

.coc-precheck-card {
  border: 1px solid var(--aitext-split-border);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.02);
}

.generate-strategy-grid,
.editorial-score-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.strategy-chip,
.editorial-score-item,
.strategy-scene-row {
  padding: 10px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.03);
}

.strategy-chip {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.strategy-chip__label {
  font-size: 12px;
  color: #64748b;
}

.strategy-scene-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.editorial-score-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

@media (max-width: 900px) {
  .generate-strategy-grid,
  .editorial-score-grid {
    grid-template-columns: 1fr;
  }
}
</style>
