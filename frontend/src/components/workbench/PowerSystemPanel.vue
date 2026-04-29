<template>
  <div class="power-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">战力系统</h3>
          <n-tag size="small" round :bordered="false">防崩坏</n-tag>
        </div>
        <p class="panel-lead">
          面向系统文、游戏文和升级流，固定等级规则、角色上限、战斗事件与越级代价，防止后期战力崩坏。
        </p>
      </div>
      <n-button size="small" type="primary" secondary :loading="loading" @click="loadOverview">
        刷新
      </n-button>
      <n-button size="small" secondary :disabled="!overview" @click="copyPowerSystemPrompt">
        复制战力约束
      </n-button>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <n-alert v-if="loadError" type="error" :show-icon="true" class="section-alert">
          {{ loadError }}
        </n-alert>

        <template v-else-if="overview">
          <n-space vertical :size="14">
            <n-alert
              v-for="warning in overview.warnings"
              :key="`${warning.title}-${warning.message}`"
              :type="warningType(warning.severity)"
              :title="warning.title"
              class="section-alert"
            >
              {{ warning.message }}
            </n-alert>

            <n-card size="small" title="系统文 / 游戏文标准规范" :bordered="false">
              <n-code :code="overview.standard" word-wrap />
            </n-card>

            <n-card size="small" title="战力规则" :bordered="false">
              <n-space vertical :size="12">
                <n-form-item label="作品类型" label-placement="top" :show-feedback="false">
                  <n-select v-model:value="rulesForm.genre_type" :options="genreOptions" />
                </n-form-item>
                <n-form-item label="境界 / 等级表" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="rulesForm.tier_schema" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" />
                </n-form-item>
                <n-form-item label="核心规则" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="rulesForm.core_rules" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" />
                </n-form-item>
                <n-form-item label="禁忌规则" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="rulesForm.taboo_rules" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" />
                </n-form-item>
                <n-form-item label="升级节奏" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="rulesForm.escalation_rules" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" />
                </n-form-item>
                <n-space :size="8">
                  <n-button secondary :loading="suggestingRules" @click="suggestRules">
                    AI 生成规则
                  </n-button>
                  <n-button type="primary" secondary :loading="savingRules" @click="saveRules">
                    保存战力规则
                  </n-button>
                </n-space>
              </n-space>
            </n-card>

            <n-card size="small" title="角色战力档案" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input v-model:value="profileForm.character_name" placeholder="角色名" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="profileForm.tier" placeholder="当前境界 / 等级" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="profileForm.rank_score" :min="0" :max="100" style="width: 100%" placeholder="战力分 0-100" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="profileForm.last_verified_chapter" :min="1" style="width: 100%" placeholder="最近校验章节" />
                  </n-grid-item>
                </n-grid>
                <n-input v-model:value="profileForm.abilities" type="textarea" placeholder="能力 / 技能 / 装备" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-input v-model:value="profileForm.limitations" type="textarea" placeholder="弱点 / 消耗 / 冷却 / 代价" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-input v-model:value="profileForm.growth_stage" type="textarea" placeholder="成长阶段 / 下次突破条件" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-space :size="8">
                  <n-button secondary :loading="suggestingProfile" @click="suggestProfile">
                    AI 生成档案
                  </n-button>
                  <n-button type="primary" secondary :loading="savingProfile" :disabled="!profileForm.character_name.trim()" @click="saveProfile">
                    保存角色档案
                  </n-button>
                </n-space>

                <n-empty v-if="overview.profiles.length === 0" description="暂无角色战力档案" size="small" />
                <n-space v-else vertical :size="8">
                  <div v-for="profile in overview.profiles" :key="profile.id" class="profile-row">
                    <n-space justify="space-between" align="center">
                      <n-text strong>{{ profile.character_name }}</n-text>
                      <n-tag size="small" round :type="profile.rank_score >= 80 ? 'warning' : 'info'">
                        {{ profile.tier || '未定阶' }} · {{ profile.rank_score }}
                      </n-tag>
                    </n-space>
                    <n-text depth="3" style="font-size:12px">
                      能力：{{ profile.abilities || '未记录' }}
                    </n-text>
                    <n-text depth="3" style="font-size:12px">
                      限制：{{ profile.limitations || '未记录' }}
                    </n-text>
                  </div>
                </n-space>
              </n-space>
            </n-card>

            <n-card size="small" title="战斗 / 升级事件" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input-number v-model:value="eventForm.chapter_number" :min="1" style="width: 100%" placeholder="章节号" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="eventForm.character_name" placeholder="角色名" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="eventForm.event_type" :options="eventTypeOptions" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="eventForm.power_delta" :min="-10" :max="10" style="width: 100%" placeholder="战力变化" />
                  </n-grid-item>
                </n-grid>
                <n-input v-model:value="eventForm.opponent" placeholder="对手 / 副本 / 阶段目标" />
                <n-input v-model:value="eventForm.outcome" type="textarea" placeholder="结果：例如越级击败但重伤" :autosize="{ minRows: 2, maxRows: 4 }" />
                <n-input v-model:value="eventForm.evidence" type="textarea" placeholder="证据：代价、克制、底牌、环境、冷却、受伤等" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-space :size="8">
                  <n-button secondary :loading="suggestingEvent" @click="suggestEvent">
                    AI 生成事件
                  </n-button>
                  <n-button type="primary" secondary :loading="savingEvent" :disabled="!eventForm.character_name.trim()" @click="saveEvent">
                    记录战力事件
                  </n-button>
                </n-space>

                <n-empty v-if="overview.recent_events.length === 0" description="暂无战力事件" size="small" />
                <n-timeline v-else size="small">
                  <n-timeline-item
                    v-for="event in overview.recent_events"
                    :key="event.id"
                    type="info"
                    :title="`${event.character_name} · ${event.outcome || event.event_type}`"
                    :time="`第${event.chapter_number}章 · Δ ${event.power_delta}`"
                  >
                    <n-text depth="3" style="font-size:12px">
                      {{ event.evidence || '未记录代价/证据' }}
                    </n-text>
                  </n-timeline-item>
                </n-timeline>
              </n-space>
            </n-card>
          </n-space>
        </template>

        <n-empty v-else description="暂无战力系统数据" size="small" />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { powerSystemApi, type PowerSystemOverview } from '@/api/powerSystem'
import { novelproSuggestionsApi } from '@/api/novelproSuggestions'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const savingRules = ref(false)
const savingProfile = ref(false)
const savingEvent = ref(false)
const suggestingRules = ref(false)
const suggestingProfile = ref(false)
const suggestingEvent = ref(false)
const loadError = ref('')
const overview = ref<PowerSystemOverview | null>(null)

const genreOptions = [
  { label: '系统文 / 游戏文', value: 'system_game' },
  { label: '玄幻升级流', value: 'fantasy_progression' },
  { label: '都市异能', value: 'urban_power' },
  { label: '自定义', value: 'custom' },
]

const eventTypeOptions = [
  { label: '战斗', value: 'battle' },
  { label: '升级', value: 'level_up' },
  { label: '副本', value: 'dungeon' },
  { label: '装备/技能', value: 'skill' },
  { label: '失败/受伤', value: 'cost' },
]

const rulesForm = reactive({
  genre_type: 'system_game',
  tier_schema: '',
  core_rules: '',
  taboo_rules: '',
  escalation_rules: '',
})

const profileForm = reactive({
  character_name: '',
  tier: '',
  rank_score: 0,
  abilities: '',
  limitations: '',
  growth_stage: '',
  last_verified_chapter: null as number | null,
  notes: '',
})

const eventForm = reactive({
  chapter_number: props.currentChapter || 1,
  character_name: '',
  event_type: 'battle',
  opponent: '',
  outcome: '',
  power_delta: 0,
  evidence: '',
})

function warningType(value: string) {
  if (value === 'error') return 'error'
  if (value === 'warning') return 'warning'
  return 'info'
}

function applyRulesForm() {
  if (!overview.value) return
  rulesForm.genre_type = overview.value.rules.genre_type || 'system_game'
  rulesForm.tier_schema = overview.value.rules.tier_schema || ''
  rulesForm.core_rules = overview.value.rules.core_rules || ''
  rulesForm.taboo_rules = overview.value.rules.taboo_rules || ''
  rulesForm.escalation_rules = overview.value.rules.escalation_rules || ''
}

function suggestionText(fields: Record<string, unknown>, key: string) {
  const value = fields[key]
  if (value == null) return ''
  return String(value)
}

function suggestionNumber(fields: Record<string, unknown>, key: string, fallback: number | null) {
  const value = fields[key]
  if (value == null || value === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

async function loadOverview() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await powerSystemApi.getOverview(props.slug)
    applyRulesForm()
  } catch {
    overview.value = null
    loadError.value = '加载战力系统失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function suggestRules() {
  suggestingRules.value = true
  try {
    const result = await novelproSuggestionsApi.suggestFields(props.slug, {
      suggestion_type: 'power_rules',
      chapter_number: props.currentChapter,
      fields: ['genre_type', 'tier_schema', 'core_rules', 'taboo_rules', 'escalation_rules'],
      target: {
        warning_count: overview.value?.warnings.length || 0,
      },
      current_values: { ...rulesForm },
      instruction: '根据初始设定和当前战力风险，生成适合系统文/游戏文的等级表、核心规则、禁忌规则和升级节奏。',
    })
    rulesForm.genre_type = suggestionText(result.fields, 'genre_type') || rulesForm.genre_type
    rulesForm.tier_schema = suggestionText(result.fields, 'tier_schema') || rulesForm.tier_schema
    rulesForm.core_rules = suggestionText(result.fields, 'core_rules') || rulesForm.core_rules
    rulesForm.taboo_rules = suggestionText(result.fields, 'taboo_rules') || rulesForm.taboo_rules
    rulesForm.escalation_rules = suggestionText(result.fields, 'escalation_rules') || rulesForm.escalation_rules
    message.success(result.rationale || '已生成战力规则建议')
  } catch {
    message.error('生成战力规则失败，请稍后重试')
  } finally {
    suggestingRules.value = false
  }
}

async function saveRules() {
  savingRules.value = true
  try {
    await powerSystemApi.saveRules(props.slug, { ...rulesForm })
    message.success('战力规则已保存')
    await loadOverview()
  } catch {
    message.error('保存战力规则失败')
  } finally {
    savingRules.value = false
  }
}

async function suggestProfile() {
  suggestingProfile.value = true
  try {
    const result = await novelproSuggestionsApi.suggestFields(props.slug, {
      suggestion_type: 'power_profile',
      chapter_number: props.currentChapter,
      fields: ['character_name', 'tier', 'rank_score', 'abilities', 'limitations', 'growth_stage', 'last_verified_chapter', 'notes'],
      target: {
        existing_profiles: overview.value?.profiles.map(profile => profile.character_name) || [],
      },
      current_values: { ...profileForm },
      instruction: '根据当前设定和战力规则，为一个最需要补档案的角色生成战力档案，必须包含限制/代价，避免无解化。',
    })
    profileForm.character_name = suggestionText(result.fields, 'character_name') || profileForm.character_name
    profileForm.tier = suggestionText(result.fields, 'tier') || profileForm.tier
    profileForm.rank_score = suggestionNumber(result.fields, 'rank_score', profileForm.rank_score) || 0
    profileForm.abilities = suggestionText(result.fields, 'abilities') || profileForm.abilities
    profileForm.limitations = suggestionText(result.fields, 'limitations') || profileForm.limitations
    profileForm.growth_stage = suggestionText(result.fields, 'growth_stage') || profileForm.growth_stage
    profileForm.last_verified_chapter = suggestionNumber(result.fields, 'last_verified_chapter', profileForm.last_verified_chapter)
    profileForm.notes = suggestionText(result.fields, 'notes') || profileForm.notes
    message.success(result.rationale || '已生成角色战力档案建议')
  } catch {
    message.error('生成角色档案失败，请稍后重试')
  } finally {
    suggestingProfile.value = false
  }
}

async function saveProfile() {
  savingProfile.value = true
  try {
    await powerSystemApi.saveProfile(props.slug, { ...profileForm })
    message.success('角色战力档案已保存')
    profileForm.character_name = ''
    profileForm.tier = ''
    profileForm.rank_score = 0
    profileForm.abilities = ''
    profileForm.limitations = ''
    profileForm.growth_stage = ''
    profileForm.last_verified_chapter = null
    profileForm.notes = ''
    await loadOverview()
  } catch {
    message.error('保存角色战力档案失败')
  } finally {
    savingProfile.value = false
  }
}

async function suggestEvent() {
  suggestingEvent.value = true
  try {
    const result = await novelproSuggestionsApi.suggestFields(props.slug, {
      suggestion_type: 'power_event',
      chapter_number: eventForm.chapter_number || props.currentChapter,
      fields: ['chapter_number', 'character_name', 'event_type', 'opponent', 'outcome', 'power_delta', 'evidence'],
      target: {
        recent_warnings: overview.value?.warnings || [],
        profiles: overview.value?.profiles.map(profile => ({
          character_name: profile.character_name,
          tier: profile.tier,
          rank_score: profile.rank_score,
        })) || [],
      },
      current_values: { ...eventForm },
      instruction: '根据当前章节和战力风险生成一条战斗/升级事件。若涉及胜利或升级，必须写清代价、克制、环境、底牌或冷却。',
    })
    eventForm.chapter_number = suggestionNumber(result.fields, 'chapter_number', eventForm.chapter_number) || eventForm.chapter_number
    eventForm.character_name = suggestionText(result.fields, 'character_name') || eventForm.character_name
    eventForm.event_type = suggestionText(result.fields, 'event_type') || eventForm.event_type
    eventForm.opponent = suggestionText(result.fields, 'opponent') || eventForm.opponent
    eventForm.outcome = suggestionText(result.fields, 'outcome') || eventForm.outcome
    eventForm.power_delta = suggestionNumber(result.fields, 'power_delta', eventForm.power_delta) || 0
    eventForm.evidence = suggestionText(result.fields, 'evidence') || eventForm.evidence
    message.success(result.rationale || '已生成战力事件建议')
  } catch {
    message.error('生成战力事件失败，请稍后重试')
  } finally {
    suggestingEvent.value = false
  }
}

async function saveEvent() {
  savingEvent.value = true
  try {
    await powerSystemApi.createEvent(props.slug, { ...eventForm })
    message.success('战力事件已记录')
    eventForm.character_name = ''
    eventForm.opponent = ''
    eventForm.outcome = ''
    eventForm.power_delta = 0
    eventForm.evidence = ''
    await loadOverview()
  } catch {
    message.error('记录战力事件失败')
  } finally {
    savingEvent.value = false
  }
}

function copyPowerSystemPrompt() {
  if (!overview.value) return
  const prompt = [
    '【战力系统硬约束】',
    overview.value.standard,
    '',
    '【境界 / 等级表】',
    overview.value.rules.tier_schema,
    '',
    '【核心规则】',
    overview.value.rules.core_rules,
    '',
    '【禁忌规则】',
    overview.value.rules.taboo_rules,
    '',
    '【升级节奏】',
    overview.value.rules.escalation_rules,
    '',
    '【角色战力档案】',
    ...overview.value.profiles.map((profile) => (
      `- ${profile.character_name}：${profile.tier || '未定阶'}，战力分 ${profile.rank_score}；能力：${profile.abilities || '未记录'}；限制：${profile.limitations || '未记录'}`
    )),
    '',
    '写作时必须遵守以上规则；任何越级胜利都要写清代价、克制、环境或底牌，禁止临时发明新战力规则。',
  ].join('\n')

  void navigator.clipboard.writeText(prompt).then(
    () => message.success('已复制战力约束提示词'),
    () => message.error('复制战力约束失败'),
  )
}

watch(
  () => [props.slug, props.currentChapter] as const,
  () => {
    if (props.currentChapter) {
      eventForm.chapter_number = props.currentChapter
    }
    void loadOverview()
  },
)

onMounted(() => {
  void loadOverview()
})
</script>

<style scoped>
.power-panel {
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

.profile-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 8px;
  background: var(--app-surface);
}
</style>
