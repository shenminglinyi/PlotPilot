<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="选题立项池"
    :style="{ width: '94vw', maxWidth: '1120px', height: '82vh' }"
    :bordered="true"
    :segmented="{ content: true }"
    :mask-closable="true"
    :close-on-esc="true"
  >
    <div class="topic-panel">
      <section class="topic-form">
        <n-form label-placement="top">
          <n-grid :cols="2" :x-gap="12" :y-gap="8" responsive="screen">
            <n-gi>
              <n-form-item label="赛道 / 类型">
                <n-select
                  v-model:value="form.genre"
                  :options="genreOptions"
                  placeholder="选择赛道"
                  clearable
                />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="世界观基调">
                <n-select
                  v-model:value="form.world_preset"
                  :options="worldPresetOptions"
                  placeholder="选择基调"
                  clearable
                />
              </n-form-item>
            </n-gi>
          </n-grid>

          <n-form-item label="关键词">
            <n-dynamic-tags v-model:value="form.keywords" />
          </n-form-item>
          <n-form-item label="手动补充说明">
            <n-input
              v-model:value="form.brief"
              type="textarea"
              placeholder="写下这次想重点参考的方向、情绪、限制或灵感"
              :autosize="{ minRows: 2, maxRows: 5 }"
            />
          </n-form-item>
          <n-form-item label="目标爽点">
            <n-dynamic-tags v-model:value="form.desired_selling_points" />
          </n-form-item>
          <n-form-item label="避雷套路">
            <n-dynamic-tags v-model:value="form.avoid_patterns" />
          </n-form-item>
          <n-form-item label="篇幅档">
            <n-radio-group v-model:value="form.length_tier">
              <n-space :size="10" :wrap="true">
                <n-radio value="short">短篇</n-radio>
                <n-radio value="standard">标准</n-radio>
                <n-radio value="epic">史诗</n-radio>
              </n-space>
            </n-radio-group>
          </n-form-item>

          <n-space justify="end">
            <n-button secondary :loading="loading" @click="loadTopics">刷新</n-button>
            <n-button type="primary" :loading="generating" @click="handleGenerate">
              生成选题
            </n-button>
          </n-space>
        </n-form>

        <div class="signal-import">
          <div class="block-label">市场观察导入</div>
          <n-input
            v-model:value="signalText"
            type="textarea"
            placeholder="每行一条：标题 | 类型 | 标签1,标签2 | 摘要；也可直接粘贴榜单观察摘要"
            :autosize="{ minRows: 3, maxRows: 6 }"
            :disabled="importingSignals"
          />
          <n-space justify="end" :size="8">
            <n-button size="small" secondary :loading="loadingSignals" @click="loadSignals">
              查看信号
            </n-button>
            <n-button size="small" type="primary" :loading="importingSignals" @click="importMarketSignals">
              导入观察
            </n-button>
          </n-space>
          <div class="collector-block">
            <div class="block-label">公开来源采集</div>
            <div class="collector-source-list">
              <label
                v-for="source in signalSources"
                :key="source.key"
                class="collector-source-item"
              >
                <n-checkbox
                  :checked="selectedSourceKeys.includes(source.key)"
                  @update:checked="toggleSourceSelection(source.key, $event)"
                >
                  {{ source.name }}
                </n-checkbox>
                <span class="source-type-label">{{ sourceTypeLabel(source) }}</span>
                <n-tag
                  v-if="source.requires_auth"
                  size="small"
                  type="default"
                  :bordered="false"
                >
                  需登录
                </n-tag>
              </label>
            </div>
            <n-space justify="end" :size="8">
              <n-button size="small" secondary :loading="loadingSources" @click="loadSignalSources">
                刷新来源
              </n-button>
              <n-button
                size="small"
                secondary
                :loading="testingSourceConnections"
                :disabled="selectedSourceKeys.length === 0"
                @click="testSignalSources"
              >
                测试连接
              </n-button>
              <n-button
                size="small"
                type="primary"
                ghost
                :loading="collectingSignals"
                :disabled="selectedSourceKeys.length === 0"
                @click="collectMarketSignals"
              >
                自动采集
              </n-button>
            </n-space>
            <div v-if="sourceConnectionResults.length" class="source-test-list">
              <div
                v-for="result in sourceConnectionResults"
                :key="result.source_key"
                class="source-test-item"
              >
                <n-tag size="small" :type="result.ok ? 'success' : 'error'" :bordered="false">
                  {{ result.ok ? '已连接' : '未连通' }}
                </n-tag>
                <span>{{ result.source_name }}</span>
                <span>{{ result.message }}</span>
                <span v-if="result.sample_titles.length">样例：{{ result.sample_titles.join('、') }}</span>
              </div>
            </div>
          </div>
          <div class="collector-block">
            <div class="signal-summary-head">
              <div class="block-label">自动采集设置</div>
              <n-button size="small" secondary :loading="savingAutomationSettings" @click="saveAutomationSettings">
                保存设置
              </n-button>
            </div>
            <div class="automation-grid">
              <label class="automation-field automation-toggle">
                <span class="automation-label">启用定时采集</span>
                <n-switch v-model:value="automationSettings.enabled" />
              </label>
              <label class="automation-field">
                <span class="automation-label">间隔（分钟）</span>
                <n-input-number v-model:value="automationSettings.interval_minutes" :min="15" :max="1440" />
              </label>
              <label class="automation-field">
                <span class="automation-label">单源条数</span>
                <n-input-number v-model:value="automationSettings.limit_per_source" :min="1" :max="30" />
              </label>
              <label class="automation-field">
                <span class="automation-label">趋势窗口（天）</span>
                <n-input-number v-model:value="automationSettings.lookback_days" :min="1" :max="90" />
              </label>
            </div>
            <div class="automation-status">
              <span>状态：{{ automationStatusLabel }}</span>
              <span v-if="automationSettings.last_run_at">最近执行：{{ automationSettings.last_run_at }}</span>
              <span v-if="automationSettings.last_error" class="automation-error">{{ automationSettings.last_error }}</span>
            </div>
            <div v-if="sourceHealth.length" class="source-health-list">
              <div
                v-for="health in sourceHealth"
                :key="health.source_key"
                class="source-health-item"
              >
                <n-tag size="small" :type="sourceHealthTagType(health.status)" :bordered="false">
                  {{ sourceHealthStatusLabel(health.status) }}
                </n-tag>
                <span class="source-health-name">{{ health.source_name }}</span>
                <span>最近 {{ health.last_count }} 条</span>
                <span v-if="health.last_run_at">执行：{{ health.last_run_at }}</span>
                <span v-if="health.next_run_at">下次：{{ health.next_run_at }}</span>
                <span v-if="health.last_error" class="automation-error">{{ health.last_error }}</span>
              </div>
            </div>
          </div>
          <div class="collector-block">
            <div class="signal-summary-head">
              <div class="block-label">外部 API / 登录态</div>
              <n-button size="small" secondary :loading="loadingSourceCredentials" @click="loadSourceCredentials">
                刷新状态
              </n-button>
            </div>
            <div class="credential-grid">
              <label class="automation-field">
                <span class="automation-label">来源</span>
                <n-select
                  v-model:value="credentialForm.source_key"
                  :options="credentialSourceOptions"
                  placeholder="选择来源"
                />
              </label>
              <label class="automation-field">
                <span class="automation-label">API Key</span>
                <n-input
                  v-model:value="credentialForm.api_key"
                  type="password"
                  show-password-on="click"
                  placeholder="留空则不更新"
                />
              </label>
              <label class="automation-field credential-cookie-field">
                <span class="automation-label">接口 Endpoint</span>
                <n-input
                  v-model:value="credentialForm.endpoint_url"
                  placeholder="可填平台 JSON 接口地址，留空则使用默认公开页"
                />
              </label>
              <label class="automation-field credential-cookie-field">
                <span class="automation-label">Cookie</span>
                <n-input
                  v-model:value="credentialForm.cookie"
                  type="textarea"
                  placeholder="留空则不更新"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                />
              </label>
              <label class="automation-field credential-cookie-field">
                <span class="automation-label">自定义 Headers</span>
                <n-input
                  v-model:value="credentialForm.headers_text"
                  type="textarea"
                  placeholder="每行一个：Header-Name: value"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                />
              </label>
            </div>
            <div class="automation-status">
              <span>API Key：{{ selectedCredentialStatus?.api_key_configured ? '已配置' : '未配置' }}</span>
              <span>Cookie：{{ selectedCredentialStatus?.cookie_configured ? '已配置' : '未配置' }}</span>
              <span>Endpoint：{{ selectedCredentialStatus?.endpoint_configured ? '已配置' : '默认' }}</span>
              <span v-if="selectedCredentialStatus?.header_keys?.length">
                Headers：{{ selectedCredentialStatus.header_keys.join('、') }}
              </span>
              <span v-if="selectedCredentialStatus?.updated_at">更新：{{ selectedCredentialStatus.updated_at }}</span>
            </div>
            <n-space justify="end" :size="8">
              <n-button
                size="small"
                type="primary"
                ghost
                :loading="savingSourceCredentials"
                :disabled="!credentialForm.source_key"
                @click="saveSourceCredentials"
              >
                保存凭据
              </n-button>
            </n-space>
          </div>
        </div>
      </section>

      <section class="topic-list">
        <n-tabs v-model:value="activeStatus" type="segment" @update:value="loadTopics">
          <n-tab-pane name="draft" tab="草稿" />
          <n-tab-pane name="archived" tab="归档" />
          <n-tab-pane name="adopted" tab="已采用" />
        </n-tabs>

        <div v-if="marketSignalSummary" class="signal-summary-card">
          <div class="signal-summary-head">
            <div>
              <div class="block-label">市场摘要</div>
              <div class="signal-summary-total">近 {{ marketSignalSummary.total }} 条信号</div>
            </div>
            <div class="summary-chip-row">
              <n-tag size="small" type="info" :bordered="false">
                小说 {{ categoryCount('novel') }}
              </n-tag>
              <n-tag size="small" type="warning" :bordered="false">
                漫画 {{ categoryCount('comic') }}
              </n-tag>
            </div>
          </div>
          <div class="summary-grid">
            <div class="summary-cell">
              <div class="block-label">Top 标签</div>
              <div class="summary-chip-row">
                <n-tag v-for="item in topTags" :key="item.label" size="small">
                  {{ item.label }} {{ item.count }}
                </n-tag>
                <span v-if="topTags.length === 0" class="summary-empty">暂无</span>
              </div>
            </div>
            <div class="summary-cell">
              <div class="block-label">Top 类型</div>
              <div class="summary-chip-row">
                <n-tag v-for="item in topGenres" :key="item.label" size="small" type="success">
                  {{ item.label }} {{ item.count }}
                </n-tag>
                <span v-if="topGenres.length === 0" class="summary-empty">暂无</span>
              </div>
            </div>
            <div class="summary-cell">
              <div class="block-label">Top 来源</div>
              <div class="summary-chip-row">
                <n-tag v-for="item in topSources" :key="item.label" size="small" type="default">
                  {{ item.label }} {{ item.count }}
                </n-tag>
                <span v-if="topSources.length === 0" class="summary-empty">暂无</span>
              </div>
            </div>
          </div>
          <div v-if="comicOpportunities.length" class="comic-opportunity-list">
            <div class="block-label">漫画机会</div>
            <div v-for="item in comicOpportunities" :key="item" class="comic-opportunity-item">
              {{ item }}
            </div>
          </div>
        </div>

        <div v-if="marketSignals.length" class="signal-strip">
          <div class="signal-strip-header">
            <div class="block-label">最近市场信号</div>
            <n-button size="tiny" quaternary @click="marketSignals = []">收起</n-button>
          </div>
          <div class="signal-list">
            <div v-for="signal in marketSignals" :key="signal.id" class="signal-item">
              <div class="signal-head">
                <n-checkbox
                  :checked="selectedSignalIds.includes(signal.id)"
                  @update:checked="toggleSignalSelection(signal.id, $event)"
                />
                <div class="signal-title">{{ signal.title || signal.summary }}</div>
              </div>
              <div class="signal-summary">{{ signal.summary }}</div>
              <div class="tag-row">
                <n-tag v-if="signal.genre" size="small">{{ signal.genre }}</n-tag>
                <n-tag v-for="tag in signal.tags" :key="tag" size="small" type="info">
                  {{ tag }}
                </n-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-if="canCompareCurrentTab" class="compare-toolbar">
          <span class="compare-count">已选 {{ selectedTopicIds.length }} / 5</span>
          <n-space :size="8">
            <n-button size="small" quaternary :disabled="selectedTopicIds.length === 0" @click="clearCompare">
              清空
            </n-button>
            <n-button
              size="small"
              type="primary"
              :disabled="selectedTopicIds.length < 2 || selectedTopicIds.length > 5"
              :loading="comparing"
              @click="compareTopics"
            >
              对比选题
            </n-button>
          </n-space>
        </div>

        <n-card v-if="compareResult" size="small" class="compare-result">
          <div class="compare-result-header">
            <div>
              <div class="block-label">推荐选题</div>
              <strong>{{ recommendedTitle }}</strong>
            </div>
            <n-tag size="small" type="success" :bordered="false">
              {{ compareResult.rankings.length }} 项对比
            </n-tag>
          </div>
          <p class="compare-summary">{{ compareResult.summary }}</p>
          <div class="ranking-list">
            <div
              v-for="(ranking, index) in compareResult.rankings"
              :key="ranking.topic_id"
              class="ranking-item"
              :class="{ recommended: ranking.topic_id === compareResult.recommended_topic_id }"
            >
              <div class="ranking-head">
                <span class="ranking-title">{{ index + 1 }}. {{ ranking.title }}</span>
                <n-tag size="small" :type="ranking.topic_id === compareResult.recommended_topic_id ? 'success' : 'default'">
                  {{ normalizeScore(ranking.score) }}
                </n-tag>
              </div>
              <div class="ranking-reason">{{ ranking.reason }}</div>
              <div v-if="ranking.risks.length" class="ranking-risks">
                <span v-for="risk in ranking.risks" :key="risk">· {{ risk }}</span>
              </div>
            </div>
          </div>
        </n-card>

        <n-spin :show="loading">
          <n-empty v-if="topics.length === 0" description="暂无选题" />
          <div v-else class="topic-cards">
            <n-card v-for="idea in topics" :key="idea.id" size="small" class="topic-card">
              <template #header>
                <div class="topic-card-header">
                  <div class="topic-title-wrap">
                    <n-checkbox
                      v-if="canCompareCurrentTab"
                      :checked="selectedTopicIds.includes(idea.id)"
                      :disabled="isTopicSelectionDisabled(idea)"
                      @update:checked="toggleTopicSelection(idea.id, $event)"
                    />
                    <span class="topic-title">{{ idea.title }}</span>
                  </div>
                  <n-tag size="small" type="info" :bordered="false">
                    推荐 {{ normalizeScore(idea.score) }}
                  </n-tag>
                </div>
              </template>

              <n-space vertical :size="9">
                <div class="topic-meta">
                  <n-tag size="small">{{ idea.genre || '未分类' }}</n-tag>
                  <n-tag size="small">{{ idea.world_preset || '未设定' }}</n-tag>
                  <n-tag size="small">{{ lengthLabel(idea.length_tier) }}</n-tag>
                </div>

                <p class="topic-logline">{{ idea.logline || idea.premise }}</p>

                <div v-if="idea.market_tags.length" class="tag-row">
                  <n-tag
                    v-for="tag in idea.market_tags"
                    :key="tag"
                    size="small"
                    type="info"
                    round
                  >
                    {{ tag }}
                  </n-tag>
                </div>

                <div v-if="idea.selling_points.length" class="topic-block">
                  <div class="block-label">商业看点</div>
                  <div class="tag-row">
                    <n-tag
                      v-for="point in idea.selling_points"
                      :key="point"
                      size="small"
                      type="success"
                    >
                      {{ point }}
                    </n-tag>
                  </div>
                </div>

                <div v-if="idea.long_term_potential" class="topic-line">
                  <strong>长线潜力：</strong>{{ idea.long_term_potential }}
                </div>
                <div v-if="idea.core_conflict" class="topic-line">
                  <strong>核心冲突：</strong>{{ idea.core_conflict }}
                </div>
                <div v-if="idea.protagonist_hook" class="topic-line">
                  <strong>主角钩子：</strong>{{ idea.protagonist_hook }}
                </div>
                <div v-if="idea.opening_hook" class="topic-line">
                  <strong>开篇事件：</strong>{{ idea.opening_hook }}
                </div>

                <div v-if="idea.risk_notes.length" class="risk-list">
                  <div class="block-label">风险提示</div>
                  <div v-for="risk in idea.risk_notes" :key="risk">· {{ risk }}</div>
                </div>

                <div v-if="hasReportContent(idea.development_notes)" class="topic-report">
                  <div class="block-label">立项案</div>
                  <div class="report-rows">
                    <div
                      v-for="[key, value] in reportEntries(idea.development_notes)"
                      :key="key"
                      class="report-row"
                    >
                      <span class="report-key">{{ formatReportKey(key) }}</span>
                      <div class="report-value">
                        <ul v-if="Array.isArray(value)" class="report-list">
                          <li v-for="(item, index) in value" :key="`${key}-${index}`">
                            {{ formatReportValue(item) }}
                          </li>
                        </ul>
                        <div v-else-if="isReportObject(value)" class="report-subrows">
                          <div
                            v-for="[childKey, childValue] in reportEntries(value)"
                            :key="childKey"
                            class="report-subrow"
                          >
                            <span class="report-subkey">{{ formatReportKey(childKey) }}</span>
                            <span>{{ formatReportValue(childValue) }}</span>
                          </div>
                        </div>
                        <span v-else>{{ formatReportValue(value) }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="hasReportContent(idea.evaluation)" class="topic-report">
                  <div class="block-label">评估维度</div>
                  <div class="report-rows">
                    <div
                      v-for="[key, value] in reportEntries(idea.evaluation)"
                      :key="key"
                      class="report-row"
                    >
                      <span class="report-key">{{ formatReportKey(key) }}</span>
                      <div class="report-value">
                        <ul v-if="Array.isArray(value)" class="report-list">
                          <li v-for="(item, index) in value" :key="`${key}-${index}`">
                            {{ formatReportValue(item) }}
                          </li>
                        </ul>
                        <div v-else-if="isReportObject(value)" class="report-subrows">
                          <div
                            v-for="[childKey, childValue] in reportEntries(value)"
                            :key="childKey"
                            class="report-subrow"
                          >
                            <span class="report-subkey">{{ formatReportKey(childKey) }}</span>
                            <span>{{ formatReportValue(childValue) }}</span>
                          </div>
                        </div>
                        <span v-else>{{ formatReportValue(value) }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <n-space justify="end" :wrap="true" class="topic-actions">
                  <n-button
                    v-if="idea.status !== 'adopted'"
                    size="small"
                    secondary
                    :loading="deepeningIds.has(idea.id)"
                    :disabled="isTopicBusy(idea.id)"
                    @click="deepenTopic(idea)"
                  >
                    深化
                  </n-button>
                  <n-button
                    v-if="idea.status !== 'adopted'"
                    size="small"
                    secondary
                    :loading="evaluatingIds.has(idea.id)"
                    :disabled="isTopicBusy(idea.id)"
                    @click="evaluateTopic(idea)"
                  >
                    评估
                  </n-button>
                  <n-button
                    v-if="idea.status === 'draft'"
                    size="small"
                    secondary
                    :disabled="isTopicBusy(idea.id)"
                    @click="setStatus(idea, 'archived')"
                  >
                    归档
                  </n-button>
                  <n-button
                    v-if="idea.status === 'archived'"
                    size="small"
                    secondary
                    :disabled="isTopicBusy(idea.id)"
                    @click="setStatus(idea, 'draft')"
                  >
                    恢复
                  </n-button>
                  <n-button
                    v-if="idea.status !== 'adopted'"
                    size="small"
                    type="primary"
                    :loading="adoptingIds.has(idea.id)"
                    :disabled="isTopicBusy(idea.id) || isOtherTopicAdopting(idea.id)"
                    @click="openAdoptPreview(idea)"
                  >
                    采用为新书
                  </n-button>
                </n-space>
              </n-space>
            </n-card>
          </div>
        </n-spin>
      </section>
    </div>
  </n-modal>

  <n-modal
    v-model:show="adoptPreviewVisible"
    preset="card"
    title="采用为新书"
    :style="{ width: '92vw', maxWidth: '720px' }"
    :bordered="true"
    :mask-closable="!confirmingAdopt"
    :close-on-esc="!confirmingAdopt"
  >
    <div v-if="pendingAdoptIdea" class="adopt-preview">
      <div class="adopt-preview-meta">
        <n-tag size="small">{{ pendingAdoptIdea.genre || '未分类' }}</n-tag>
        <n-tag size="small">{{ pendingAdoptIdea.world_preset || '未设定' }}</n-tag>
        <n-tag size="small">{{ lengthLabel(pendingAdoptIdea.length_tier) }}</n-tag>
        <n-tag size="small" type="info" :bordered="false">
          推荐 {{ normalizeScore(pendingAdoptIdea.score) }}
        </n-tag>
      </div>

      <n-form label-placement="top">
        <n-form-item label="新书标题">
          <n-input
            v-model:value="adoptDraft.title"
            placeholder="输入新书标题"
            :disabled="confirmingAdopt"
          />
        </n-form-item>
        <n-form-item label="核心梗概">
          <n-input
            v-model:value="adoptDraft.premise"
            type="textarea"
            placeholder="确认或微调要带入新书向导的核心梗概"
            :autosize="{ minRows: 4, maxRows: 8 }"
            :disabled="confirmingAdopt"
          />
        </n-form-item>
      </n-form>

      <div v-if="pendingAdoptIdea.logline" class="adopt-preview-section">
        <div class="block-label">一句话卖点</div>
        <p>{{ pendingAdoptIdea.logline }}</p>
      </div>
      <div v-if="pendingAdoptIdea.core_conflict || pendingAdoptIdea.opening_hook" class="adopt-preview-section">
        <div class="block-label">关键钩子</div>
        <p v-if="pendingAdoptIdea.core_conflict">核心冲突：{{ pendingAdoptIdea.core_conflict }}</p>
        <p v-if="pendingAdoptIdea.opening_hook">开篇事件：{{ pendingAdoptIdea.opening_hook }}</p>
      </div>
      <div v-if="hasReportContent(pendingAdoptIdea.development_notes)" class="adopt-preview-section">
        <div class="block-label">将带入的新书立项案</div>
        <div
          v-for="[key, value] in reportEntries(pendingAdoptIdea.development_notes)"
          :key="key"
          class="adopt-preview-line"
        >
          <strong>{{ formatReportKey(key) }}：</strong>{{ formatReportValue(value) }}
        </div>
      </div>
      <div v-if="hasReportContent(pendingAdoptIdea.evaluation)" class="adopt-preview-section">
        <div class="block-label">评估风险</div>
        <div
          v-for="[key, value] in reportEntries(pendingAdoptIdea.evaluation)"
          :key="key"
          class="adopt-preview-line"
        >
          <strong>{{ formatReportKey(key) }}：</strong>{{ formatReportValue(value) }}
        </div>
      </div>
    </div>

    <template #footer>
      <n-space justify="end">
        <n-button :disabled="confirmingAdopt" @click="closeAdoptPreview">
          取消
        </n-button>
        <n-button type="primary" :loading="confirmingAdopt" @click="confirmAdoptTopic">
          确认采用并进入向导
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { topicApi, type TopicCompareResult, type TopicIdea, type TopicLengthTier, type TopicIdeaStatus, type TopicMarketSignal, type TopicMarketSignalSource, type TopicMarketSignalSummary, type TopicMarketSignalAutomationSettings, type TopicMarketSignalSourceCredentialStatus, type TopicMarketSignalSourceConnection, type TopicMarketSignalSourceHealth } from '@/api/topic'
import type { NovelDTO } from '@/api/novel'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'adopted', novel: NovelDTO): void
}>()

const message = useMessage()
const visible = computed({
  get: () => props.show,
  set: (value: boolean) => emit('update:show', value),
})

const form = reactive({
  brief: '',
  genre: '',
  world_preset: '',
  keywords: [] as string[],
  desired_selling_points: [] as string[],
  avoid_patterns: [] as string[],
  length_tier: 'standard' as TopicLengthTier,
})

const activeStatus = ref<TopicIdeaStatus>('draft')
const topics = ref<TopicIdea[]>([])
const loading = ref(false)
const generating = ref(false)
const adoptingIds = ref<Set<string>>(new Set())
const deepeningIds = ref<Set<string>>(new Set())
const evaluatingIds = ref<Set<string>>(new Set())
const comparing = ref(false)
const selectedTopicIds = ref<string[]>([])
const compareResult = ref<TopicCompareResult | null>(null)
const signalText = ref('')
const marketSignals = ref<TopicMarketSignal[]>([])
const marketSignalSummary = ref<TopicMarketSignalSummary | null>(null)
const selectedSignalIds = ref<string[]>([])
const signalSources = ref<TopicMarketSignalSource[]>([])
const sourceCredentials = ref<TopicMarketSignalSourceCredentialStatus[]>([])
const sourceConnectionResults = ref<TopicMarketSignalSourceConnection[]>([])
const sourceHealth = ref<TopicMarketSignalSourceHealth[]>([])
const selectedSourceKeys = ref<string[]>([])
const importingSignals = ref(false)
const loadingSignals = ref(false)
const loadingSources = ref(false)
const collectingSignals = ref(false)
const testingSourceConnections = ref(false)
const savingAutomationSettings = ref(false)
const loadingSourceCredentials = ref(false)
const savingSourceCredentials = ref(false)
const adoptPreviewVisible = ref(false)
const pendingAdoptIdea = ref<TopicIdea | null>(null)
const confirmingAdopt = ref(false)
const adoptDraft = reactive({
  title: '',
  premise: '',
})
const automationSettings = reactive<TopicMarketSignalAutomationSettings>({
  enabled: false,
  interval_minutes: 180,
  limit_per_source: 8,
  lookback_days: 30,
  source_weights: {},
  selected_source_keys: [],
  last_run_at: '',
  last_status: 'idle',
  last_error: '',
  updated_at: '',
})
const credentialForm = reactive({
  source_key: '',
  api_key: '',
  cookie: '',
  endpoint_url: '',
  headers_text: '',
})

const canCompareCurrentTab = computed(() => activeStatus.value === 'draft' || activeStatus.value === 'archived')
const recommendedTitle = computed(() => {
  if (!compareResult.value) return '--'
  return compareResult.value.rankings.find(
    item => item.topic_id === compareResult.value?.recommended_topic_id,
  )?.title || compareResult.value.recommended_topic_id
})
const topSources = computed(() => topSummaryEntries(marketSignalSummary.value?.weighted_source_scores, marketSignalSummary.value?.source_counts))
const topGenres = computed(() => topSummaryEntries(marketSignalSummary.value?.weighted_genre_scores, marketSignalSummary.value?.genre_counts))
const topTags = computed(() => topSummaryEntries(marketSignalSummary.value?.weighted_tag_scores, marketSignalSummary.value?.tag_counts))
const comicOpportunities = computed(() => marketSignalSummary.value?.comic_opportunities?.slice(0, 3) || [])
const credentialSourceOptions = computed(() => signalSources.value.map(source => ({
  label: source.name,
  value: source.key,
})))
const selectedCredentialStatus = computed(() => sourceCredentials.value.find(
  item => item.source_key === credentialForm.source_key,
))
const automationStatusLabel = computed(() => {
  if (automationSettings.last_status === 'success') return '最近执行成功'
  if (automationSettings.last_status === 'error') return '最近执行失败'
  if (automationSettings.enabled) return '已启用，等待执行'
  return '未启用'
})

const genreOptions = [
  { label: '玄幻升级', value: '玄幻升级' },
  { label: '都市爽文', value: '都市爽文' },
  { label: '仙侠修真', value: '仙侠修真' },
  { label: '科幻赛博', value: '科幻赛博' },
  { label: '悬疑推理', value: '悬疑推理' },
  { label: '历史架空', value: '历史架空' },
  { label: '游戏异界', value: '游戏异界' },
  { label: '言情甜宠', value: '言情甜宠' },
  { label: '其他', value: '其他' },
]

const worldPresetOptions = [
  { label: '修仙风', value: '修仙风' },
  { label: '赛博朋克风', value: '赛博朋克风' },
  { label: '悬疑风', value: '悬疑风' },
  { label: '高武江湖', value: '高武江湖' },
  { label: '末日废土', value: '末日废土' },
  { label: '西幻史诗', value: '西幻史诗' },
  { label: '现代都市', value: '现代都市' },
  { label: '克系诡异', value: '克系诡异' },
]

function lengthLabel(value: string) {
  if (value === 'short') return '短篇'
  if (value === 'epic') return '史诗'
  return '标准'
}

function normalizeScore(score: number) {
  if (!Number.isFinite(score)) return '--'
  return Math.max(0, Math.min(100, Math.round(score)))
}

function topSummaryEntries(
  weightedCounts: Record<string, number> | undefined,
  fallbackCounts?: Record<string, number> | undefined,
  limit = 4,
): Array<{ label: string; count: number }> {
  const counts = Object.keys(weightedCounts || {}).length > 0 ? weightedCounts : fallbackCounts
  return Object.entries(counts || {})
    .filter(([label, count]) => label && Number.isFinite(count) && count > 0)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'zh-CN'))
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }))
}

function categoryCount(category: string) {
  return marketSignalSummary.value?.category_counts?.[category] || 0
}

function isReportObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function hasReportContent(value: Record<string, unknown> | null | undefined) {
  return reportEntries(value).length > 0
}

function hasReportValue(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.some(hasReportValue)
  if (isReportObject(value)) return Object.values(value).some(hasReportValue)
  return true
}

function reportEntries(value: Record<string, unknown> | null | undefined): [string, unknown][] {
  if (!isReportObject(value)) return []
  return Object.entries(value).filter(([, item]) => hasReportValue(item))
}

function formatReportKey(key: string) {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .trim()
}

function formatReportValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.filter(hasReportValue).map(formatReportValue).join('、')
  if (isReportObject(value)) return JSON.stringify(value)
  return String(value)
}

function errorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function replaceTopic(updated: TopicIdea) {
  topics.value = topics.value.map(item => (item.id === updated.id ? updated : item))
}

function markBusy(target: typeof deepeningIds, topicId: string) {
  target.value = new Set([...target.value, topicId])
}

function clearBusy(target: typeof deepeningIds, topicId: string) {
  const next = new Set(target.value)
  next.delete(topicId)
  target.value = next
}

function isTopicBusy(topicId: string) {
  return deepeningIds.value.has(topicId) || evaluatingIds.value.has(topicId) || adoptingIds.value.has(topicId)
}

function isOtherTopicAdopting(topicId: string) {
  return adoptingIds.value.size > 0 && !adoptingIds.value.has(topicId)
}

function isTopicSelectionDisabled(idea: TopicIdea) {
  return !selectedTopicIds.value.includes(idea.id) && selectedTopicIds.value.length >= 5
}

function toggleTopicSelection(topicId: string, checked: boolean) {
  compareResult.value = null
  if (checked) {
    if (!selectedTopicIds.value.includes(topicId) && selectedTopicIds.value.length < 5) {
      selectedTopicIds.value = [...selectedTopicIds.value, topicId]
    }
    return
  }
  selectedTopicIds.value = selectedTopicIds.value.filter(id => id !== topicId)
}

function clearCompare() {
  selectedTopicIds.value = []
  compareResult.value = null
}

function toggleSignalSelection(signalId: string, checked: boolean) {
  if (checked) {
    if (!selectedSignalIds.value.includes(signalId)) {
      selectedSignalIds.value = [...selectedSignalIds.value, signalId]
    }
    return
  }
  selectedSignalIds.value = selectedSignalIds.value.filter(id => id !== signalId)
}

function toggleSourceSelection(sourceKey: string, checked: boolean) {
  if (checked) {
    if (!selectedSourceKeys.value.includes(sourceKey)) {
      selectedSourceKeys.value = [...selectedSourceKeys.value, sourceKey]
    }
    return
  }
  selectedSourceKeys.value = selectedSourceKeys.value.filter(key => key !== sourceKey)
}

function sourceTypeLabel(source: TopicMarketSignalSource) {
  if (source.source_type === 'api') return 'API'
  if (source.source_type === 'authenticated_source') return '登录态'
  if (source.requires_auth) return '登录态'
  return '公开页'
}

function selectedMarketSignals() {
  return marketSignals.value
    .filter(signal => selectedSignalIds.value.includes(signal.id))
    .map(signal => ({
      id: signal.id,
      source: signal.source,
      title: signal.title,
      genre: signal.genre,
      tags: signal.tags,
      summary: signal.summary,
    }))
}

function openAdoptPreview(idea: TopicIdea) {
  pendingAdoptIdea.value = idea
  adoptDraft.title = idea.title
  adoptDraft.premise = idea.premise || idea.logline
  adoptPreviewVisible.value = true
}

function closeAdoptPreview() {
  if (confirmingAdopt.value) return
  adoptPreviewVisible.value = false
  pendingAdoptIdea.value = null
  adoptDraft.title = ''
  adoptDraft.premise = ''
}

async function loadTopics() {
  loading.value = true
  try {
    topics.value = await topicApi.list(activeStatus.value)
    clearCompare()
  } catch (error: any) {
    message.error(errorMessage(error, '选题加载失败'))
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    topics.value = await topicApi.generate({
      ...form,
      brief: form.brief.trim(),
      market_signals: selectedMarketSignals(),
      count: 3,
    })
    activeStatus.value = 'draft'
    clearCompare()
    message.success('选题已生成')
  } catch (error: any) {
    message.error(errorMessage(error, '选题生成失败'))
  } finally {
    generating.value = false
  }
}

async function loadSignals() {
  loadingSignals.value = true
  try {
    marketSignals.value = await topicApi.listSignals(8)
    await loadSignalSummary(true)
  } catch (error: any) {
    message.error(errorMessage(error, '市场信号加载失败'))
  } finally {
    loadingSignals.value = false
  }
}

async function loadSignalSummary(silent = false) {
  try {
    marketSignalSummary.value = await topicApi.signalSummary(100)
  } catch (error) {
    marketSignalSummary.value = null
    if (!silent) {
      message.warning('市场摘要暂不可用，不影响其他选题功能')
    }
  }
}

async function loadAutomationSettings() {
  try {
    const settings = await topicApi.getAutomationSettings()
    Object.assign(automationSettings, settings)
    if (settings.selected_source_keys.length > 0) {
      selectedSourceKeys.value = [...settings.selected_source_keys]
    }
    await loadSourceHealth(true)
  } catch (_error) {
    message.warning('自动采集设置暂不可用，不影响手动采集和选题功能')
  }
}

async function loadSourceHealth(silent = false) {
  try {
    sourceHealth.value = await topicApi.listSignalSourceHealth()
  } catch (error: any) {
    sourceHealth.value = []
    if (!silent) {
      message.warning(errorMessage(error, '采集健康状态暂不可用'))
    }
  }
}

async function loadSignalSources() {
  loadingSources.value = true
  try {
    signalSources.value = await topicApi.listSignalSources()
    if (!credentialForm.source_key && signalSources.value.length > 0) {
      credentialForm.source_key = signalSources.value[0].key
    }
    if (selectedSourceKeys.value.length === 0 && automationSettings.selected_source_keys.length > 0) {
      selectedSourceKeys.value = [...automationSettings.selected_source_keys]
    } else if (selectedSourceKeys.value.length === 0) {
      selectedSourceKeys.value = signalSources.value.map(source => source.key)
    }
  } catch (error: any) {
    message.error(errorMessage(error, '采集来源加载失败'))
  } finally {
    loadingSources.value = false
  }
}

async function loadSourceCredentials() {
  loadingSourceCredentials.value = true
  try {
    sourceCredentials.value = await topicApi.listSourceCredentials()
  } catch (error: any) {
    message.warning(errorMessage(error, '来源凭据状态暂不可用'))
  } finally {
    loadingSourceCredentials.value = false
  }
}

async function saveSourceCredentials() {
  if (!credentialForm.source_key) {
    message.warning('请选择来源')
    return
  }
  const apiKey = credentialForm.api_key.trim()
  const cookie = credentialForm.cookie.trim()
  const endpointUrl = credentialForm.endpoint_url.trim()
  const headers = parseHeadersText(credentialForm.headers_text)
  if (!apiKey && !cookie && !endpointUrl && Object.keys(headers).length === 0) {
    message.warning('请填写 Endpoint、API Key、Cookie 或自定义 Headers')
    return
  }
  savingSourceCredentials.value = true
  try {
    const status = await topicApi.updateSourceCredentials(credentialForm.source_key, {
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(cookie ? { cookie } : {}),
      ...(endpointUrl ? { endpoint_url: endpointUrl } : {}),
      ...(Object.keys(headers).length > 0 ? { headers } : {}),
    })
    const index = sourceCredentials.value.findIndex(item => item.source_key === status.source_key)
    if (index >= 0) {
      sourceCredentials.value[index] = status
    } else {
      sourceCredentials.value.push(status)
    }
    credentialForm.api_key = ''
    credentialForm.cookie = ''
    credentialForm.endpoint_url = ''
    credentialForm.headers_text = ''
    message.success('来源凭据已保存')
  } catch (error: any) {
    message.error(errorMessage(error, '来源凭据保存失败'))
  } finally {
    savingSourceCredentials.value = false
  }
}

function parseHeadersText(text: string): Record<string, string> {
  const headers: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const index = line.indexOf(':')
    if (index <= 0) continue
    const key = line.slice(0, index).trim()
    const value = line.slice(index + 1).trim()
    if (key && value) headers[key] = value
  }
  return headers
}

async function saveAutomationSettings() {
  savingAutomationSettings.value = true
  try {
    const settings = await topicApi.updateAutomationSettings({
      enabled: automationSettings.enabled,
      interval_minutes: automationSettings.interval_minutes,
      limit_per_source: automationSettings.limit_per_source,
      lookback_days: automationSettings.lookback_days,
      selected_source_keys: selectedSourceKeys.value,
      source_weights: automationSettings.source_weights,
    })
    Object.assign(automationSettings, settings)
    if (settings.selected_source_keys.length > 0) {
      selectedSourceKeys.value = [...settings.selected_source_keys]
    }
    message.success('自动采集设置已保存')
  } catch (error: any) {
    message.error(errorMessage(error, '自动采集设置保存失败'))
  } finally {
    savingAutomationSettings.value = false
  }
}

async function collectMarketSignals() {
  if (selectedSourceKeys.value.length === 0) {
    message.warning('请选择至少一个采集来源')
    return
  }
  collectingSignals.value = true
  try {
    const collected = await topicApi.collectSignals({
      source_keys: selectedSourceKeys.value,
      limit_per_source: 8,
    })
    marketSignals.value = [...collected, ...marketSignals.value].slice(0, 12)
    selectedSignalIds.value = [
      ...collected.map(signal => signal.id),
      ...selectedSignalIds.value,
    ].filter((id, index, all) => all.indexOf(id) === index)
    await loadSignalSummary(true)
    await loadSourceHealth(true)
    message.success(`已采集 ${collected.length} 条市场信号`)
  } catch (error: any) {
    message.error(errorMessage(error, '自动采集失败'))
  } finally {
    collectingSignals.value = false
  }
}

function sourceHealthStatusLabel(status: string) {
  if (status === 'success') return '正常'
  if (status === 'error') return '失败'
  return '待采集'
}

function sourceHealthTagType(status: string): 'success' | 'error' | 'default' {
  if (status === 'success') return 'success'
  if (status === 'error') return 'error'
  return 'default'
}

async function testSignalSources() {
  if (selectedSourceKeys.value.length === 0) {
    message.warning('请选择至少一个采集来源')
    return
  }
  testingSourceConnections.value = true
  try {
    sourceConnectionResults.value = await topicApi.testSignalSources({
      source_keys: selectedSourceKeys.value,
      limit_per_source: 1,
    })
    const failed = sourceConnectionResults.value.filter(item => !item.ok)
    if (failed.length > 0) {
      message.warning(`连接测试完成，${failed.length} 个来源未采到信号`)
    } else {
      message.success('连接测试通过')
    }
  } catch (error: any) {
    message.error(errorMessage(error, '连接测试失败'))
  } finally {
    testingSourceConnections.value = false
  }
}

async function importMarketSignals() {
  const rawText = signalText.value.trim()
  if (!rawText) {
    message.warning('请先粘贴市场观察')
    return
  }
  importingSignals.value = true
  try {
    const imported = await topicApi.importSignals({ raw_text: rawText, source: '手动观察' })
    signalText.value = ''
    marketSignals.value = [...imported, ...marketSignals.value].slice(0, 8)
    selectedSignalIds.value = [
      ...imported.map(signal => signal.id),
      ...selectedSignalIds.value,
    ].filter((id, index, all) => all.indexOf(id) === index)
    await loadSignalSummary(true)
    message.success(`已导入 ${imported.length} 条市场观察`)
  } catch (error: any) {
    message.error(errorMessage(error, '市场观察导入失败'))
  } finally {
    importingSignals.value = false
  }
}

async function setStatus(idea: TopicIdea, status: TopicIdeaStatus) {
  try {
    await topicApi.updateStatus(idea.id, status)
    topics.value = topics.value.filter(item => item.id !== idea.id)
    selectedTopicIds.value = selectedTopicIds.value.filter(id => id !== idea.id)
    compareResult.value = null
  } catch (error: any) {
    message.error(errorMessage(error, '状态更新失败'))
  }
}

async function deepenTopic(idea: TopicIdea) {
  markBusy(deepeningIds, idea.id)
  try {
    const updated = await topicApi.deepen(idea.id)
    replaceTopic(updated)
    compareResult.value = null
    message.success('选题已深化')
  } catch (error: any) {
    message.error(errorMessage(error, '深化失败'))
  } finally {
    clearBusy(deepeningIds, idea.id)
  }
}

async function evaluateTopic(idea: TopicIdea) {
  markBusy(evaluatingIds, idea.id)
  try {
    const updated = await topicApi.evaluate(idea.id)
    replaceTopic(updated)
    compareResult.value = null
    message.success('选题已评估')
  } catch (error: any) {
    message.error(errorMessage(error, '评估失败'))
  } finally {
    clearBusy(evaluatingIds, idea.id)
  }
}

async function compareTopics() {
  if (selectedTopicIds.value.length < 2 || selectedTopicIds.value.length > 5) {
    message.warning('请选择 2-5 个选题')
    return
  }
  comparing.value = true
  try {
    compareResult.value = await topicApi.compare(selectedTopicIds.value)
    message.success('选题对比完成')
  } catch (error: any) {
    message.error(errorMessage(error, '选题对比失败'))
  } finally {
    comparing.value = false
  }
}

async function confirmAdoptTopic() {
  const idea = pendingAdoptIdea.value
  if (!idea) return
  const title = adoptDraft.title.trim()
  const premise = adoptDraft.premise.trim()
  if (!title) {
    message.warning('请填写新书标题')
    return
  }
  if (!premise) {
    message.warning('请填写核心梗概')
    return
  }
  confirmingAdopt.value = true
  markBusy(adoptingIds, idea.id)
  try {
    if (title !== idea.title || premise !== idea.premise) {
      const updated = await topicApi.update(idea.id, { title, premise })
      replaceTopic(updated)
    }
    const novel = await topicApi.adopt(idea.id)
    message.success('已采用为新书')
    emit('adopted', novel)
    adoptPreviewVisible.value = false
    pendingAdoptIdea.value = null
    visible.value = false
  } catch (error: any) {
    message.error(errorMessage(error, '采用失败'))
  } finally {
    clearBusy(adoptingIds, idea.id)
    confirmingAdopt.value = false
  }
}

watch(
  () => props.show,
  (open) => {
    if (open) {
      void loadTopics()
      void loadSignalSummary(true)
      void loadAutomationSettings()
      void loadSourceCredentials()
      if (signalSources.value.length === 0) void loadSignalSources()
    }
  },
)
</script>

<style scoped>
.topic-panel {
  display: grid;
  grid-template-columns: minmax(280px, 360px) 1fr;
  gap: 18px;
  height: calc(82vh - 92px);
  min-height: 0;
}

.topic-form,
.topic-list {
  min-height: 0;
  overflow: auto;
}

.topic-form {
  padding-right: 4px;
}

.signal-import {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--app-border-color);
}

.collector-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}

.automation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}

.credential-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}

.credential-cookie-field {
  grid-column: 1 / -1;
}

.automation-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.automation-toggle {
  justify-content: space-between;
}

.automation-label {
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.automation-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.automation-error {
  color: #b91c1c;
}

.collector-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  font-size: 12px;
}

.collector-source-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.source-type-label {
  color: var(--app-text-muted);
  font-size: 11px;
}

.source-test-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.source-test-item,
.source-health-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.source-health-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.source-health-name {
  color: var(--app-text-primary);
  font-weight: 600;
}

.topic-list {
  padding-left: 2px;
}

.signal-summary-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--app-border-color);
  border-radius: 8px;
}

.signal-summary-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.signal-summary-total {
  font-size: 13px;
  font-weight: 650;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.summary-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.summary-empty {
  color: var(--app-text-muted);
  font-size: 12px;
}

.comic-opportunity-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
}

.comic-opportunity-item {
  color: var(--app-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.topic-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 12px;
  padding-top: 12px;
}

.compare-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 10px 0 0;
}

.signal-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 0 0;
}

.signal-strip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.signal-list {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.signal-item {
  flex: 0 0 220px;
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--app-border-color);
  border-radius: 8px;
}

.signal-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 650;
}

.signal-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.signal-summary {
  display: -webkit-box;
  margin: 4px 0 6px;
  overflow: hidden;
  color: var(--app-text-secondary);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.compare-count {
  color: var(--app-text-muted);
  font-size: 12px;
}

.compare-result {
  margin-top: 10px;
  border-radius: 8px;
}

.compare-result-header,
.ranking-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.compare-summary,
.ranking-reason,
.ranking-risks {
  margin: 0;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.compare-summary {
  margin-top: 8px;
}

.ranking-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.ranking-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px;
  border: 1px solid var(--app-border-color);
  border-radius: 8px;
}

.ranking-item.recommended {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
}

.ranking-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 650;
}

.ranking-risks {
  display: flex;
  flex-direction: column;
  color: #a16207;
}

.topic-card {
  border-radius: 8px;
}

.topic-card-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.topic-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.topic-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 650;
}

.topic-meta,
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-logline,
.topic-line,
.risk-list {
  margin: 0;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.topic-logline {
  color: var(--app-text-primary);
}

.topic-block,
.risk-list,
.topic-report {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.block-label {
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.risk-list {
  color: #a16207;
}

.topic-report {
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.report-rows,
.report-subrows {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.report-row,
.report-subrow {
  display: grid;
  grid-template-columns: minmax(68px, 0.36fr) minmax(0, 1fr);
  gap: 8px;
  min-width: 0;
}

.report-key,
.report-subkey {
  color: var(--app-text-muted);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.report-value {
  min-width: 0;
  overflow-wrap: anywhere;
}

.report-list {
  margin: 0;
  padding-left: 16px;
}

.topic-actions {
  padding-top: 2px;
}

.adopt-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.adopt-preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.adopt-preview-section {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.adopt-preview-section p {
  margin: 0;
}

.adopt-preview-line {
  overflow-wrap: anywhere;
}

@media (max-width: 860px) {
  .topic-panel {
    grid-template-columns: 1fr;
    height: auto;
    max-height: calc(82vh - 92px);
  }

  .topic-form,
  .topic-list {
    overflow: visible;
  }

  .compare-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .signal-summary-head {
    flex-direction: column;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .automation-grid {
    grid-template-columns: 1fr;
  }

  .credential-grid {
    grid-template-columns: 1fr;
  }
}
</style>
