<template>
  <n-modal
    v-model:show="modalOpen"
    :mask-closable="false"
    :close-on-esc="false"
    :closable="true"
    preset="card"
    title="新书设置向导"
    style="width: 94%; max-width: 960px; max-height: 92vh"
    :segmented="{ content: true, footer: true }"
  >
    <n-steps :current="currentStep" :status="stepStatus" size="small" class="wizard-steps">
      <n-step title="世界观" description="5维度框架" class="wizard-step-clickable" @click="goToStep(1)" />
      <n-step title="人物" description="主要角色" class="wizard-step-clickable" @click="goToStep(2)" />
      <n-step title="地图" description="地图系统" class="wizard-step-clickable" @click="goToStep(3)" />
      <n-step title="故事线" description="主线支线" class="wizard-step-clickable" @click="goToStep(4)" />
      <n-step title="开始" description="进入工作台" />
    </n-steps>

    <div class="step-content">
      <!-- 续传提示 -->
      <n-alert v-if="resumedFromStep > 1" type="success" style="margin-bottom: 16px">
        检测到之前的进度，已回到第 {{ resumedFromStep }} 步。您可以继续完成剩余设置。
      </n-alert>

      <!-- Step 1: Generate Worldbuilding + Style (SSE) -->
      <div v-if="currentStep === 1" class="step-panel">
        <n-alert v-if="bibleError" type="error" style="margin-bottom: 16px; width: 100%">
          <div class="wizard-error-text">{{ bibleError }}</div>
        </n-alert>

        <!-- 生成中：骨架屏 + 流式数据 -->
        <div v-if="generatingBible" class="step-generating">
          <div class="generating-header">
            <div class="generating-icon">
              <n-icon size="36" color="#2080f0">
                <IconBook />
              </n-icon>
            </div>
            <div class="generating-text">
              <h3>{{ phaseMessage || '正在生成世界观...' }}</h3>
              <p class="generating-sub">AI 正在逐维度构建您的世界，出一个渲染一个</p>
            </div>
          </div>

          <WizardSkeleton
            type="worldbuilding"
            :active-dimension="activeDimension"
            :completed-dimensions="completedDimensions"
          >
            <template #core_rules>
              <div class="dimension-fields" v-if="orderedWorldbuildingFields('core_rules').length">
                <div v-for="field in orderedWorldbuildingFields('core_rules')" :key="field.key"
                  class="field-card" :class="{ 'field-card--streaming': activeDimension === 'core_rules' && activeField === field.key }">
                  <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                  <div class="field-card__content">{{ field.value }}<span v-if="activeDimension === 'core_rules' && activeField === field.key" class="streaming-cursor">▎</span></div>
                </div>
              </div>
              <div v-else-if="activeDimension === 'core_rules'" class="raw-stream-preview">
                正在等待核心法则子项解析<span class="streaming-cursor">▎</span>
              </div>
            </template>
            <template #geography>
              <div class="dimension-fields" v-if="orderedWorldbuildingFields('geography').length">
                <div v-for="field in orderedWorldbuildingFields('geography')" :key="field.key"
                  class="field-card" :class="{ 'field-card--streaming': activeDimension === 'geography' && activeField === field.key }">
                  <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                  <div class="field-card__content">{{ field.value }}<span v-if="activeDimension === 'geography' && activeField === field.key" class="streaming-cursor">▎</span></div>
                </div>
              </div>
              <div v-else-if="activeDimension === 'geography'" class="raw-stream-preview">
                正在等待地理生态子项解析<span class="streaming-cursor">▎</span>
              </div>
            </template>
            <template #society>
              <div class="dimension-fields" v-if="orderedWorldbuildingFields('society').length">
                <div v-for="field in orderedWorldbuildingFields('society')" :key="field.key"
                  class="field-card" :class="{ 'field-card--streaming': activeDimension === 'society' && activeField === field.key }">
                  <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                  <div class="field-card__content">{{ field.value }}<span v-if="activeDimension === 'society' && activeField === field.key" class="streaming-cursor">▎</span></div>
                </div>
              </div>
              <div v-else-if="activeDimension === 'society'" class="raw-stream-preview">
                正在等待社会结构子项解析<span class="streaming-cursor">▎</span>
              </div>
            </template>
            <template #culture>
              <div class="dimension-fields" v-if="orderedWorldbuildingFields('culture').length">
                <div v-for="field in orderedWorldbuildingFields('culture')" :key="field.key"
                  class="field-card" :class="{ 'field-card--streaming': activeDimension === 'culture' && activeField === field.key }">
                  <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                  <div class="field-card__content">{{ field.value }}<span v-if="activeDimension === 'culture' && activeField === field.key" class="streaming-cursor">▎</span></div>
                </div>
              </div>
              <div v-else-if="activeDimension === 'culture'" class="raw-stream-preview">
                正在等待历史文化子项解析<span class="streaming-cursor">▎</span>
              </div>
            </template>
            <template #daily_life>
              <div class="dimension-fields" v-if="orderedWorldbuildingFields('daily_life').length">
                <div v-for="field in orderedWorldbuildingFields('daily_life')" :key="field.key"
                  class="field-card" :class="{ 'field-card--streaming': activeDimension === 'daily_life' && activeField === field.key }">
                  <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                  <div class="field-card__content">{{ field.value }}<span v-if="activeDimension === 'daily_life' && activeField === field.key" class="streaming-cursor">▎</span></div>
                </div>
              </div>
              <div v-else-if="activeDimension === 'daily_life'" class="raw-stream-preview">
                正在等待沉浸感细节子项解析<span class="streaming-cursor">▎</span>
              </div>
            </template>
          </WizardSkeleton>

          <!-- 文风公约实时预览（SSE 生成中即可见） -->
          <div v-if="styleText" class="style-preview-generating">
            <div class="style-preview-header">
              <n-icon size="16" color="#18a058"><IconCheck /></n-icon>
              <span class="style-preview-title">文风公约</span>
              <n-tag size="tiny" type="success">已生成</n-tag>
            </div>
            <div class="style-preview-content">{{ styleText }}</div>
          </div>
        </div>

        <!-- 生成完成后显示可编辑预览 -->
        <div v-else-if="bibleGenerated" class="bible-preview">
          <n-alert type="success" title="世界观生成完成" style="margin-bottom: 16px">
            请查看并修改世界观设定和文风公约，确认后下一步将基于此生成人物和地点。
          </n-alert>

          <n-collapse :default-expanded-names="['worldbuilding', 'style']">
            <n-collapse-item title="世界观（5维度框架）" name="worldbuilding">
              <n-space vertical size="small">
                <n-card v-for="dim in wbDimensionCards" :key="dim.key" size="small" :title="dim.label">
                  <div class="dimension-fields">
                    <div v-for="field in orderedWorldbuildingFields(dim.key)" :key="field.key" class="field-card field-card--editable">
                      <div class="field-card__title">{{ dimKeyLabels[field.key] || field.key }}</div>
                      <n-input
                        v-model:value="worldbuildingData[dim.key][field.key]"
                        type="textarea"
                        :autosize="{ minRows: 1, maxRows: 4 }"
                        size="small"
                      />
                    </div>
                  </div>
                </n-card>
              </n-space>
            </n-collapse-item>

            <n-collapse-item title="文风公约" name="style">
              <n-card size="small">
                <n-input
                  v-model:value="styleText"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 10 }"
                  placeholder="文风公约"
                />
              </n-card>
            </n-collapse-item>
          </n-collapse>
          <n-button secondary style="margin-top: 12px" @click="startBibleGeneration()">
            重新生成
          </n-button>
        </div>

        <!-- 初始状态 -->
        <div v-else class="step-info">
          <n-icon size="48" color="#18a058">
            <IconBook />
          </n-icon>
          <h3>准备生成世界观</h3>
          <p>AI 将分析您的故事创意，逐维度构建世界观和文风公约。</p>
          <n-button type="primary" style="margin-top: 16px" @click="startBibleGeneration()">
            开始生成
          </n-button>
        </div>
      </div>

      <!-- Step 2: Generate Characters (SSE) -->
      <div v-else-if="currentStep === 2" class="step-panel">
        <n-alert v-if="charactersError" type="error" style="margin-bottom: 16px; width: 100%">
          {{ charactersError }}
        </n-alert>

        <!-- 生成中：逐个角色流式呈现 -->
        <div v-if="generatingCharacters && !charactersGenerated" class="step-generating">
          <div class="generating-header">
            <div class="generating-icon">
              <n-icon size="36" color="#2080f0">
                <IconPeople />
              </n-icon>
            </div>
            <div class="generating-text">
              <h3>{{ phaseMessage || '正在生成人物...' }}</h3>
              <p class="generating-sub">角色逐一呈现</p>
            </div>
          </div>

          <div class="streaming-cards">
            <!-- 已接收的角色 —— 完整卡片 -->
            <transition-group name="fade-slide">
              <div v-for="(char, idx) in streamingCharacters" :key="char.name || idx" class="char-card char-card--filled">
                <div class="char-card__header">
                  <div class="char-card__avatar" :class="char.role === '主角' ? 'char-card__avatar--protag' : ''">{{ char.name?.[0] || '?' }}</div>
                  <div class="char-card__title">
                    <span class="char-card__name">{{ char.name }}</span>
                    <n-tag size="small" :type="char.role === '主角' ? 'success' : 'default'" round>{{ char.role || '角色' }}</n-tag>
                  </div>
                </div>
                <div v-if="char.description" class="char-card__desc">{{ char.description }}</div>
                <div v-if="char.core_belief" class="char-card__anchor">
                  <span class="char-card__anchor-label">核心信念</span>
                  <span>{{ char.core_belief }}</span>
                </div>
                <div v-if="char.verbal_tic || char.idle_behavior" class="char-card__anchor">
                  <span class="char-card__anchor-label">声线/动作</span>
                  <span>{{ [char.verbal_tic, char.idle_behavior].filter(Boolean).join('；') }}</span>
                </div>
                <div v-if="char.relationships && char.relationships.length" class="char-card__relations">
                  <n-tag v-for="(rel, ri) in char.relationships.slice(0, 3)" :key="ri" size="tiny" :bordered="false" type="info">
                    {{ typeof rel === 'string' ? rel : (rel.relation || rel.description || rel.target || '') }}
                  </n-tag>
                </div>
              </div>
            </transition-group>
            <!-- 当前正在生成的骨架位 —— 与卡片结构一致 -->
            <div class="char-card char-card--loading">
              <div class="char-card__header">
                <div class="char-card__avatar char-card__avatar--skeleton">
                  <span class="skeleton-dot__pulse"></span>
                </div>
                <div class="char-card__title">
                  <span class="char-card__skeleton-bar" style="width: 60px"></span>
                  <span class="char-card__skeleton-bar char-card__skeleton-bar--tag"></span>
                </div>
              </div>
              <div class="char-card__skeleton-body">
                <span class="char-card__skeleton-bar" style="width: 90%"></span>
                <span class="char-card__skeleton-bar" style="width: 70%"></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 生成完成后显示可编辑预览 -->
        <div v-else-if="charactersGenerated" class="bible-preview">
          <n-alert type="success" title="人物生成完成" style="margin-bottom: 16px">
            请查看并修改角色设定，确认后将继续。
          </n-alert>
          <n-space vertical size="small" style="margin-bottom: 14px">
            <n-button
              size="small"
              type="primary"
              secondary
              :loading="bulkExtractingPsyche"
              :disabled="!editableCharacters.length"
              @click="runBulkCharacterExtract"
            >
              从简介填充空锚点（无模型）
            </n-button>
            <n-text depth="3" style="font-size: 11px; line-height: 1.5">
              与工作台「角色锚点」同一套 Bible 字段；仅填补仍为空的 T0 / 声线风格等，不覆盖已写内容。可在下方改完再点「确认修改并继续」落库。
            </n-text>
          </n-space>
          <n-list bordered class="character-editor-list">
            <n-list-item v-for="(char, idx) in editableCharacters" :key="idx">
              <div class="editable-character">
                <n-space vertical size="small" style="width: 100%">
                  <div class="character-editor-head">
                    <n-input v-model:value="char.name" size="small" class="character-editor-head__name" placeholder="姓名" />
                    <n-input v-model:value="char.role" size="small" class="character-editor-head__role" placeholder="角色定位" />
                    <n-button quaternary size="small" type="error" @click="editableCharacters.splice(idx, 1)">删除</n-button>
                  </div>

                  <n-grid :cols="2" :x-gap="10" :y-gap="10" responsive="screen">
                    <n-grid-item>
                      <div class="role-lock-panel">
                        <div class="role-lock-panel__title">基础</div>
                        <div class="editable-field">
                          <div class="editable-field__label">功能定位</div>
                          <n-input v-model:value="char.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" size="small" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">公开人设</div>
                          <n-input v-model:value="char.public_profile" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" />
                        </div>
                      </div>
                    </n-grid-item>

                    <n-grid-item>
                      <div class="role-lock-panel role-lock-panel--strong">
                        <div class="role-lock-panel__title">写作锁</div>
                        <div class="editable-field">
                          <div class="editable-field__label">核心信念</div>
                          <n-input v-model:value="char.core_belief" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">道德禁忌</div>
                          <n-dynamic-tags v-model:value="char.moral_taboos" size="small" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">心理状态</div>
                          <n-input v-model:value="char.mental_state" size="small" placeholder="例如：警惕、愧疚、亢奋" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">状态成因</div>
                          <n-input v-model:value="char.mental_state_reason" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" />
                        </div>
                      </div>
                    </n-grid-item>

                    <n-grid-item>
                      <div class="role-lock-panel">
                        <div class="role-lock-panel__title">声线与动作</div>
                        <div class="editable-field">
                          <div class="editable-field__label">口头禅</div>
                          <n-input v-model:value="char.verbal_tic" size="small" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">压力动作</div>
                          <n-input v-model:value="char.idle_behavior" size="small" />
                        </div>
                        <div class="voice-grid">
                          <n-input v-model:value="char.voice_profile.style" size="small" placeholder="声线风格" />
                          <n-input v-model:value="char.voice_profile.sentence_pattern" size="small" placeholder="句式模式" />
                          <n-input v-model:value="char.voice_profile.speech_tempo" size="small" placeholder="语速" />
                        </div>
                      </div>
                    </n-grid-item>

                    <n-grid-item>
                      <div class="role-lock-panel">
                        <div class="role-lock-panel__title">隐藏线索</div>
                        <div class="editable-field">
                          <div class="editable-field__label">隐藏身份 / 真实动机</div>
                          <n-input v-model:value="char.hidden_profile" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" />
                        </div>
                        <div class="editable-field">
                          <div class="editable-field__label">揭示章节</div>
                          <n-input-number v-model:value="char.reveal_chapter" size="small" :min="1" clearable style="width: 100%" />
                        </div>
                        <div v-if="char.relationships && char.relationships.length" class="editable-field">
                          <div class="editable-field__label">人物关系</div>
                          <n-space :size="4" wrap>
                            <n-tag v-for="(rel, ri) in char.relationships" :key="ri" size="small" :bordered="false">
                              {{ formatRelationship(rel) }}
                            </n-tag>
                          </n-space>
                        </div>
                      </div>
                    </n-grid-item>

                    <n-grid-item :span="2" v-if="char.active_wounds.length">
                      <div class="role-lock-panel">
                        <div class="role-lock-panel__title">创伤触发器</div>
                        <div class="wound-grid">
                          <div v-for="(wound, wi) in char.active_wounds" :key="wi" class="wound-row">
                            <n-input v-model:value="wound.description" size="small" placeholder="创伤" />
                            <n-input v-model:value="wound.trigger" size="small" placeholder="触发条件" />
                            <n-input v-model:value="wound.effect" size="small" placeholder="触发反应" />
                          </div>
                        </div>
                      </div>
                    </n-grid-item>
                  </n-grid>
                </n-space>
              </div>
            </n-list-item>
          </n-list>
          <n-button secondary style="margin-top: 12px" @click="startCharactersGeneration()">
            重新生成
          </n-button>
        </div>

        <!-- 初始状态 -->
        <div v-else class="step-info">
          <n-icon size="48" color="#2080f0">
            <IconPeople />
          </n-icon>
          <h3>生成主要角色</h3>
          <p>基于已确认的世界观，AI 将生成主要角色及其关系。</p>
          <n-button type="primary" style="margin-top: 16px" @click="startCharactersGeneration()">
            开始生成
          </n-button>
        </div>
      </div>

      <!-- Step 3: Generate Locations (SSE) -->
      <div v-else-if="currentStep === 3" class="step-panel">
        <n-alert v-if="locationsError" type="error" style="margin-bottom: 16px; width: 100%">
          {{ locationsError }}
        </n-alert>

        <!-- 生成中：骨架屏 + 流式数据 -->
        <div v-if="generatingLocations && !locationsGenerated" class="step-generating">
          <div class="generating-header">
            <div class="generating-icon">
              <n-icon size="36" color="#f0a020">
                <IconMap />
              </n-icon>
            </div>
            <div class="generating-text">
              <h3>{{ phaseMessage || '正在生成地图...' }}</h3>
              <p class="generating-sub">地点逐一呈现</p>
            </div>
          </div>

          <div class="streaming-loc-cards">
            <!-- 已接收的地点 —— 完整卡片 -->
            <transition-group name="fade-slide">
              <div v-for="(loc, idx) in streamingLocations" :key="loc.name || loc.id || idx" class="loc-card loc-card--filled">
                <div class="loc-card__header">
                  <div class="loc-card__icon">📍</div>
                  <div class="loc-card__title">
                    <span class="loc-card__name">{{ loc.name }}</span>
                    <n-tag size="small" type="info" round>{{ loc.type || loc.location_type || '地点' }}</n-tag>
                  </div>
                </div>
                <div v-if="loc.description" class="loc-card__desc">{{ loc.description }}</div>
              </div>
            </transition-group>
            <!-- 当前正在生成的骨架位 -->
            <div class="loc-card loc-card--loading">
              <div class="loc-card__header">
                <div class="loc-card__icon--skeleton"></div>
                <div class="loc-card__title">
                  <span class="loc-card__skeleton-bar" style="width: 70px"></span>
                  <span class="loc-card__skeleton-bar" style="width: 40px; height: 20px; border-radius: 10px"></span>
                </div>
              </div>
              <div class="loc-card__skeleton-body">
                <span class="loc-card__skeleton-bar" style="width: 85%"></span>
                <span class="loc-card__skeleton-bar" style="width: 60%"></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 生成完成后显示可编辑预览 -->
        <div v-else-if="locationsGenerated" class="bible-preview">
          <n-alert type="success" title="地图生成完成" style="margin-bottom: 16px">
            请查看并修改地点设定，确认后将继续。
          </n-alert>
          <BibleLocationsGraphPreview :locations="bibleData.locations || []" />
          <n-list bordered style="margin-top: 16px">
            <n-list-item v-for="(loc, idx) in editableLocations" :key="loc.id || idx">
              <div class="editable-location">
                <n-space vertical size="small" style="width: 100%">
                  <n-space :size="8" align="center">
                    <n-input v-model:value="loc.name" size="small" style="width: 140px" placeholder="地点名" />
                    <n-input v-model:value="loc.location_type" size="small" style="width: 100px" placeholder="类型" />
                    <n-button quaternary size="small" type="error" @click="editableLocations.splice(idx, 1)">删除</n-button>
                  </n-space>
                  <n-input
                    v-model:value="loc.description"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    size="small"
                    placeholder="地点描述"
                  />
                </n-space>
              </div>
            </n-list-item>
          </n-list>
          <n-button secondary style="margin-top: 12px" @click="startLocationsGeneration()">
            重新生成
          </n-button>
        </div>

        <!-- 初始状态 -->
        <div v-else class="step-info">
          <n-icon size="48" color="#f0a020">
            <IconMap />
          </n-icon>
          <h3>生成地图系统</h3>
          <p>基于已确认的世界观和人物，AI 将生成重要地点和地图结构。</p>
          <n-button type="primary" style="margin-top: 16px" @click="startLocationsGeneration()">
            开始生成
          </n-button>
        </div>
      </div>

      <!-- Step 4: 主线候选（LLM 推演） -->
      <div v-else-if="currentStep === 4" class="step-panel step-panel--storyline">
        <n-alert
          v-if="step4RestoredFromCache"
          type="success"
          closable
          class="wizard-hint-alert"
          style="margin-bottom: 12px; width: 100%"
          @close="step4RestoredFromCache = false"
        >
          已恢复上次浏览时的<strong>主线候选</strong>与未提交的自定义文案（本地缓存，减少重复推演）。
        </n-alert>
        <div class="step-info step-info--wide">
          <n-icon size="48" color="#2080f0">
            <IconTimeline />
          </n-icon>
          <h3>确立故事主轴</h3>
          <p>基于你已确认的世界观、人物与地图，系统推演三条可选<strong>主线方向</strong>。选定一条即可落库为「主线」；支线留到工作台再养。</p>
        </div>

        <n-alert v-if="plotSuggestError" type="error" style="margin-bottom: 12px; width: 100%">
          {{ plotSuggestError }}
        </n-alert>
        <n-alert v-if="mainPlotCommitted" type="success" title="已保存主线" style="margin-bottom: 12px; width: 100%">
          已进入本书的主故事线记录，可随时在工作台「设置 → 故事线」中修改。
        </n-alert>

        <n-spin :show="plotSuggesting" style="width: 100%">
          <template #description>
            <span style="color: #999; font-size: 13px">AI 正在推演故事主线方向...</span>
          </template>

          <div v-if="plotSuggesting && !plotOptions.length" style="width: 100%">
            <WizardSkeleton type="storyline" />
            <div v-if="plotSuggestRawPreview" class="plot-stream-preview">
              {{ plotSuggestRawPreview }}
              <span class="streaming-cursor">▎</span>
            </div>
          </div>

          <div v-if="!customMode" class="plot-options-block">
            <n-space vertical :size="12" style="width: 100%">
              <transition-group name="fade-slide">
                <n-card
                  v-for="opt in plotOptions"
                  :key="opt.id"
                  size="small"
                  :bordered="true"
                  class="plot-option-card"
                  :class="{ 'plot-option-card--disabled': mainPlotCommitted }"
                >
                  <template #header>
                    <n-space align="center" :size="8">
                      <n-tag size="small" type="info" round>{{ opt.type || '主线方案' }}</n-tag>
                      <span class="plot-option-title">{{ opt.title }}</span>
                    </n-space>
                  </template>
                  <n-space vertical :size="8">
                    <div class="plot-line"><strong>梗概：</strong>{{ opt.logline }}</div>
                    <div v-if="opt.core_conflict" class="plot-line"><strong>核心冲突：</strong>{{ opt.core_conflict }}</div>
                    <div v-if="opt.starting_hook" class="plot-line"><strong>开篇钩子：</strong>{{ opt.starting_hook }}</div>
                    <n-button
                      type="primary"
                      size="small"
                      :loading="adoptingPlotId === opt.id"
                      :disabled="mainPlotCommitted"
                      @click="adoptPlotOption(opt)"
                    >
                      选这条作为主线
                    </n-button>
                  </n-space>
                </n-card>
              </transition-group>
            </n-space>

            <n-space style="margin-top: 16px; width: 100%" justify="center" :size="12">
              <n-button secondary :disabled="mainPlotCommitted || plotSuggesting" @click="refreshPlotSuggestions">
                换一组方向
              </n-button>
              <n-button secondary :disabled="mainPlotCommitted" @click="customMode = true">
                我有自己的想法
              </n-button>
            </n-space>
          </div>

          <div v-else class="plot-custom-block">
            <n-input
              v-model:value="customLogline"
              type="textarea"
              placeholder="用一句话写下你想写的主线（例如：废柴少年为救妹妹卷入财阀灵根黑市……）"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="mainPlotCommitted"
            />
            <n-space style="margin-top: 12px" :size="8">
              <n-button :disabled="mainPlotCommitted" @click="cancelCustomMainPlot">返回候选</n-button>
              <n-button
                type="primary"
                :loading="adoptingCustom"
                :disabled="mainPlotCommitted"
                @click="adoptCustomMainPlot"
              >
                用这句话作为主线
              </n-button>
            </n-space>
          </div>
        </n-spin>
      </div>

      <!-- Step 5: Complete -->
      <div v-else-if="currentStep === 5" class="step-panel">
        <div class="step-info">
          <n-icon size="48" color="#18a058">
            <IconCheck />
          </n-icon>
          <h3>准备就绪！</h3>
          <p>所有基础设置已完成，现在可以开始创作了。</p>
          <p style="margin-top: 12px; color: #666">您可以随时在工作台的"设置"面板中调整这些内容。</p>
        </div>
      </div>
    </div>

    <template #footer>
      <n-space justify="space-between">
        <n-space>
          <n-button v-if="currentStep > 1 && currentStep < 5" @click="handlePrev">
            上一步
          </n-button>
          <n-button v-if="currentStep > 1 && currentStep < 5" @click="handleSkip">
            跳过向导
          </n-button>
        </n-space>
        <n-space>
          <!-- 步骤1~3：已生成后显示"确认修改并继续" -->
          <n-button
            v-if="(currentStep === 1 && bibleGenerated) || (currentStep === 2 && charactersGenerated) || (currentStep === 3 && locationsGenerated)"
            type="primary"
            :loading="savingStep"
            @click="handleNext"
          >
            确认修改并继续
          </n-button>
          <!-- 步骤4：选了主线后可下一步 -->
          <n-button v-if="currentStep === 4" :disabled="!mainPlotCommitted" @click="handleNext"> 下一步 </n-button>
          <!-- 步骤5：进入工作台 -->
          <n-button v-if="currentStep === 5" type="primary" @click="handleComplete">
            进入工作台
          </n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { h, ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { bibleApi, type BibleDTO, type BibleRelationshipEntry, type CharacterDTO, type StyleNoteDTO, type WorldSettingDTO, consumeBibleGenerateStream, type WorldbuildingDimensionData } from '@/api/bible'
// timeout constants removed - SSE runs until complete or error
import { worldbuildingApi } from '@/api/worldbuilding'
import { consumeMainPlotOptionsStream, workflowApi, type MainPlotOptionDTO } from '@/api/workflow'
import { characterPsycheApi } from '@/api/engineCore'
import { resolveHttpUrl } from '@/api/config'
import BibleLocationsGraphPreview from './BibleLocationsGraphPreview.vue'
import WizardSkeleton from './WizardSkeleton.vue'
import {
  clearWizardUiCache,
  isPlotOptionsCacheFresh,
  markWizardCompleted,
  readWizardUiCache,
  setWizardLastStep,
  writeWizardUiCache,
  type WizardUiCachePayload,
} from '@/utils/wizardStageCache'

const WB_DIMS = ['core_rules', 'geography', 'society', 'culture', 'daily_life'] as const
type WorldbuildingDimKey = (typeof WB_DIMS)[number]

const WB_FIELD_ORDER: Record<WorldbuildingDimKey, string[]> = {
  core_rules: [
    'power_system',
    'progression_path',
    'combat_resolution',
    'physics_rules',
    'magic_tech',
    'version_rules',
    'forbidden_methods',
    'cost_and_limitation',
    'resource_scarcity',
  ],
  geography: [
    'terrain',
    'climate',
    'resources',
    'ecology',
    'forbidden_zones',
    'urban_core',
    'hidden_realms',
  ],
  society: [
    'politics',
    'economy',
    'class_system',
    'power_structure',
    'oppression_mechanism',
    'class_division',
  ],
  culture: [
    'history',
    'religion',
    'taboos',
    'worship',
    'oaths_and_curses',
  ],
  daily_life: [
    'food_clothing',
    'language_slang',
    'entertainment',
    'survival_tactics',
    'market_reality',
    'food_and_drink',
    'slang_and_profanity',
  ],
}

/** 世界观维度 key → 中文标签 */
const dimKeyLabels: Record<string, string> = {
  power_system: '力量体系',
  progression_path: '成长路径',
  combat_resolution: '攻防判定',
  physics_rules: '物理规律',
  magic_tech: '魔法/科技',
  version_rules: '赛季版本',
  forbidden_methods: '禁用手段',
  cost_and_limitation: '代价与限制',
  resource_scarcity: '稀缺资源',
  terrain: '地形',
  climate: '气候',
  resources: '资源',
  ecology: '生态',
  forbidden_zones: '禁区',
  urban_core: '核心城市',
  hidden_realms: '秘境',
  politics: '政治',
  economy: '经济',
  class_system: '阶级',
  power_structure: '权力结构',
  oppression_mechanism: '压迫机制',
  class_division: '阶层划分',
  history: '历史',
  religion: '宗教',
  taboos: '禁忌',
  worship: '崇拜与祭祀',
  oaths_and_curses: '誓言与诅咒',
  food_clothing: '衣食住行',
  language_slang: '俚语口音',
  entertainment: '娱乐方式',
  survival_tactics: '生存策略',
  market_reality: '市场真相',
  food_and_drink: '饮食文化',
  slang_and_profanity: '黑话粗话',
  continent_name: '大陆名称',
  key_regions: '关键区域',
  climate_impact: '气候影响',
  fatal_flaw: '致命缺陷',
  realm_structure: '境界结构',
  dominant_faith: '主流信仰',
  doctrine: '教义',
  rituals: '仪式',
  values: '价值观',
  art_and_literature: '文艺',
  ruling_class: '统治阶层',
  middle_class: '中间阶层',
  lower_class: '底层',
  black_market: '黑市',
  slave_trade: '奴役贸易',
}

function emptyWorldbuildingShape(): Record<(typeof WB_DIMS)[number], Record<string, string>> {
  return {
    core_rules: {},
    geography: {},
    society: {},
    culture: {},
    daily_life: {},
  }
}

function orderedWorldbuildingFields(dim: WorldbuildingDimKey): Array<{ key: string; value: string }> {
  const block = worldbuildingData.value[dim] || {}
  const ordered = WB_FIELD_ORDER[dim] || []
  return ordered
    .map(key => ({ key, value: String(block[key] ?? '') }))
    .filter(field => field.value.trim().length > 0)
}

function createEmptyBible(): BibleDTO {
  return {
    id: '',
    novel_id: '',
    characters: [],
    world_settings: [],
    locations: [],
    timeline_notes: [],
    style_notes: [],
  }
}

function worldbuildingFromWorldSettings(
  settings: { name: string; description?: string }[] | undefined
): Record<(typeof WB_DIMS)[number], Record<string, string>> {
  const out = emptyWorldbuildingShape()
  const dimSet = new Set<string>(WB_DIMS)
  for (const s of settings || []) {
    const dot = s.name.indexOf('.')
    if (dot < 0) continue
    const dim = s.name.slice(0, dot)
    const key = s.name.slice(dot + 1)
    if (!dimSet.has(dim) || !key) continue
    out[dim as (typeof WB_DIMS)[number]][key] = (s.description || '').trim()
  }
  return out
}

function normalizeWorldbuildingFromApi(raw: Record<string, unknown> | null | undefined) {
  const out = emptyWorldbuildingShape()
  if (!raw || typeof raw !== 'object') return out
  for (const d of WB_DIMS) {
    const block = raw[d]
    if (block && typeof block === 'object') {
      const normalized: Record<string, string> = {}
      for (const [key, value] of Object.entries(block as Record<string, unknown>)) {
        const text = String(value ?? '').trim()
        if (text) normalized[key] = text
      }
      out[d] = normalized
    }
  }
  return out
}

function hasWorldbuildingContent(slices: ReturnType<typeof emptyWorldbuildingShape>) {
  return Object.values(slices).some(dim =>
    Object.values(dim).some(value => String(value ?? '').trim().length > 0)
  )
}

function mergeWorldbuildingDisplay(
  fromApi: ReturnType<typeof normalizeWorldbuildingFromApi>,
  fromBibleSettings: ReturnType<typeof worldbuildingFromWorldSettings>
) {
  const out = emptyWorldbuildingShape()
  for (const d of WB_DIMS) {
    const merged = { ...fromBibleSettings[d], ...fromApi[d] }
    out[d] = merged
  }
  return out
}

function styleConventionFromBible(bible: BibleDTO): string {
  const b = bible as BibleDTO & { style?: string }
  if (b.style && String(b.style).trim()) return String(b.style).trim()
  const notes: StyleNoteDTO[] = b.style_notes || []
  const conv = notes.filter(
    (n: StyleNoteDTO) => n.category === '文风公约' || (n.category || '').includes('文风')
  )
  if (conv.length) return conv.map((n: StyleNoteDTO) => (n.content || '').trim()).filter(Boolean).join('\n\n')
  if (notes.length)
    return notes
      .map((n: StyleNoteDTO) => `[${n.category || '风格'}] ${n.content || ''}`.trim())
      .join('\n\n')
  return ''
}

function formatApiError(error: unknown): string {
  const e = error as {
    response?: { data?: { detail?: unknown } }
    message?: string
    code?: string
  }
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d))
    return d.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('；')
  if (d != null && typeof d === 'object') return JSON.stringify(d)
  if (e?.message) return e.message
  return ''
}

function isLikelyTimeoutError(error: unknown): boolean {
  const text = `${formatApiError(error)} ${error instanceof Error ? error.message : ''} ${(error as { code?: string })?.code || ''}`
  return /timeout|ECONNABORTED|ETIMEDOUT|aborted|超时/i.test(text)
}

const IconBook = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z' })
  )

const IconPeople = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z' })
  )

const IconMap = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z' })
  )

const IconTimeline = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M23 8c0 1.1-.9 2-2 2-.18 0-.35-.02-.51-.07l-3.56 3.55c.05.16.07.34.07.52 0 1.1-.9 2-2 2s-2-.9-2-2c0-.18.02-.36.07-.52l-2.55-2.55c-.16.05-.34.07-.52.07s-.36-.02-.52-.07l-4.55 4.56c.05.16.07.33.07.51 0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2c.18 0 .35.02.51.07l4.56-4.55C8.02 9.36 8 9.18 8 9c0-1.1.9-2 2-2s2 .9 2 2c0 .18-.02.36-.07.52l2.55 2.55c.16-.05.34-.07.52-.07s.36.02.52.07l3.55-3.56C19.02 8.35 19 8.18 19 8c0-1.1.9-2 2-2s2 .9 2 2z' })
  )

const IconCheck = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z' })
  )

const props = withDefaults(
  defineProps<{
    novelId: string
    show: boolean
    targetChapters?: number
  }>(),
  { targetChapters: 100 }
)

const message = useMessage()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'complete'): void
  (e: 'skip'): void
}>()

const modalOpen = computed({
  get: () => props.show,
  set: (v: boolean) => {
    if (v) {
      emit('update:show', true)
      return
    }
    requestClose()
  },
})

const currentStep = ref(1)
const stepStatus = ref<'process' | 'finish' | 'error' | 'wait'>('process')
const resumedFromStep = ref(0)

// ── 第1步：SSE 流式生成世界观 ──
const generatingBible = ref(false)
const bibleGenerated = ref(false)
const bibleError = ref('')
const bibleData = ref<BibleDTO>(createEmptyBible())
const worldbuildingData = ref<ReturnType<typeof emptyWorldbuildingShape>>(emptyWorldbuildingShape())
const styleText = ref('')

/** SSE 流式状态 */
const phaseMessage = ref('')
const activeDimension = ref('')
const completedDimensions = ref<Set<string>>(new Set())
const activeField = ref('')
const arrivedFields = ref<Set<string>>(new Set())
/** 维度级流式文本：LLM 逐 token 输出时暂存，字段解析完成后清空 */
const streamingDimText = ref('')
const worldbuildingRawBuffer = ref('')
const sseAbortController = ref<AbortController | null>(null)

const styleConventionDisplay = computed(() => {
  if (styleText.value) return styleText.value
  return styleConventionFromBible(bibleData.value)
})

/** 世界观维度卡片（用于生成完后的折叠面板） */
const wbDimensionCards = computed(() => {
  const labels: Record<string, string> = {
    core_rules: '核心法则',
    geography: '地理生态',
    society: '社会结构',
    culture: '历史文化',
    daily_life: '沉浸感细节',
  }
  return WB_DIMS.map(key => ({ key, label: labels[key], data: worldbuildingData.value[key] }))
})

function nextPendingWorldbuildingDimension(): string {
  return WB_DIMS.find(dim => !completedDimensions.value.has(dim)) || WB_DIMS[0]
}

// ── 第2步：SSE 流式生成人物 ──
const generatingCharacters = ref(false)
const charactersGenerated = ref(false)
const charactersError = ref('')
const streamingCharacters = ref<Array<Partial<EditableCharacter> & { name: string; role: string; description: string }>>([])
const charactersSseAbort = ref<AbortController | null>(null)
/** 可编辑的人物列表（从 bibleData 拷贝，用户可修改后确认落库） */
interface EditableVoiceProfile {
  style: string
  sentence_pattern: string
  speech_tempo: string
  metaphors?: string[]
  catchphrases?: string[]
  [key: string]: unknown
}

interface EditableWound {
  description: string
  trigger: string
  effect: string
  [key: string]: string
}

interface EditableCharacter {
  id: string
  name: string
  role: string
  description: string
  mental_state: string
  mental_state_reason: string
  verbal_tic: string
  idle_behavior: string
  relationships: BibleRelationshipEntry[]
  public_profile: string
  hidden_profile: string
  reveal_chapter: number | null
  core_belief: string
  moral_taboos: string[]
  voice_profile: EditableVoiceProfile
  active_wounds: EditableWound[]
}

function normalizeVoiceProfile(raw: Record<string, unknown> | undefined): EditableVoiceProfile {
  return {
    ...(raw || {}),
    style: String(raw?.style ?? ''),
    sentence_pattern: String(raw?.sentence_pattern ?? ''),
    speech_tempo: String(raw?.speech_tempo ?? ''),
  }
}

function normalizeWounds(raw: Array<Record<string, string>> | undefined): EditableWound[] {
  return (raw || []).map((w) => ({
    ...w,
    description: String(w.description ?? ''),
    trigger: String(w.trigger ?? ''),
    effect: String(w.effect ?? ''),
  }))
}

function formatRelationship(rel: BibleRelationshipEntry | string): string {
  if (typeof rel === 'string') return rel
  return rel.relation || rel.description || rel.target || ''
}

/** 从 CharacterDTO 映射到 EditableCharacter，解析 description 中的 role */
function mapCharacterToEditable(c: CharacterDTO): EditableCharacter {
  let role = c.role || ''
  let desc = c.description || ''
  // 后端存储时把 role 拼到 description 开头："主角 - 描述内容"
  // 如果 role 为空但 description 包含 " - "，尝试从中解析
  if (!role && desc.includes(' - ')) {
    const sepIdx = desc.indexOf(' - ')
    role = desc.slice(0, sepIdx).trim()
    desc = desc.slice(sepIdx + 3).trim()
  } else if (role && desc.startsWith(role) && desc.includes(' - ')) {
    // description 仍包含 role 前缀，去掉重复
    const sepIdx = desc.indexOf(' - ')
    desc = desc.slice(sepIdx + 3).trim()
  }
  return {
    id: c.id || '',
    name: c.name || '',
    role,
    description: desc,
    mental_state: c.mental_state || '',
    mental_state_reason: c.mental_state_reason || '',
    verbal_tic: c.verbal_tic || '',
    idle_behavior: c.idle_behavior || '',
    relationships: c.relationships || [],
    public_profile: c.public_profile || '',
    hidden_profile: c.hidden_profile || '',
    reveal_chapter: c.reveal_chapter ?? null,
    core_belief: c.core_belief || '',
    moral_taboos: [...(c.moral_taboos || [])],
    voice_profile: normalizeVoiceProfile(c.voice_profile || {}),
    active_wounds: normalizeWounds(c.active_wounds as Array<Record<string, string>> | undefined),
  }
}

const editableCharacters = ref<EditableCharacter[]>([])

// ── 第3步：SSE 流式生成地点 ──
const generatingLocations = ref(false)
const locationsGenerated = ref(false)
const locationsError = ref('')
const streamingLocations = ref<Array<{ name: string; id?: string; type?: string; location_type?: string; description: string }>>([])
const locationsSseAbort = ref<AbortController | null>(null)
/** 可编辑的地点列表（从 bibleData 拷贝，用户可修改后确认落库） */
const editableLocations = ref<Array<{ name: string; id?: string; location_type?: string; description: string }>>([])

// ── Step 4：主线推演 ──
const plotOptions = ref<MainPlotOptionDTO[]>([])
const plotSuggesting = ref(false)
const plotSuggestError = ref('')
const mainPlotCommitted = ref(false)
const customMode = ref(false)
const customLogline = ref('')
const adoptingPlotId = ref<string | null>(null)
const adoptingCustom = ref(false)
const step4RestoredFromCache = ref(false)
const plotSuggestRawPreview = ref('')

const chapterEndForStoryline = computed(() => Math.max(1, props.targetChapters ?? 100))

function persistStepFourUiToCache(opts?: { includePlotOptions?: boolean }) {
  if (currentStep.value !== 4) return
  const patch: Partial<Omit<WizardUiCachePayload, 'v' | 'novelId'>> = {
    customMode: customMode.value,
    customLogline: customLogline.value,
  }
  if (opts?.includePlotOptions) {
    patch.plotOptions = plotOptions.value.length ? plotOptions.value : undefined
  }
  writeWizardUiCache(props.novelId, patch)
}

async function loadPlotSuggestions() {
  step4RestoredFromCache.value = false
  plotSuggesting.value = true
  plotSuggestError.value = ''
  plotOptions.value = []
  plotSuggestRawPreview.value = ''
  try {
    let streamError = ''
    await consumeMainPlotOptionsStream(props.novelId, {
      onPhase: (message) => {
        if (message) phaseMessage.value = message
      },
      onChunk: (text) => {
        if (!text) return
        plotSuggestRawPreview.value = `${plotSuggestRawPreview.value}${text}`.slice(-1600)
      },
      onOption: (option) => {
        if (!option?.id) return
        const idx = plotOptions.value.findIndex(o => o.id === option.id)
        if (idx >= 0) {
          plotOptions.value.splice(idx, 1, option)
        } else {
          plotOptions.value = [...plotOptions.value, option]
        }
      },
      onDone: (options) => {
        if (options.length) plotOptions.value = options
      },
      onError: (message) => {
        streamError = message || '流式推演失败'
      },
    })
    if (streamError && !plotOptions.value.length) {
      throw new Error(streamError)
    }
    if (plotOptions.value.length) {
      writeWizardUiCache(props.novelId, { plotOptions: plotOptions.value })
    }
  } catch (e: unknown) {
    try {
      const res = await workflowApi.suggestMainPlotOptions(props.novelId)
      plotOptions.value = res.plot_options || []
      if (plotOptions.value.length) {
        writeWizardUiCache(props.novelId, { plotOptions: plotOptions.value })
      }
    } catch (fallbackError: unknown) {
      let msg = formatApiError(fallbackError) || formatApiError(e) || '推演失败，请重试'
      if (isLikelyTimeoutError(fallbackError) || isLikelyTimeoutError(e)) {
        msg = `请求超时：LLM 响应时间过长。请换更快模型后重试。`
      }
      plotSuggestError.value = msg
    }
  } finally {
    plotSuggesting.value = false
    phaseMessage.value = ''
  }
}

async function refreshPlotSuggestions() {
  await loadPlotSuggestions()
}

async function adoptPlotOption(opt: MainPlotOptionDTO) {
  adoptingPlotId.value = opt.id
  try {
    const parts = [
      opt.logline,
      opt.core_conflict ? `核心冲突：${opt.core_conflict}` : '',
      opt.starting_hook ? `开篇钩子：${opt.starting_hook}` : '',
    ].filter(Boolean)
    await workflowApi.createStoryline(props.novelId, {
      storyline_type: 'main_plot',
      estimated_chapter_start: 1,
      estimated_chapter_end: chapterEndForStoryline.value,
      name: opt.title.slice(0, 200),
      description: parts.join('\n\n').slice(0, 8000),
    })
    mainPlotCommitted.value = true
    clearWizardUiCache(props.novelId)
    message.success('主线已保存')
  } catch (e: unknown) {
    message.error(formatApiError(e) || '保存失败')
  } finally {
    adoptingPlotId.value = null
  }
}

async function adoptCustomMainPlot() {
  const t = customLogline.value.trim()
  if (!t) {
    message.warning('请先写下一句话主线')
    return
  }
  adoptingCustom.value = true
  try {
    await workflowApi.createStoryline(props.novelId, {
      storyline_type: 'main_plot',
      estimated_chapter_start: 1,
      estimated_chapter_end: chapterEndForStoryline.value,
      name: t.length > 80 ? `${t.slice(0, 80)}…` : t,
      description: t.slice(0, 8000),
    })
    mainPlotCommitted.value = true
    customMode.value = false
    clearWizardUiCache(props.novelId)
    message.success('主线已保存')
  } catch (e: unknown) {
    message.error(formatApiError(e) || '保存失败')
  } finally {
    adoptingCustom.value = false
  }
}

function cancelCustomMainPlot() {
  customMode.value = false
  persistStepFourUiToCache()
}

function hydrateStepFourFromCache() {
  step4RestoredFromCache.value = false
  const cached = readWizardUiCache(props.novelId)
  if (!cached) return
  if (cached.customMode != null) customMode.value = cached.customMode
  if (cached.customLogline != null) customLogline.value = cached.customLogline
  if (isPlotOptionsCacheFresh(cached) && cached.plotOptions?.length) {
    plotOptions.value = cached.plotOptions
    step4RestoredFromCache.value = true
    return
  }
  if (cached.plotOptions?.length && !isPlotOptionsCacheFresh(cached)) {
    writeWizardUiCache(props.novelId, { plotOptions: undefined })
  }
}

// ════════════════════════════════════════════════════════════════════════════
// SSE 流式生成函数（含降级到轮询的逻辑）
// ════════════════════════════════════════════════════════════════════════════

/** SSE 是否可用的缓存标记（同会话内只检测一次） */
const sseAvailable = ref<boolean | null>(null)

/** 检测 SSE 流式接口是否可用（同会话内缓存，默认走 SSE） */
async function checkSseAvailable(_novelId: string): Promise<boolean> {
  if (sseAvailable.value !== null) return sseAvailable.value
  // generate-stream 为 POST-only，不做 HEAD/OPTIONS 预检（会 405 污染服务端日志）。
  // 运行时 consumeBibleGenerateStream 失败会自动降级到轮询。
  sseAvailable.value = true
  return true
}

// ── 轮询降级逻辑（保留原轮询代码作为 fallback） ──

const pollTimerRef = ref<ReturnType<typeof setTimeout> | null>(null)
const biblePollEpoch = ref(0)
const step2PollEpoch = ref(0)
const step3PollEpoch = ref(0)

function finishWorldbuildingGeneration() {
  completedDimensions.value = new Set(WB_DIMS)
  activeDimension.value = ''
  activeField.value = ''
  streamingDimText.value = ''
  worldbuildingRawBuffer.value = ''
  generatingBible.value = false
  bibleGenerated.value = true
  phaseMessage.value = ''
  currentStep.value = 1
  setWizardLastStep(props.novelId, 1)
  void loadBibleData()
}

function clearGenerationTimers() {
  if (pollTimerRef.value != null) { clearTimeout(pollTimerRef.value); pollTimerRef.value = null }
}

function clearPollTimer() {
  if (pollTimerRef.value != null) { clearTimeout(pollTimerRef.value); pollTimerRef.value = null }
}

function pollBibleUntil(
  predicate: (bible: BibleDTO) => boolean,
  options: {
    isStale: () => boolean
    onSuccess: () => void
    onTimeout: () => void
    onFatal: (message: string) => void
    watchBackendFailure?: boolean
  },
): void {
  const tick = async () => {
    if (options.isStale()) return
    try {
      const bible = await bibleApi.getBible(props.novelId)
      if (options.isStale()) return
      bibleData.value = bible
      if (predicate(bible)) { options.onSuccess(); return }
      if (options.watchBackendFailure) {
        try {
          const fb = await bibleApi.getBibleGenerationFeedback(props.novelId)
          if (options.isStale()) return
          if (fb.error) { options.onFatal(`${fb.error}（阶段：${fb.stage || '未知'}）`); return }
        } catch { /* */ }
      }
    } catch (err: unknown) {
      if (options.isStale()) return
      options.onFatal(formatApiError(err) || '查询 Bible 失败')
      return
    }
    window.setTimeout(() => { void tick() }, 2000)
  }
  void tick()
}

/** 轮询模式：第1步生成世界观 */
async function startBibleGenerationPoll() {
  clearGenerationTimers()
  biblePollEpoch.value += 1
  const epoch = biblePollEpoch.value
  generatingBible.value = true
  bibleGenerated.value = false
  bibleError.value = ''
  phaseMessage.value = '正在生成世界观...'

  try {
    await bibleApi.generateBible(props.novelId, 'worldbuilding')
    if (biblePollEpoch.value !== epoch || !generatingBible.value) return
    phaseMessage.value = '正在生成世界观和文风...'

    const schedulePoll = (delayMs: number) => {
      clearPollTimer()
      pollTimerRef.value = window.setTimeout(() => { void runPoll() }, delayMs)
    }

    const runPoll = async () => {
      if (biblePollEpoch.value !== epoch || !generatingBible.value) return
      try {
        const status = await bibleApi.getBibleStatus(props.novelId)
        if (biblePollEpoch.value !== epoch || !generatingBible.value) return
        if (status.ready) {
          clearGenerationTimers()
          finishWorldbuildingGeneration()
          return
        }
      } catch (error: unknown) {
        if (biblePollEpoch.value !== epoch) return
        clearGenerationTimers()
        generatingBible.value = false
        bibleError.value = formatApiError(error) || '检查状态失败'
        phaseMessage.value = ''
        return
      }
      if (biblePollEpoch.value !== epoch || !generatingBible.value) return
      schedulePoll(2000)
    }

    schedulePoll(0)
  } catch (error: unknown) {
    if (biblePollEpoch.value !== epoch) return
    generatingBible.value = false
    let detail = formatApiError(error) || '生成失败，请重试'
    if (isLikelyTimeoutError(error)) {
      detail = '提交「世界观生成」时连接超时。请确认 API 已启动后再试。'
    }
    bibleError.value = detail
    phaseMessage.value = ''
  }
}

/** 轮询模式：第2步生成人物 */
async function startCharactersGenerationPoll() {
  step2PollEpoch.value += 1
  const epoch2 = step2PollEpoch.value
  generatingCharacters.value = true
  charactersGenerated.value = false
  charactersError.value = ''
  phaseMessage.value = '正在生成人物...'

  try {
    await bibleApi.generateBible(props.novelId, 'characters')
    pollBibleUntil(
      (b) => (b.characters?.length ?? 0) > 0,
      {
        isStale: () => step2PollEpoch.value !== epoch2 || currentStep.value !== 2 || !generatingCharacters.value,
        watchBackendFailure: true,
        onSuccess: () => { generatingCharacters.value = false; charactersGenerated.value = true; phaseMessage.value = '' },
        onTimeout: () => { generatingCharacters.value = false; charactersError.value = `等待人物生成超时。`; phaseMessage.value = '' },
        onFatal: (msg) => { generatingCharacters.value = false; charactersError.value = msg; phaseMessage.value = '' },
      },
    )
  } catch (error: unknown) {
    generatingCharacters.value = false
    charactersError.value = isLikelyTimeoutError(error) ? '提交人物生成超时' : formatApiError(error) || '人物生成启动失败'
    phaseMessage.value = ''
  }
}

/** 轮询模式：第3步生成地点 */
async function startLocationsGenerationPoll() {
  step3PollEpoch.value += 1
  const epoch3 = step3PollEpoch.value
  generatingLocations.value = true
  locationsGenerated.value = false
  locationsError.value = ''
  phaseMessage.value = '正在生成地图...'

  try {
    await bibleApi.generateBible(props.novelId, 'locations')
    pollBibleUntil(
      (b) => (b.locations?.length ?? 0) > 0,
      {
        isStale: () => step3PollEpoch.value !== epoch3 || currentStep.value !== 3 || !generatingLocations.value,
        watchBackendFailure: true,
        onSuccess: () => { generatingLocations.value = false; locationsGenerated.value = true; phaseMessage.value = '' },
        onTimeout: () => { generatingLocations.value = false; locationsError.value = `等待地图生成超时。`; phaseMessage.value = '' },
        onFatal: (msg) => { generatingLocations.value = false; locationsError.value = msg; phaseMessage.value = '' },
      },
    )
  } catch (error: unknown) {
    generatingLocations.value = false
    locationsError.value = isLikelyTimeoutError(error) ? '提交地图生成超时' : formatApiError(error) || '地图生成启动失败'
    phaseMessage.value = ''
  }
}

// ── SSE 模式入口（自动降级） ──

/** 启动第1步生成（SSE 流式，失败降级到轮询） */
async function startBibleGeneration() {
  try {
    const useSse = await checkSseAvailable(props.novelId)
    if (useSse) {
      startBibleGenerationSSE()
    } else {
      startBibleGenerationPoll()
    }
  } catch {
    // SSE 检测异常时直接尝试 SSE
    startBibleGenerationSSE()
  }
}

/** 启动第1步 SSE 流式生成世界观 */
function startBibleGenerationSSE() {
generatingBible.value = true
bibleGenerated.value = false
bibleError.value = ''
  phaseMessage.value = '正在准备生成环境...'
  activeDimension.value = ''
  completedDimensions.value = new Set()
  activeField.value = ''
  arrivedFields.value = new Set()
  streamingDimText.value = ''
  worldbuildingRawBuffer.value = ''
  worldbuildingData.value = emptyWorldbuildingShape()
  styleText.value = ''

  const ctrl = new AbortController()
  sseAbortController.value = ctrl

  consumeBibleGenerateStream(props.novelId, 'worldbuilding', {
    signal: ctrl.signal,
    onPhase: (phase, msg) => {
      phaseMessage.value = msg
      // 世界观维度级阶段：worldbuilding_core_rules / worldbuilding_geography 等
      if (phase.startsWith('worldbuilding_') && phase !== 'worldbuilding_done') {
        const dimKey = phase.replace('worldbuilding_', '')
        if (WB_DIMS.includes(dimKey as typeof WB_DIMS[number])) {
          if (activeDimension.value && activeDimension.value !== dimKey) {
            completedDimensions.value = new Set([...completedDimensions.value, activeDimension.value])
          }
          activeDimension.value = dimKey
          activeField.value = ''
          arrivedFields.value = new Set()
        } else if (dimKey === 'style') {
          // worldbuilding_style phase：文风公约生成中，清除 activeDimension
          // 让所有维度都显示"等待中"，文风信息通过 phaseMessage 显示
          activeDimension.value = ''
          activeField.value = ''
        } else {
          // 其他 worldbuilding_* phase 事件（如 worldbuilding_done），忽略
        }
      }
      if (phase === 'worldbuilding' || phase === 'worldbuilding_streaming') {
        activeDimension.value = ''
        activeField.value = ''
      }
      if (phase === 'worldbuilding_done') {
        completedDimensions.value = new Set(WB_DIMS)
        activeDimension.value = ''
        activeField.value = ''
        streamingDimText.value = ''
      }
    },
    onStyle: (content) => {
      styleText.value = content
    },
    onStyleChunk: (chunk) => {
      styleText.value += chunk
    },
    onWorldbuildingChunk: (chunk) => {
      if (!chunk) return
      worldbuildingRawBuffer.value = `${worldbuildingRawBuffer.value}${chunk}`.slice(-3000)
      if (!activeDimension.value) {
        activeDimension.value = nextPendingWorldbuildingDimension()
      }
    },
    onWorldbuildingFieldPartial: (dimension, field, value) => {
      if (activeDimension.value !== dimension) {
        if (activeDimension.value) {
          completedDimensions.value = new Set([...completedDimensions.value, activeDimension.value])
        }
        activeDimension.value = dimension
      }
      activeField.value = field
      streamingDimText.value = ''
      // Direct property mutation avoids replacing the entire ref on every token,
      // which would trigger full-tree re-renders during high-frequency streaming.
      const dim = dimension as keyof typeof worldbuildingData.value
      worldbuildingData.value[dim][field] = value
    },
    onWorldbuildingField: (dimension, field, value) => {
      const dim = dimension as keyof typeof worldbuildingData.value
      worldbuildingData.value[dim][field] = value
      if (activeDimension.value !== dimension) {
        if (activeDimension.value) {
          completedDimensions.value = new Set([...completedDimensions.value, activeDimension.value])
        }
        activeDimension.value = dimension
      }
      arrivedFields.value = new Set([...arrivedFields.value, field])
      activeField.value = ''
      streamingDimText.value = ''
    },
    onWorldbuildingDimension: (data: WorldbuildingDimensionData) => {
      const dim = data.dimension as keyof typeof worldbuildingData.value
      Object.assign(worldbuildingData.value[dim], data.content)
      if (activeDimension.value && activeDimension.value !== data.dimension) {
        completedDimensions.value = new Set([...completedDimensions.value, activeDimension.value])
      }
      activeDimension.value = data.dimension
      streamingDimText.value = ''
    },
    onDone: () => {
      finishWorldbuildingGeneration()
    },
    onError: (msg) => {
      // SSE 失败时降级到轮询（后台可能已经启动了生成任务）
      if (msg.includes('HTTP') || msg.includes('fetch') || msg.includes('连接') || msg.includes('Stream')) {
        console.warn('[Wizard] SSE 流式生成失败，降级到轮询模式:', msg)
        startBibleGenerationPoll()
      } else {
        generatingBible.value = false
        bibleError.value = msg
        phaseMessage.value = ''
      }
    },
  })
}

/** 启动第2步生成（SSE 流式，失败降级到轮询） */
async function startCharactersGeneration() {
  try {
    const useSse = await checkSseAvailable(props.novelId)
    if (useSse) {
      startCharactersGenerationSSE()
    } else {
      startCharactersGenerationPoll()
    }
  } catch {
    startCharactersGenerationSSE()
  }
}

/** 启动第2步 SSE 流式生成人物 */
function startCharactersGenerationSSE() {
generatingCharacters.value = true
charactersGenerated.value = false
charactersError.value = ''
  streamingCharacters.value = []
  phaseMessage.value = '正在生成人物...'

  const ctrl = new AbortController()
  charactersSseAbort.value = ctrl

  consumeBibleGenerateStream(props.novelId, 'characters', {
    signal: ctrl.signal,
    onPhase: (_phase, msg) => {
      phaseMessage.value = msg
    },
    onCharacter: (char) => {
      const c = char as Partial<CharacterDTO> & {
        role?: string
        gender?: string
        age?: string
        ghost?: string
        want?: string
        need?: string
        flaw?: string
      }
      if (c.name) {
        // 从 description 中解析 role（后端可能把 role 拼到 description 开头）
        let role = c.role || ''
        let desc = c.description || ''
        if (!role && desc.includes(' - ')) {
          const sepIdx = desc.indexOf(' - ')
          role = desc.slice(0, sepIdx).trim()
          desc = desc.slice(sepIdx + 3).trim()
        } else if (role && desc.startsWith(role) && desc.includes(' - ')) {
          const sepIdx = desc.indexOf(' - ')
          desc = desc.slice(sepIdx + 3).trim()
        }
        streamingCharacters.value = [...streamingCharacters.value, {
          name: c.name,
          role,
          description: desc,
          relationships: c.relationships || [],
          public_profile: c.public_profile || '',
          hidden_profile: c.hidden_profile || '',
          reveal_chapter: c.reveal_chapter ?? null,
          mental_state: c.mental_state || '',
          mental_state_reason: c.mental_state_reason || '',
          verbal_tic: c.verbal_tic || '',
          idle_behavior: c.idle_behavior || '',
          core_belief: c.core_belief || '',
          moral_taboos: [...(c.moral_taboos || [])],
          voice_profile: normalizeVoiceProfile(c.voice_profile || {}),
          active_wounds: normalizeWounds(c.active_wounds as Array<Record<string, string>> | undefined),
        }]
      }
    },
    onCharacterChunk: (_chunk) => {
      // LLM 逐 token 输出中 —— 更新进度提示
      if (!phaseMessage.value.includes('正在生成')) {
        phaseMessage.value = 'AI 正在构思角色...'
      }
    },
    onDone: () => {
      generatingCharacters.value = false
      charactersGenerated.value = true
      phaseMessage.value = ''
      loadBibleData()
    },
    onError: (msg) => {
      // SSE 失败时降级到轮询
      if (msg.includes('HTTP') || msg.includes('fetch') || msg.includes('连接') || msg.includes('Stream')) {
        console.warn('[Wizard] 人物 SSE 失败，降级到轮询:', msg)
        startCharactersGenerationPoll()
      } else {
        generatingCharacters.value = false
        charactersError.value = msg
        phaseMessage.value = ''
      }
    },
  })
}

/** 启动第3步生成（SSE 流式，失败降级到轮询） */
async function startLocationsGeneration() {
  try {
    const useSse = await checkSseAvailable(props.novelId)
    if (useSse) {
      startLocationsGenerationSSE()
    } else {
      startLocationsGenerationPoll()
    }
  } catch {
    startLocationsGenerationSSE()
  }
}

/** 启动第3步 SSE 流式生成地点 */
function startLocationsGenerationSSE() {
generatingLocations.value = true
locationsGenerated.value = false
locationsError.value = ''
  streamingLocations.value = []
  phaseMessage.value = '正在生成地图...'

  const ctrl = new AbortController()
  locationsSseAbort.value = ctrl

  consumeBibleGenerateStream(props.novelId, 'locations', {
    signal: ctrl.signal,
    onPhase: (_phase, msg) => {
      phaseMessage.value = msg
    },
    onLocation: (loc) => {
      const l = loc as { name?: string; id?: string; type?: string; location_type?: string; description?: string }
      if (l.name) {
        streamingLocations.value = [...streamingLocations.value, {
          name: l.name,
          id: l.id,
          type: l.type,
          location_type: l.location_type,
          description: l.description || '',
        }]
      }
    },
    onLocationChunk: (_chunk) => {
      // LLM 逐 token 输出中 —— 更新进度提示
      if (!phaseMessage.value.includes('正在生成')) {
        phaseMessage.value = 'AI 正在构思地点...'
      }
    },
    onDone: () => {
      generatingLocations.value = false
      locationsGenerated.value = true
      phaseMessage.value = ''
      loadBibleData()
    },
    onError: (msg) => {
      // SSE 失败时降级到轮询
      if (msg.includes('HTTP') || msg.includes('fetch') || msg.includes('连接') || msg.includes('Stream')) {
        console.warn('[Wizard] 地图 SSE 失败，降级到轮询:', msg)
        startLocationsGenerationPoll()
      } else {
        generatingLocations.value = false
        locationsError.value = msg
        phaseMessage.value = ''
      }
    },
  })
}

/** 加载完整 Bible 数据（SSE 完成后从 API 刷新） */
async function loadBibleData() {
  try {
    const bible = await bibleApi.getBible(props.novelId)
    bibleData.value = bible

    let fromApi = emptyWorldbuildingShape()
    try {
      const w = await worldbuildingApi.getWorldbuilding(props.novelId)
      fromApi = normalizeWorldbuildingFromApi(w as unknown as Record<string, unknown>)
    } catch { /* 404 */ }
    const fromWs = worldbuildingFromWorldSettings(bible.world_settings)
    worldbuildingData.value = mergeWorldbuildingDisplay(fromApi, fromWs)

    // 始终用后端最新数据刷新文风
    styleText.value = styleConventionFromBible(bible)

    // 将人物/地点拷贝到可编辑列表
    editableCharacters.value = (bible.characters || []).map(mapCharacterToEditable)
    editableLocations.value = (bible.locations || []).map(l => ({
      name: l.name || '',
      id: l.id || undefined,
      location_type: l.location_type || '',
      description: l.description || '',
    }))
  } catch (error) {
    console.error('Failed to load Bible data:', error)
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 向导生命周期
// ════════════════════════════════════════════════════════════════════════════

function resetWizardStateForOpen() {
  currentStep.value = 1
  stepStatus.value = 'process'
  plotOptions.value = []
  mainPlotCommitted.value = false
  customMode.value = false
  customLogline.value = ''
  plotSuggestError.value = ''
  charactersError.value = ''
  locationsError.value = ''
  resumedFromStep.value = 0
  streamingCharacters.value = []
  streamingLocations.value = []
  editableCharacters.value = []
  editableLocations.value = []
}

async function detectWizardProgress(): Promise<number> {
  try {
    const bible = await bibleApi.getBible(props.novelId)
    bibleData.value = bible

    let fromApi = emptyWorldbuildingShape()
    try {
      const w = await worldbuildingApi.getWorldbuilding(props.novelId)
      fromApi = normalizeWorldbuildingFromApi(w as unknown as Record<string, unknown>)
    } catch { /* 404 */ }
    const fromWs = worldbuildingFromWorldSettings(bible.world_settings)
    worldbuildingData.value = mergeWorldbuildingDisplay(fromApi, fromWs)
    styleText.value = styleConventionFromBible(bible)

    // ── 判断后端是否已有数据（用于决定步骤内部显示"生成中"还是"可编辑预览"） ──
    const hasWorldbuilding = hasWorldbuildingContent(fromWs) || hasWorldbuildingContent(worldbuildingData.value)
    const hasStyle = styleConventionFromBible(bible).length > 0
    const hasCharacters = (bible.characters?.length ?? 0) > 0
    const hasLocations = (bible.locations?.length ?? 0) > 0

    // 有数据就标记为"已生成"（步骤内展示可编辑预览），没有则展示"生成中"或初始状态
    if (hasWorldbuilding || hasStyle) {
      bibleGenerated.value = true
    }
    if (hasCharacters) {
      charactersGenerated.value = true
      editableCharacters.value = (bible.characters || []).map(mapCharacterToEditable)
    }
    if (hasLocations) {
      locationsGenerated.value = true
      editableLocations.value = (bible.locations || []).map(l => ({
        name: l.name || '',
        id: l.id || undefined,
        location_type: l.location_type || '',
        description: l.description || '',
      }))
    }

    // ── 判断主线是否已提交 ──
    let hasMainPlot = false
    try {
      const storylines = await workflowApi.getStorylines(props.novelId)
      hasMainPlot = storylines.some(s => s.storyline_type === 'main_plot')
      if (hasMainPlot) {
        mainPlotCommitted.value = true
        clearWizardUiCache(props.novelId)
      }
    } catch { /* 忽略 */ }

    // ── 决定恢复到哪一步：优先用缓存的 lastStep，没缓存才按后端数据推断 ──
    const cached = readWizardUiCache(props.novelId)
    const cachedLastStep = cached?.lastStep

    if (cachedLastStep && cachedLastStep >= 1 && !cached?.wizardCompleted) {
      // 有缓存且未完成 → 回到上次停下的步骤（不跳过）
      resumedFromStep.value = cachedLastStep
      return cachedLastStep
    }

    // 没有缓存时，回到最近一个已生成但尚未确认的步骤。
    // 生成完成只展示可编辑预览，只有用户点"下一步"才进入下一阶段。
    if (!hasWorldbuilding && !hasStyle) {
      resumedFromStep.value = 0
      return 1
    }
    if (!hasCharacters) {
      resumedFromStep.value = 1
      return 1
    }
    if (!hasLocations) {
      resumedFromStep.value = 2
      return 2
    }
    if (!hasMainPlot) {
      resumedFromStep.value = 3
      return 3
    }

    resumedFromStep.value = 5
    return 5
  } catch (err) {
    console.warn('[NovelSetupGuide] detectWizardProgress failed:', err)
    return 1
  }
}

async function runWizardOpenSequence() {
  resetWizardStateForOpen()
  const step = await detectWizardProgress()
  currentStep.value = step
  maxVisitedStep.value = step
  if (step === 4 && !mainPlotCommitted.value) {
    hydrateStepFourFromCache()
  }
  if (step === 1 && !bibleGenerated.value) {
    startBibleGeneration()
  }
}

function stopGenerationOnClose() {
  sseAbortController.value?.abort()
  charactersSseAbort.value?.abort()
  locationsSseAbort.value?.abort()
  generatingBible.value = false
  generatingCharacters.value = false
  generatingLocations.value = false
}

watch(
  () => props.show,
  async (val) => {
    if (val) {
      await runWizardOpenSequence()
    } else {
      stopGenerationOnClose()
      persistStepFourUiToCache({ includePlotOptions: true })
    }
  }
)

onMounted(async () => {
  if (props.show) {
    await runWizardOpenSequence()
  }
})

onUnmounted(() => {
  stopGenerationOnClose()
})

watch(currentStep, (step, prevStep) => {
  // 记录向导进度到缓存
  if (props.show) {
    setWizardLastStep(props.novelId, step)
  }
  // 切换步骤时刷新数据（排除初次加载，首次由 runWizardOpenSequence 处理）
  if (prevStep !== undefined && props.show) {
    void loadBibleData()
  }
  if (step === 4 && props.show && !mainPlotCommitted.value && plotOptions.value.length === 0 && !plotSuggesting.value) {
    void loadPlotSuggestions()
  }
})

watch([customMode, customLogline], () => {
  if (currentStep.value === 4 && props.show) {
    persistStepFourUiToCache()
  }
})

/** 保存中状态 */
const savingStep = ref(false)

/** 保存步骤1的编辑（世界观 + 文风）到后端 */
async function saveWorldbuildingEdits(): Promise<boolean> {
  try {
    // 保存世界观维度数据
    const wbData: Record<string, Record<string, string>> = {}
    for (const dim of WB_DIMS) {
      wbData[dim] = { ...worldbuildingData.value[dim] }
    }
    await worldbuildingApi.updateWorldbuilding(props.novelId, wbData as any)

    // 保存文风公约。世界观主数据已写入 Worldbuilding V2；Bible.world_settings
    // 只保留用户/系统补充的零散规则，不再承载五维世界观。
    const existing = await bibleApi.getBible(props.novelId)
    if (styleText.value) {
      await bibleApi.updateBible(props.novelId, {
        characters: existing.characters || [],
        world_settings: existing.world_settings || [],
        locations: existing.locations || [],
        timeline_notes: existing.timeline_notes || [],
        style_notes: [{
          id: `${props.novelId}-style-1`,
          category: '文风公约',
          content: styleText.value,
        }],
      })
    } else {
      await bibleApi.updateBible(props.novelId, {
        characters: existing.characters || [],
        world_settings: existing.world_settings || [],
        locations: existing.locations || [],
        timeline_notes: existing.timeline_notes || [],
        style_notes: existing.style_notes || [],
      })
    }
    return true
  } catch (e) {
    message.error(formatApiError(e) || '保存世界观修改失败')
    return false
  }
}

/** 保存步骤2的编辑（人物）到后端 */
async function saveCharactersEdits(): Promise<boolean> {
  try {
    const existing = await bibleApi.getBible(props.novelId)
    await bibleApi.updateBible(props.novelId, {
      characters: editableCharacters.value.map((c, idx) => ({
        id: c.id || `${props.novelId}-char-${idx + 1}`,
        name: c.name,
        description: c.description,
        role: c.role,
        mental_state: c.mental_state,
        mental_state_reason: c.mental_state_reason,
        verbal_tic: c.verbal_tic,
        idle_behavior: c.idle_behavior,
        relationships: c.relationships || [],
        public_profile: c.public_profile,
        hidden_profile: c.hidden_profile,
        reveal_chapter: c.reveal_chapter,
        core_belief: c.core_belief,
        moral_taboos: c.moral_taboos,
        voice_profile: c.voice_profile,
        active_wounds: c.active_wounds,
      })),
      world_settings: existing.world_settings || [],
      locations: existing.locations || [],
      timeline_notes: existing.timeline_notes || [],
      style_notes: existing.style_notes || [],
    })
    return true
  } catch (e) {
    message.error(formatApiError(e) || '保存人物修改失败')
    return false
  }
}

const bulkExtractingPsyche = ref(false)

async function runBulkCharacterExtract() {
  const list = editableCharacters.value.filter((c) => c.name.trim())
  if (!list.length) {
    message.warning('请先填写人物姓名')
    return
  }
  bulkExtractingPsyche.value = true
  try {
    const res = await characterPsycheApi.autofill(props.novelId, { mode: 'all' })
    const failed = res.characters.filter((c) => !c.ok)
    await loadBibleData()
    if (failed.length) {
      message.warning(
        `${failed.length} 位失败：` + failed.map((f) => `${f.name}（${(f.error || '').slice(0, 80)}）`).slice(0, 4).join('；'),
      )
    } else {
      message.success(
        `已从简介同步空锚点（启发式，无模型），共 ${res.characters.length} 位角色；请在预览中核对后保存`,
      )
    }
  } catch (e: unknown) {
    message.error(formatApiError(e) || '同步失败')
  } finally {
    bulkExtractingPsyche.value = false
  }
}

/** 保存步骤3的编辑（地点）到后端 */
async function saveLocationsEdits(): Promise<boolean> {
  try {
    const existing = await bibleApi.getBible(props.novelId)
    await bibleApi.updateBible(props.novelId, {
      characters: existing.characters || [],
      world_settings: existing.world_settings || [],
      locations: editableLocations.value.map(l => ({
        id: l.id || '',
        name: l.name,
        description: l.description,
        location_type: l.location_type || '场景',
      })),
      timeline_notes: existing.timeline_notes || [],
      style_notes: existing.style_notes || [],
    })
    return true
  } catch (e) {
    message.error(formatApiError(e) || '保存地点修改失败')
    return false
  }
}

/** 步骤最大可达步骤（用户走过的最远步骤） */
const maxVisitedStep = ref(1)

/** 点击步骤导航条切换步骤（只允许切换到已到过的步骤） */
function goToStep(step: number) {
  if (step < 1 || step > 5) return
  if (step > maxVisitedStep.value) return // 不允许跳到还没到过的步骤
  if (step === currentStep.value) return
  // 正在生成中不允许切换
  if (generatingBible.value || generatingCharacters.value || generatingLocations.value) return
  currentStep.value = step
}

/** 上一步 */
function handlePrev() {
  if (currentStep.value > 1) {
    // 正在生成中不允许返回
    if (generatingBible.value || generatingCharacters.value || generatingLocations.value) return
    currentStep.value--
  }
}

const handleNext = async () => {
  if (savingStep.value) return
  savingStep.value = true
  try {
    if (currentStep.value === 1) {
      // 先保存用户对世界观的编辑
      const ok = await saveWorldbuildingEdits()
      if (!ok) return
      currentStep.value = 2
      maxVisitedStep.value = Math.max(maxVisitedStep.value, 2)
      if (charactersGenerated.value) return
      startCharactersGeneration()
    } else if (currentStep.value === 2) {
      // 先保存用户对人物的编辑
      const ok = await saveCharactersEdits()
      if (!ok) return
      currentStep.value = 3
      maxVisitedStep.value = Math.max(maxVisitedStep.value, 3)
      if (locationsGenerated.value) return
      startLocationsGeneration()
    } else if (currentStep.value === 3) {
      // 先保存用户对地点的编辑
      const ok = await saveLocationsEdits()
      if (!ok) return
      currentStep.value = 4
      maxVisitedStep.value = Math.max(maxVisitedStep.value, 4)
    } else if (currentStep.value < 5) {
      currentStep.value++
      maxVisitedStep.value = Math.max(maxVisitedStep.value, currentStep.value)
    }
  } finally {
    savingStep.value = false
  }
}

const dialog = useDialog()

const handleSkip = () => {
  dialog.warning({
    title: '确认跳过向导',
    content: '已写入作品的数据会保留；第 4 步未提交的主线候选与自定义文案仍会缓存在本机，便于以后从向导继续。',
    positiveText: '跳过',
    negativeText: '取消',
    onPositiveClick: () => {
      markWizardCompleted(props.novelId)
      emit('skip')
      emit('update:show', false)
    },
  })
}

const requestClose = () => {
  dialog.warning({
    title: '关闭向导',
    content: '进度已按步骤写入作品；第 4 步未提交的主线候选与自定义文案会缓存在本机以便下次继续。',
    positiveText: '关闭',
    negativeText: '取消',
    onPositiveClick: () => {
      emit('update:show', false)
    },
  })
}

const handleComplete = () => {
  markWizardCompleted(props.novelId)
  emit('complete')
  emit('update:show', false)
}
</script>

<style scoped>
.step-content {
  margin: 24px 0;
  min-height: 280px;
  max-height: calc(90vh - 280px);
  overflow-y: auto;
}

.step-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.step-info {
  text-align: center;
  max-width: 480px;
}

.step-info h3 {
  margin: 16px 0 8px;
  font-size: 20px;
  font-weight: 600;
}

.step-info p {
  color: #666;
  line-height: 1.6;
  margin: 8px 0;
}

.step-panel--storyline {
  align-items: stretch;
  max-width: 100%;
}

.step-info--wide {
  max-width: 100%;
  text-align: center;
}

/* ── 生成中样式 ── */
.step-generating {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.generating-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f7ff 0%, #e8f5e9 100%);
}

.generating-icon {
  flex-shrink: 0;
}

.generating-text h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.generating-sub {
  margin: 0;
  font-size: 13px;
  color: #888;
}

/* ── 维度字段卡片 ── */
.dimension-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-card {
  background: var(--app-surface, var(--n-color-modal));
  border: 1px solid var(--app-border, var(--n-border-color));
  border-radius: 8px;
  padding: 10px 14px;
  animation: field-appear 0.35s ease;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.field-card:hover {
  border-color: var(--color-brand-border, var(--n-primary-color-hover));
}

.field-card--editable {
  padding: 8px 12px;
}

.field-card--editable .field-card__title {
  margin-bottom: 4px;
}

.field-card__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted, var(--n-text-color-3));
  margin-bottom: 6px;
  letter-spacing: 0;
  text-transform: uppercase;
}

.field-card__content {
  font-size: 13px;
  line-height: 1.65;
  color: var(--app-text-primary, var(--n-text-color-1));
  white-space: pre-wrap;
  word-break: break-word;
}

.raw-stream-preview {
  min-height: 42px;
  padding: 12px 14px 12px 16px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-brand, #2563eb) 9%, transparent), transparent 42%),
    var(--app-surface-subtle, var(--n-color-modal));
  border: 1px solid color-mix(in srgb, var(--color-brand, #2563eb) 34%, var(--app-border, rgba(15, 23, 42, 0.12)));
  border-left: 3px solid var(--color-brand, var(--n-primary-color));
  box-shadow: 0 8px 22px color-mix(in srgb, var(--color-brand, #2563eb) 10%, transparent);
  color: var(--app-text-primary, var(--n-text-color-1));
  font-size: 13px;
  font-weight: 500;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.raw-stream-preview::before {
  content: '实时输出';
  display: block;
  width: fit-content;
  margin-bottom: 6px;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--color-brand-light, rgba(37, 99, 235, 0.08));
  color: var(--color-brand, var(--n-primary-color));
  font-size: 11px;
  font-weight: 700;
}

.plot-stream-preview {
  margin-top: 12px;
  padding: 12px 14px;
  max-height: 160px;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--app-border, var(--n-border-color));
  background: var(--app-surface-subtle, var(--n-color-modal));
  color: var(--app-text-secondary, var(--n-text-color-2));
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@keyframes field-appear {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.field-card--streaming {
  border-color: color-mix(in srgb, var(--color-brand, #2563eb) 46%, var(--app-border, transparent));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-brand, #2563eb) 8%, transparent), transparent 48%),
    var(--app-surface, var(--n-color-modal));
  box-shadow: inset 3px 0 0 var(--color-brand, var(--n-primary-color));
}

.streaming-cursor {
  display: inline;
  color: var(--color-brand, var(--n-primary-color));
  animation: blink-cursor 0.8s ease-in-out infinite;
  font-weight: 700;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 文风公约实时预览（生成中） */
.style-preview-generating {
  margin-top: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-success, #22c55e) 9%, transparent), transparent 45%),
    var(--app-surface-subtle, var(--n-color-modal));
  border: 1px solid color-mix(in srgb, var(--color-success, #22c55e) 34%, var(--app-border, rgba(15, 23, 42, 0.12)));
  border-left: 3px solid var(--color-success, var(--n-success-color));
  animation: fade-in 0.4s ease;
}

.style-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.style-preview-title {
  font-weight: 500;
  font-size: 14px;
  color: var(--app-text-primary, var(--n-text-color-1));
  flex: 1;
}

.style-preview-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--app-text-primary, var(--n-text-color-1));
  padding-left: 24px;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── 流式卡片（人物） ── */
.streaming-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
}

.char-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  transition: all 0.35s ease;
}

.char-card--filled {
  border-color: #18a05830;
  background: #18a05806;
}

.char-card--loading {
  border-style: dashed;
  border-color: #2080f040;
  background: #2080f004;
}

.char-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.char-card__avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  flex-shrink: 0;
}

.char-card__avatar--protag {
  background: linear-gradient(135deg, #f5af19 0%, #f12711 100%);
  box-shadow: 0 0 0 2px #f5af1930;
}

.char-card__avatar--skeleton {
  background: #f0f0f0;
  color: transparent;
}

.char-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.char-card__name {
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.char-card__desc {
  font-size: 13px;
  color: var(--app-text-secondary, var(--n-text-color-2));
  line-height: 1.6;
  margin-top: 8px;
  padding-left: 46px;
}

.char-card__anchor {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin-top: 6px;
  padding-left: 46px;
  color: var(--app-text-primary, var(--n-text-color-1));
  font-size: 12px;
  line-height: 1.5;
}

.char-card__anchor-label {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--color-brand-light, rgba(37, 99, 235, 0.08));
  color: var(--color-brand, var(--n-primary-color));
  font-weight: 700;
}

.char-card__relations {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
  padding-left: 46px;
}

.char-card__skeleton-bar {
  display: inline-block;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e4e4e4 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.char-card__skeleton-bar--tag {
  width: 48px;
  height: 20px;
  border-radius: 10px;
}

.char-card__skeleton-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
  padding-left: 46px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── 流式卡片（地点） ── */
.streaming-loc-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.loc-card {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  transition: all 0.35s ease;
}

.loc-card--filled {
  border-color: #2080f030;
  background: #2080f006;
}

.loc-card--loading {
  border-style: dashed;
  border-color: #f0a02040;
  background: #f0a02004;
}

.loc-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loc-card__icon {
  font-size: 18px;
  flex-shrink: 0;
}

.loc-card__icon--skeleton {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background: #f0f0f0;
  animation: shimmer 1.5s ease-in-out infinite;
  background-size: 200% 100%;
}

.loc-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.loc-card__name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.loc-card__desc {
  font-size: 13px;
  color: #666;
  line-height: 1.5;
  margin-top: 6px;
  padding-left: 26px;
}

.loc-card__skeleton-bar {
  display: inline-block;
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e4e4e4 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.loc-card__skeleton-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 8px;
  padding-left: 26px;
}

/* ── 动画 ── */
.fade-slide-enter-active {
  transition: all 0.4s ease;
}

.fade-slide-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ── 其他 ── */
.bible-preview {
  width: 100%;
}

.plot-options-block,
.plot-custom-block {
  width: 100%;
}

.wizard-error-text {
  white-space: pre-line;
  line-height: 1.65;
  font-size: 13px;
}

.wizard-hint-alert {
  line-height: 1.55;
  text-align: left;
}

.plot-option-title {
  font-weight: 600;
  font-size: 15px;
}

.plot-line {
  font-size: 13px;
  line-height: 1.55;
  color: #555;
  text-align: left;
}

.plot-option-card--disabled {
  opacity: 0.72;
  pointer-events: none;
}

.style-convention-text {
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 14px;
}

/* (editable-field 已替换为 field-card) */

.editable-character,
.editable-location {
  width: 100%;
  padding: 4px 0;
}

.character-editor-list :deep(.n-list-item__main) {
  width: 100%;
}

.character-editor-head {
  display: grid;
  grid-template-columns: minmax(120px, 180px) minmax(100px, 150px) auto;
  gap: 8px;
  align-items: center;
}

.character-editor-head__name,
.character-editor-head__role {
  min-width: 0;
}

.role-lock-panel {
  height: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border, var(--n-border-color));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-brand, #2563eb) 5%, transparent), transparent 42%),
    var(--app-surface, var(--n-color-modal));
}

.role-lock-panel--strong {
  border-color: color-mix(in srgb, var(--color-brand, #2563eb) 30%, var(--app-border, rgba(15, 23, 42, 0.12)));
  box-shadow: inset 3px 0 0 var(--color-brand, var(--n-primary-color));
}

.role-lock-panel__title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-brand, var(--n-primary-color));
}

.editable-field {
  width: 100%;
  margin-top: 8px;
}
.editable-field__label {
  font-size: 12px;
  color: var(--app-text-muted, var(--n-text-color-3));
  margin-bottom: 4px;
  line-height: 1.4;
}

.voice-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.wound-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wound-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

@media (max-width: 720px) {
  .character-editor-head {
    grid-template-columns: 1fr;
  }

  .voice-grid,
  .wound-row {
    grid-template-columns: 1fr;
  }
}

/* 步骤导航可点击 */
.wizard-steps :deep(.n-step) {
  cursor: default;
}
.wizard-step-clickable {
  cursor: pointer !important;
}
.wizard-step-clickable:hover :deep(.n-step-indicator) {
  box-shadow: 0 0 0 3px rgba(24, 160, 88, 0.15);
}
</style>
