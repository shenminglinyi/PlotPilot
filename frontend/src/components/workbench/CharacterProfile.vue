<template>
  <div class="character-profile">
    <div class="profile-header">
      <div class="profile-header-row">
        <n-text strong class="profile-header-title">{{ dossierTitle }}</n-text>
        <n-space v-if="selectedCharacterId" size="small" wrap align="center">
          <n-tag v-if="psycheDetail?.role" size="small" round :bordered="false" type="info">
            {{ psycheDetail.role }}
          </n-tag>
          <n-tag
            v-if="mentalTagForHeader"
            size="small"
            round
            :bordered="false"
            type="warning"
          >
            {{ mentalTagForHeader }}
          </n-tag>
        </n-space>
      </div>
      <n-text depth="3" class="profile-header-sub">{{ dossierSubtitle }}</n-text>
    </div>

    <div v-if="!selectedCharacterId" class="profile-empty">
      <n-empty description="左侧点选角色" size="small">
        <template #extra>
          <n-text depth="3" style="font-size: 11px">本栏为只读案卷：叙事核、声线锚点、引擎装配条一次陈列。</n-text>
        </template>
      </n-empty>
    </div>

    <n-spin v-else :show="loading">
      <div class="profile-content">
        <n-card size="small" :bordered="true" class="profile-card dossier-card">
          <template #header>
            <n-text strong class="card-kicker">叙事核</n-text>
          </template>

          <div class="dossier-stack" :class="{ 'dossier-stack--with-sketch': hasNarrativeSketch }">
            <template v-if="hasNarrativeSketch">
              <n-text class="section-label" depth="3">速写</n-text>
              <div class="sketch-block">
                <div class="sketch-body">{{ psycheDetail?.mask_summary }}</div>
              </div>
            </template>

            <n-text class="section-label dossier-stack__t0-label" depth="3">T0</n-text>
            <div class="t0-block">
              <n-text class="t0-heading" depth="3">四维（Bible / 引擎）</n-text>
              <dl class="t0-dl">
                <div class="t0-row belief">
                  <dt>
                    <n-tooltip placement="top-start" trigger="hover">
                      <template #trigger>
                        <span class="t0-key">信念</span>
                      </template>
                      价值分叉时默认站哪边
                    </n-tooltip>
                  </dt>
                  <dd>{{ psycheDetail?.core_belief?.trim() || '—' }}</dd>
                </div>
                <div class="t0-row taboo">
                  <dt>
                    <n-tooltip placement="top-start" trigger="hover">
                      <template #trigger>
                        <span class="t0-key">禁忌</span>
                      </template>
                      碰了就人设崩的那根线
                    </n-tooltip>
                  </dt>
                  <dd>{{ psycheDetail?.taboo?.trim() || '—' }}</dd>
                </div>
                <div class="t0-row voice">
                  <dt>
                    <n-tooltip placement="top-start" trigger="hover">
                      <template #trigger>
                        <span class="t0-key">声线</span>
                      </template>
                      句式、口癖、节奏的总和
                    </n-tooltip>
                  </dt>
                  <dd>{{ psycheDetail?.voice_tag?.trim() || '—' }}</dd>
                </div>
                <div class="t0-row wound">
                  <dt>
                    <n-tooltip placement="top-start" trigger="hover">
                      <template #trigger>
                        <span class="t0-key">触发</span>
                      </template>
                      压力下会犯的蠢 / 过激反应
                    </n-tooltip>
                  </dt>
                  <dd>{{ psycheDetail?.wound?.trim() || '—' }}</dd>
                </div>
              </dl>
              <div v-if="psycheDetail && psycheDetail.trauma_count > 0" class="trauma-inline">
                <n-tag size="tiny" type="warning" :bordered="false">
                  心理转折 ×{{ psycheDetail.trauma_count }}
                </n-tag>
              </div>
              <div
                v-if="(psycheDetail?.evolution_timeline?.length ?? 0) > 0"
                class="evolution-timeline"
              >
                <n-text class="section-label" depth="3">心理变化（引擎按章记录）</n-text>
                <ol class="evo-list">
                  <li
                    v-for="(row, i) in psycheDetail!.evolution_timeline"
                    :key="i"
                    class="evo-item"
                  >
                    <span class="evo-ch">第{{ row.trigger_chapter }}章后</span>
                    <span class="evo-ev">{{ row.trigger_event?.trim() || '（未命名事件）' }}</span>
                    <span v-if="row.changed_fields?.length" class="evo-fields">
                      {{ formatPsycheChangedFields(row.changed_fields) }}
                    </span>
                  </li>
                </ol>
              </div>
            </div>
          </div>
        </n-card>

        <!-- 写章案卷：声线锚点 + 装配条，全部默认展开只读 -->
        <n-card size="small" :bordered="true" class="profile-card dossier-read-card">
          <template #header>
            <n-text strong class="card-kicker">写章案卷</n-text>
          </template>

          <n-text class="section-label" depth="3">声线锚点（Bible）</n-text>
          <dl class="readonly-dl">
            <div class="readonly-row">
              <dt>心理</dt>
              <dd>{{ fieldOrDash(bibleChar?.mental_state) }}</dd>
            </div>
            <div v-if="(bibleChar?.mental_state_reason || '').trim()" class="readonly-row readonly-row--sub">
              <dt>成因</dt>
              <dd>{{ bibleChar?.mental_state_reason }}</dd>
            </div>
            <div class="readonly-row">
              <dt>口癖</dt>
              <dd>{{ fieldOrDash(bibleChar?.verbal_tic) }}</dd>
            </div>
            <div class="readonly-row">
              <dt>小动作</dt>
              <dd>{{ fieldOrDash(bibleChar?.idle_behavior) }}</dd>
            </div>
          </dl>

          <n-divider style="margin: 12px 0 10px" />

          <n-text class="section-label" depth="3">装配条（引擎可读）</n-text>
          <n-text depth="3" class="inject-lead">
            与写章 context 同构；多角场记时不会只带此人。
          </n-text>
          <pre v-if="injectPreviewBody" class="inject-preview inject-preview--open">{{ injectPreviewBody }}</pre>
          <n-text v-else depth="3" style="font-size: 11px">暂无装配预览</n-text>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { characterPsycheApi, type CharacterPsycheDetailDTO } from '@/api/engineCore'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'

interface Props {
  slug: string
  selectedCharacterId: string | null
  /** 工作台当前章：用于隐藏面「第几章后揭示」与预览一致 */
  currentChapterNumber?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapterNumber: null,
})

const message = useMessage()

const loading = ref(false)
const characterName = ref('')
const bibleChar = ref<CharacterDTO | null>(null)
const psycheDetail = ref<CharacterPsycheDetailDTO | null>(null)

const dossierTitle = computed(() =>
  props.selectedCharacterId && characterName.value ? characterName.value : '锚点与档案',
)

const dossierSubtitle = computed(() => {
  if (!props.selectedCharacterId) {
    return '只读案卷 · 叙事核、声线锚点、装配条'
  }
  return '叙事核与写章数据同源 Bible · 本栏仅陈列'
})

const hasNarrativeSketch = computed(() => Boolean(psycheDetail.value?.mask_summary?.trim()))

const mentalTagForHeader = computed(() => {
  const raw = (bibleChar.value?.mental_state || '').trim()
  if (!raw) return ''
  if (raw.toUpperCase() === 'NORMAL') return ''
  return raw
})

const PSYCHE_CHANGE_LABELS: Record<string, string> = {
  core_belief: '信念',
  moral_taboos: '禁忌',
  voice_profile: '声线',
  active_wounds: '触发',
}

function formatPsycheChangedFields(keys: string[]): string {
  return keys.map((k) => PSYCHE_CHANGE_LABELS[k] || k).join('、')
}

function fieldOrDash(v: string | undefined | null) {
  const t = (v || '').trim()
  return t || '—'
}

const injectPreviewBody = computed(() => {
  if (!props.selectedCharacterId) return ''
  const c = bibleChar.value
  if (!c) {
    if (loading.value) return ''
    return '（Bible 中未找到该角色 id，请在世界观 / 作品设定中核对）'
  }
  const desk = props.currentChapterNumber
  const parts: string[] = [`- ${c.name}:`]

  const pub = (c.public_profile || '').trim() || (c.description || '').trim().slice(0, 100)
  if (pub) {
    const ell =
      (c.description || '').trim().length > 100 && !(c.public_profile || '').trim() ? '…' : ''
    parts.push(pub + ell)
  }

  const hp = (c.hidden_profile || '').trim()
  if (hp) {
    const rc = c.reveal_chapter
    if (rc == null || desk == null || desk >= rc) {
      parts.push(`[隐藏面] ${hp}`)
    } else {
      parts.push(`[隐藏面] 第 ${rc} 章后揭示（当前工作台第 ${desk} 章）`)
    }
  }

  const ms = (c.mental_state || '').trim()
  if (ms && ms !== 'NORMAL') {
    parts.push(
      `心理: ${ms}` + ((c.mental_state_reason || '').trim() ? `（${c.mental_state_reason}）` : ''),
    )
  } else if (ms === 'NORMAL' && (c.mental_state_reason || '').trim()) {
    parts.push(`心理: ${ms}（${c.mental_state_reason}）`)
  }

  if ((c.verbal_tic || '').trim()) parts.push(`口头禅: ${c.verbal_tic}`)
  if ((c.idle_behavior || '').trim()) parts.push(`习惯动作: ${c.idle_behavior}`)

  const p = psycheDetail.value
  const cb = ((c.core_belief || '').trim() || (p?.core_belief || '').trim())
  if (cb) parts.push(`T0·信念:${cb.slice(0, 260)}`)

  const taboos = c.moral_taboos || []
  for (const t of taboos.slice(0, 4)) {
    const ts = String(t).trim()
    if (ts) parts.push(`T0·禁忌:${ts.slice(0, 140)}`)
  }
  if (!taboos.length && (p?.taboo || '').trim()) {
    parts.push(`T0·禁忌:${(p?.taboo || '').trim().slice(0, 140)}`)
  }

  const wounds = c.active_wounds || []
  for (const w of wounds.slice(0, 3)) {
    const trig = String((w as { trigger?: string }).trigger || '')
      .trim()
      .slice(0, 100)
    const eff = String((w as { effect?: string }).effect || '')
      .trim()
      .slice(0, 100)
    if (trig || eff) parts.push(`T0·创伤触发:${trig}→${eff}`)
  }
  if (!wounds.length && (p?.wound || '').trim()) {
    parts.push(`T0·创伤:${(p?.wound || '').trim().slice(0, 140)}`)
  }

  const vp = c.voice_profile && typeof c.voice_profile === 'object' ? c.voice_profile : {}
  const bits = (['style', 'sentence_pattern', 'speech_tempo'] as const)
    .map((k) => vp[k as keyof typeof vp])
    .filter((x) => x != null && String(x).trim() !== '')
    .map((x) => String(x))
  if (bits.length) {
    parts.push(`T0·声线结构:${bits.join(' / ').slice(0, 140)}`)
  } else if ((p?.voice_tag || '').trim()) {
    parts.push(`T0·声线:${(p?.voice_tag || '').trim().slice(0, 140)}`)
  }

  return parts.join('\n')
})

async function loadCharacterData() {
  if (!props.selectedCharacterId) {
    bibleChar.value = null
    psycheDetail.value = null
    characterName.value = ''
    return
  }

  loading.value = true
  bibleChar.value = null
  characterName.value = ''
  try {
    const bible = await bibleApi.getBible(props.slug)
    const char =
      bible.characters?.find((x) => x.id === props.selectedCharacterId) ?? null
    bibleChar.value = char
    characterName.value = char?.name || ''

    psycheDetail.value = characterName.value
      ? await characterPsycheApi.get(props.slug, characterName.value).catch(() => null)
      : null
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    message.error(msg || '加载角色数据失败')
    bibleChar.value = null
    psycheDetail.value = null
    characterName.value = ''
  } finally {
    loading.value = false
  }
}

watch(
  () => props.selectedCharacterId,
  () => {
    void loadCharacterData()
  },
  { immediate: true },
)

useWorkbenchDeskTickReload(() => {
  if (props.selectedCharacterId) void loadCharacterData()
})
</script>

<style scoped>
.character-profile {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.profile-header {
  padding: 10px 14px 12px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.profile-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.profile-header-title {
  font-size: 14px;
  min-width: 0;
}

.profile-header-sub {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.45;
  letter-spacing: 0.02em;
}

.profile-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.profile-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile-card {
  flex-shrink: 0;
}

.card-kicker {
  font-size: 13px;
  letter-spacing: 0.04em;
}

.dossier-card :deep(.n-card-header) {
  padding: 10px 14px 8px;
}

.dossier-card :deep(.n-card__content) {
  padding-top: 4px;
}

.dossier-read-card :deep(.n-card__content) {
  padding-top: 6px;
}

.dossier-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dossier-stack__t0-label {
  margin-top: 4px;
}

.dossier-stack--with-sketch .dossier-stack__t0-label {
  margin-top: 10px;
}

.dossier-stack .sketch-body {
  max-height: min(38vh, 300px);
  overflow-y: auto;
}

.sketch-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sketch-body {
  font-size: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--app-page-bg, #fafafa);
  border-left: 3px solid var(--n-primary-color-suppl, #2080f0);
}

.t0-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.t0-heading {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.t0-dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.08));
  border-radius: 6px;
  overflow: hidden;
}

.t0-row {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 0;
  align-items: stretch;
  border-bottom: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.06));
  font-size: 12px;
  line-height: 1.55;
}

.t0-row:last-child {
  border-bottom: none;
}

.t0-row dt {
  margin: 0;
  padding: 6px 8px;
  background: var(--app-page-bg, #f5f5f5);
  border-right: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.06));
  display: flex;
  align-items: center;
}

.t0-row dd {
  margin: 0;
  padding: 6px 10px;
  word-break: break-word;
  color: var(--app-text, rgba(0, 0, 0, 0.85));
}

.t0-key {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-secondary);
  cursor: default;
  border-bottom: 1px dotted var(--n-border-color);
}

.t0-row.belief .t0-key {
  color: #d89614;
}

.t0-row.taboo .t0-key {
  color: #c03030;
}

.t0-row.voice .t0-key {
  color: #2080d0;
}

.t0-row.wound .t0-key {
  color: #7c3aed;
}

.trauma-inline {
  display: flex;
  justify-content: flex-end;
}

.evolution-timeline {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--aitext-split-border, rgba(0, 0, 0, 0.08));
}

.evolution-timeline .section-label {
  margin-bottom: 8px;
}

.evo-list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-text-secondary);
}

.evo-item {
  list-style-position: outside;
}

.evo-ch {
  font-weight: 600;
  color: var(--app-text);
  margin-right: 6px;
}

.evo-ev {
  color: var(--app-text);
}

.evo-fields {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  opacity: 0.88;
}

.section-label {
  display: block;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.readonly-dl {
  margin: 0;
  border: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.08));
  border-radius: 6px;
  overflow: hidden;
}

.readonly-row {
  display: grid;
  grid-template-columns: 44px 1fr;
  font-size: 12px;
  line-height: 1.55;
  border-bottom: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.06));
}

.readonly-row:last-child {
  border-bottom: none;
}

.readonly-row--sub {
  background: var(--app-page-bg, rgba(0, 0, 0, 0.02));
}

.readonly-row dt {
  margin: 0;
  padding: 6px 8px;
  color: var(--n-text-color-3);
  font-size: 11px;
  background: var(--app-page-bg, #f5f5f5);
  border-right: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.06));
}

.readonly-row dd {
  margin: 0;
  padding: 6px 10px;
  word-break: break-word;
}

.inject-lead {
  display: block;
  font-size: 10px;
  line-height: 1.45;
  margin-bottom: 8px;
}

.inject-preview {
  margin: 0;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.5;
  font-family: ui-monospace, 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--app-page-bg, #fafafa);
  border-radius: 6px;
  border: 1px solid var(--aitext-split-border, rgba(0, 0, 0, 0.08));
}

.inject-preview--open {
  max-height: min(42vh, 360px);
  overflow-y: auto;
}
</style>
