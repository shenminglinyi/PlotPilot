<template>
  <div class="wb-panel pp-panel">

    <!-- ── Header ──────────────────────────────────────── -->
    <header class="pp-panel-header">
      <div class="pp-panel-header-main">
        <div class="wb-header-row">
          <span class="pp-panel-title">世界观构建</span>
          <n-tag size="small" round :bordered="false" type="info" style="font-size:10px">5 维度</n-tag>
        </div>
        <div v-if="dataLoaded" class="pp-progress-strip" style="margin-top:6px">
          <n-progress
            type="line"
            :percentage="completenessPercent"
            :height="4"
            :border-radius="2"
            :color="progressColor"
            :rail-color="'var(--app-border)'"
            :show-indicator="false"
            style="flex:1"
          />
          <span class="pp-progress-label">{{ filledDimensions }}/5</span>
        </div>
      </div>
      <div class="pp-panel-actions">
        <n-button
          size="tiny"
          quaternary
          style="font-size:11px"
          @click="toggleAll"
        >
          {{ allExpanded ? '折叠全部' : '展开全部' }}
        </n-button>
        <n-tooltip :content="isDirty ? 'Ctrl+S 保存' : '已是最新'" placement="bottom">
          <template #trigger>
            <n-button
              size="small"
              :type="isDirty ? 'warning' : 'primary'"
              :loading="saving"
              @click="save"
            >
              {{ isDirty ? '● 保存' : '保存' }}
            </n-button>
          </template>
        </n-tooltip>
      </div>
    </header>

    <!-- ── First-load skeleton ────────────────────────── -->
    <div v-if="!dataLoaded && loading" class="wb-skeleton">
      <n-skeleton text :rows="4" />
      <n-skeleton text :rows="4" style="margin-top:16px" />
      <n-skeleton text :rows="3" style="margin-top:16px" />
    </div>

    <!-- ── Scrollable form ────────────────────────────── -->
    <div v-else class="pp-panel-content wb-form-wrap">
      <n-spin :show="loading && dataLoaded" :style="{ minHeight: 0 }">
        <div class="wb-form">

          <n-collapse v-model:expanded-names="expandedNames" display-directive="show">

            <!-- 1. 核心法则与底层逻辑 -->
            <n-collapse-item name="core">
              <template #header>
                <div class="wb-section-head">
                  <div class="wb-icon-badge" style="background:#6366f1">
                    <n-icon size="14" color="#fff"><FlashOutline /></n-icon>
                  </div>
                  <div class="wb-section-titles">
                    <span class="wb-section-title">核心法则与底层逻辑</span>
                    <span class="wb-section-desc">力量体系、物理规律、魔法/科技机制</span>
                  </div>
                  <span class="pp-chip" :class="sectionChipClass('core_rules')" style="margin-left:auto;font-size:10px">
                    {{ sectionChipLabel('core_rules') }}
                  </span>
                </div>
              </template>
              <div class="wb-fields">
                <div class="wb-field">
                  <label class="wb-label">力量体系/科技树</label>
                  <n-input v-model:value="formData.core_rules.power_system" type="textarea"
                    placeholder="魔法的来源？需要付出什么代价？科技水平发展到哪一步？"
                    :autosize="{ minRows: 2, maxRows: 7 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">物理规律</label>
                  <n-input v-model:value="formData.core_rules.physics_rules" type="textarea"
                    placeholder="重力、时间流逝、日夜交替是否与现实不同？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">魔法/科技机制</label>
                  <n-input v-model:value="formData.core_rules.magic_tech" type="textarea"
                    placeholder="详细的运作机制和限制"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
              </div>
            </n-collapse-item>

            <!-- 2. 地理与生态 -->
            <n-collapse-item name="geo">
              <template #header>
                <div class="wb-section-head">
                  <div class="wb-icon-badge" style="background:#10b981">
                    <n-icon size="14" color="#fff"><EarthOutline /></n-icon>
                  </div>
                  <div class="wb-section-titles">
                    <span class="wb-section-title">地理与生态环境</span>
                    <span class="wb-section-desc">地形、气候、资源、生态链</span>
                  </div>
                  <span class="pp-chip" :class="sectionChipClass('geography')" style="margin-left:auto;font-size:10px">
                    {{ sectionChipLabel('geography') }}
                  </span>
                </div>
              </template>
              <div class="wb-fields">
                <div class="wb-field">
                  <label class="wb-label">地形</label>
                  <n-input v-model:value="formData.geography.terrain" type="textarea"
                    placeholder="极寒冰原、无尽沙漠、漂浮群岛？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">气候</label>
                  <n-input v-model:value="formData.geography.climate" type="textarea"
                    placeholder="气候特征和季节变化"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">资源分布</label>
                  <n-input v-model:value="formData.geography.resources" type="textarea"
                    placeholder="水源、矿产、稀有动植物的分布"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">生态链</label>
                  <n-input v-model:value="formData.geography.ecology" type="textarea"
                    placeholder="独特的生物圈，对人类是威胁还是利用对象？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
              </div>
            </n-collapse-item>

            <!-- 3. 社会结构 -->
            <n-collapse-item name="society">
              <template #header>
                <div class="wb-section-head">
                  <div class="wb-icon-badge" style="background:#3b82f6">
                    <n-icon size="14" color="#fff"><PeopleOutline /></n-icon>
                  </div>
                  <div class="wb-section-titles">
                    <span class="wb-section-title">社会结构与权力分配</span>
                    <span class="wb-section-desc">政治、经济、阶级</span>
                  </div>
                  <span class="pp-chip" :class="sectionChipClass('society')" style="margin-left:auto;font-size:10px">
                    {{ sectionChipLabel('society') }}
                  </span>
                </div>
              </template>
              <div class="wb-fields">
                <div class="wb-field">
                  <label class="wb-label">政治体制</label>
                  <n-input v-model:value="formData.society.politics" type="textarea"
                    placeholder="君主专制、议会民主、神权统治、寡头企业？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">经济模式</label>
                  <n-input v-model:value="formData.society.economy" type="textarea"
                    placeholder="货币体系、主要产业、财富分配"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">阶级系统</label>
                  <n-input v-model:value="formData.society.class_system" type="textarea"
                    placeholder="社会分层、阶层流动性、底层困境"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
              </div>
            </n-collapse-item>

            <!-- 4. 历史信仰 -->
            <n-collapse-item name="culture">
              <template #header>
                <div class="wb-section-head">
                  <div class="wb-icon-badge" style="background:#f59e0b">
                    <n-icon size="14" color="#fff"><LibraryOutline /></n-icon>
                  </div>
                  <div class="wb-section-titles">
                    <span class="wb-section-title">历史、信仰与文化</span>
                    <span class="wb-section-desc">关键历史、宗教、禁忌</span>
                  </div>
                  <span class="pp-chip" :class="sectionChipClass('culture')" style="margin-left:auto;font-size:10px">
                    {{ sectionChipLabel('culture') }}
                  </span>
                </div>
              </template>
              <div class="wb-fields">
                <div class="wb-field">
                  <label class="wb-label">关键历史</label>
                  <n-input v-model:value="formData.culture.history" type="textarea"
                    placeholder="大灾变、圣战、革命 - 塑造现在格局的过去"
                    :autosize="{ minRows: 3, maxRows: 8 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">宗教信仰</label>
                  <n-input v-model:value="formData.culture.religion" type="textarea"
                    placeholder="信仰什么？如何影响道德观、节日和日常行为？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">文化禁忌</label>
                  <n-input v-model:value="formData.culture.taboos" type="textarea"
                    placeholder="刻板印象、社会禁忌、不可触碰的底线"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
              </div>
            </n-collapse-item>

            <!-- 5. 沉浸感细节 -->
            <n-collapse-item name="daily">
              <template #header>
                <div class="wb-section-head">
                  <div class="wb-icon-badge" style="background:#ec4899">
                    <n-icon size="14" color="#fff"><LayersOutline /></n-icon>
                  </div>
                  <div class="wb-section-titles">
                    <span class="wb-section-title">沉浸感细节</span>
                    <span class="wb-section-desc">衣食住行、俚语、娱乐 — 直接注入 AI</span>
                  </div>
                  <span class="pp-chip" :class="sectionChipClass('daily_life')" style="margin-left:auto;font-size:10px">
                    {{ sectionChipLabel('daily_life') }}
                  </span>
                </div>
              </template>
              <div class="wb-fields">
                <div class="wb-field">
                  <label class="wb-label">衣食住行</label>
                  <n-input v-model:value="formData.daily_life.food_clothing" type="textarea"
                    placeholder="平时吃什么？穿什么？住哪里？用什么交通工具？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">俚语与口音</label>
                  <n-input v-model:value="formData.daily_life.language_slang" type="textarea"
                    placeholder="特有的词汇、黑话、方言"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
                <div class="wb-field">
                  <label class="wb-label">娱乐方式</label>
                  <n-input v-model:value="formData.daily_life.entertainment" type="textarea"
                    placeholder="闲暇时怎么打发时间？"
                    :autosize="{ minRows: 2, maxRows: 5 }" />
                </div>
              </div>
            </n-collapse-item>

          </n-collapse>

        </div>
      </n-spin>
    </div>

    <!-- ── 冰山理论 ──────────────────────────────────── -->
    <div class="wb-iceberg-bar">
      <div class="wb-ice-heading">
        <n-icon size="12" class="wb-ice-bulb"><BulbOutline /></n-icon>
        <span class="wb-ice-title">冰山理论</span>
      </div>
      <p class="wb-ice-body">
        你可能设定了 100% 的世界观，但在正文中只需展示 10%。
        不要在开篇进行说明文式的「设定倾倒」，而是让主角在行动中自然触碰这些规则。
      </p>
    </div>

    <!-- ── Sticky footer ── 纯状态栏 ─────────────────── -->
    <footer v-if="dataLoaded" class="pp-panel-footer">
      <div class="wb-footer-status">
        <span v-if="isDirty" class="pp-chip pp-chip--warning" style="font-size:10px">● 有未保存的修改</span>
        <span v-else-if="lastSavedAt" class="pp-panel-footer-note">已保存 {{ lastSavedAt }}</span>
        <span v-else class="pp-panel-footer-note">
          {{ filledDimensions > 0 ? `${filledDimensions}/5 维度已填写` : '开始填写各维度设定' }}
        </span>
      </div>
      <span class="wb-shortcut-hint">Ctrl+S 保存</span>
    </footer>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  FlashOutline, EarthOutline, PeopleOutline, LibraryOutline, LayersOutline, BulbOutline,
} from '@vicons/ionicons5'
import { worldbuildingApi } from '@/api/worldbuilding'

interface Props { slug: string }
const props = defineProps<Props>()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const dataLoaded = ref(false)
const isDirty = ref(false)
const lastSavedAt = ref('')

const formData = ref({
  core_rules:  { power_system: '', physics_rules: '', magic_tech: '' },
  geography:   { terrain: '', climate: '', resources: '', ecology: '' },
  society:     { politics: '', economy: '', class_system: '' },
  culture:     { history: '', religion: '', taboos: '' },
  daily_life:  { food_clothing: '', language_slang: '', entertainment: '' },
})

// ── Controlled collapse ──────────────────────────────────────────
const ALL_NAMES = ['core', 'geo', 'society', 'culture', 'daily']
const expandedNames = ref<string[]>(['core', 'geo'])
const allExpanded = computed(() => expandedNames.value.length === ALL_NAMES.length)

function toggleAll() {
  expandedNames.value = allExpanded.value ? [] : [...ALL_NAMES]
}

// ── Section status ───────────────────────────────────────────────
type SectionKey = 'core_rules' | 'geography' | 'society' | 'culture' | 'daily_life'

function sectionValues(key: SectionKey): string[] {
  return Object.values(formData.value[key] as Record<string, string>)
}

function sectionFilledCount(key: SectionKey): number {
  return sectionValues(key).filter(v => v.trim().length > 0).length
}

function sectionTotal(key: SectionKey): number {
  return sectionValues(key).length
}

function sectionChipClass(key: SectionKey): string {
  const filled = sectionFilledCount(key)
  const total = sectionTotal(key)
  if (filled === 0) return 'pp-chip--muted'
  if (filled === total) return 'pp-chip--success'
  return 'pp-chip--warning'
}

function sectionChipLabel(key: SectionKey): string {
  const filled = sectionFilledCount(key)
  const total = sectionTotal(key)
  if (filled === 0) return '待填写'
  if (filled === total) return '✓ 已填'
  return `${filled}/${total}`
}

const filledDimensions = computed<number>(() => {
  const keys: SectionKey[] = ['core_rules', 'geography', 'society', 'culture', 'daily_life']
  return keys.filter(k => sectionFilledCount(k) > 0).length
})

const completenessPercent = computed(() => Math.round((filledDimensions.value / 5) * 100))

const progressColor = computed(() => {
  if (completenessPercent.value < 40) return 'var(--color-warning)'
  if (completenessPercent.value < 100) return 'var(--color-brand)'
  return 'var(--color-success)'
})

// ── Dirty tracking ───────────────────────────────────────────────
watch(formData, () => {
  if (dataLoaded.value) isDirty.value = true
}, { deep: true })

// ── Keyboard shortcut ────────────────────────────────────────────
function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (!saving.value) void save()
  }
}

// ── Load / save ──────────────────────────────────────────────────
const loadWorldbuilding = async () => {
  loading.value = true
  isDirty.value = false
  try {
    const data = await worldbuildingApi.getWorldbuilding(props.slug)
    const isEmpty = !data.core_rules?.power_system && !data.geography?.terrain &&
                    !data.society?.politics && !data.culture?.history && !data.daily_life?.food_clothing
    if (isEmpty) {
      message.warning('世界观尚未创建，首次保存时将自动创建')
    } else {
      formData.value = {
        core_rules:  data.core_rules  || formData.value.core_rules,
        geography:   data.geography   || formData.value.geography,
        society:     data.society     || formData.value.society,
        culture:     data.culture     || formData.value.culture,
        daily_life:  data.daily_life  || formData.value.daily_life,
      }
    }
  } catch (error: any) {
    message.error((error as any).response?.data?.detail || '加载世界观失败')
  } finally {
    loading.value = false
    dataLoaded.value = true
    // Reset dirty after data settles (watch fires synchronously before finally)
    setTimeout(() => { isDirty.value = false }, 0)
  }
}

let savedTimer: ReturnType<typeof setTimeout> | null = null

const save = async () => {
  saving.value = true
  try {
    await worldbuildingApi.updateWorldbuilding(props.slug, formData.value)
    isDirty.value = false
    lastSavedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    message.success('世界观已保存')
    if (savedTimer) clearTimeout(savedTimer)
    savedTimer = setTimeout(() => { lastSavedAt.value = '' }, 8000)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.slug, slug => {
  if (slug) {
    lastSavedAt.value = ''
    void loadWorldbuilding()
  }
})

onMounted(() => {
  loadWorldbuilding()
  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  if (savedTimer) clearTimeout(savedTimer)
})
</script>

<style scoped>
.wb-skeleton { padding: 16px; display: flex; flex-direction: column; }

.wb-form-wrap { padding: 0; }

.wb-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Collapse overrides ──────────────────────────────── */
.wb-form {
  padding: 10px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.wb-form :deep(.n-collapse) {
  border: none;
  background: transparent;
}

.wb-form :deep(.n-collapse-item) {
  border-radius: var(--app-radius-md, 10px);
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  margin-bottom: 8px;
  overflow: hidden;
}

.wb-form :deep(.n-collapse-item__header) {
  padding: 0;
  border-bottom: none;
}

.wb-form :deep(.n-collapse-item__header-main) {
  flex: 1;
  min-width: 0;
}

.wb-form :deep(.n-collapse-item.n-collapse-item--active .n-collapse-item__header) {
  border-bottom: 1px solid var(--app-border);
}

.wb-form :deep(.n-collapse-item__content-inner) {
  padding: 0;
}

/* ── Section header ─────────────────────────────────── */
.wb-section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  width: 100%;
  min-width: 0;
}

.wb-icon-badge {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wb-section-titles {
  flex: 1;
  min-width: 0;
}

.wb-section-title {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  line-height: 1.3;
}

.wb-section-desc {
  display: block;
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 1px;
  line-height: 1.3;
}

/* ── Fields ─────────────────────────────────────────── */
.wb-fields {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wb-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.wb-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

/* ── 冰山理论 底栏 ─────────────────────────────────── */
.wb-iceberg-bar {
  flex-shrink: 0;
  padding: 10px 14px 12px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface);
  border-left: 3px solid #0ea5e9;
}

.wb-ice-heading {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 5px;
}

.wb-ice-bulb {
  color: #0ea5e9;
  flex-shrink: 0;
}

.wb-ice-title {
  font-size: 11px;
  font-weight: 700;
  color: #0ea5e9;
  letter-spacing: 0.04em;
}

.wb-ice-body {
  margin: 0;
  font-size: 11px;
  line-height: 1.7;
  color: var(--app-text-muted);
}

/* ── Footer status bar ──────────────────────────────── */
.wb-footer-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.wb-shortcut-hint {
  font-size: 10px;
  color: var(--app-text-muted);
  opacity: 0.5;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
</style>
