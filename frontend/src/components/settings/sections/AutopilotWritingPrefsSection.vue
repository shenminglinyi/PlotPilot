<template>
  <div class="writing-prefs">
    <template v-if="!novelSlug">
      <div class="empty-state">
        <div class="empty-title">未绑定书目</div>
        <p class="empty-desc">
          这些参数保存在当前作品的 <span class="mono">generation_prefs</span> 中。请从书库打开作品并进入工作台（路由含
          <span class="mono">/book/&lt;id&gt;/…</span>）后再配置。
        </p>
      </div>
    </template>

    <template v-else>
      <header class="prefs-header">
        <div class="prefs-header-text">
          <h2 class="prefs-title">全托管控制</h2>
          <p class="prefs-sub">
            节拍硬帽、智能截断、章末审阅闸门与指挥器相位阈值；开关即时保存，相位阈值需点击保存。
          </p>
        </div>
        <n-tag v-if="novelTitle" size="small" :bordered="false" class="book-tag">{{ novelTitle }}</n-tag>
      </header>

      <n-spin :show="loading">
        <div class="prefs-stack">
          <!-- 字数与安全网 -->
          <n-card size="small" :bordered="true" class="prefs-card">
            <div class="card-head">
              <span class="card-title">字数与安全网</span>
              <n-text depth="3" class="card-caption">节拍级硬上限与超长时的落盘策略</n-text>
            </div>
            <n-divider class="card-divider" />

            <div class="row">
              <div class="row-label">
                <span class="row-title">节拍字数硬帽</span>
                <n-text depth="3" class="row-hint">
                  开启时由指挥器计算每节拍 <span class="mono">hard_cap</span>；超出时可截断。关闭后不再施加硬帽与截断安全网。
                </n-text>
              </div>
              <n-switch
                :value="beatHardCap"
                :loading="patching === 'beat_hard_cap_enabled'"
                size="large"
                @update:value="(v: boolean) => onBoolPref('beat_hard_cap_enabled', v)"
              >
                <template #checked>已启用</template>
                <template #unchecked>已关闭</template>
              </n-switch>
            </div>

            <n-divider class="inner-divider" />

            <div class="row" :class="{ 'row-muted': !beatHardCap }">
              <div class="row-label">
                <span class="row-title">智能截断</span>
                <n-text depth="3" class="row-hint">
                  阶段模式下默认关闭；打开「阶段」开关时会一并关闭。若需句界友好截断，可再手动打开（需先启用硬帽）。
                </n-text>
              </div>
              <n-tooltip :disabled="beatHardCap" placement="left">
                <template #trigger>
                  <span class="switch-wrap">
                    <n-switch
                      :value="smartTruncate"
                      :disabled="!beatHardCap"
                      :loading="patching === 'smart_truncate_enabled'"
                      size="large"
                      @update:value="(v: boolean) => onBoolPref('smart_truncate_enabled', v)"
                    >
                      <template #checked>智能</template>
                      <template #unchecked>硬截断</template>
                    </n-switch>
                  </span>
                </template>
                请先启用节拍硬帽，智能截断才有意义。
              </n-tooltip>
            </div>
          </n-card>

          <!-- 章末审阅闸门（paused_for_review） -->
          <n-card size="small" :bordered="true" class="prefs-card">
            <div class="card-head">
              <span class="card-title">章末审阅闸门</span>
              <n-text depth="3" class="card-caption">
                与小说家「一章一停 / 硬伤打回」对齐。开启后全托管在每章审计结束进入<n-text strong>待审阅</n-text>，须在工作台点「恢复」才继续；开启「全自动审阅跳过」的书目仍会跳过。
              </n-text>
            </div>
            <n-divider class="card-divider" />

            <div class="row">
              <div class="row-label">
                <span class="row-title">每章通过后暂停</span>
                <n-text depth="3" class="row-hint">
                  无条件每章停顿，便于人工手改再审下一章。
                </n-text>
              </div>
              <n-switch
                :value="pauseAfterEachAudit"
                :loading="patching === 'pause_after_each_chapter_audit'"
                size="large"
                @update:value="(v: boolean) => onAuditGatePref('pause_after_each_chapter_audit', v)"
              >
                <template #checked>已启用</template>
                <template #unchecked>已关闭</template>
              </n-switch>
            </div>

            <n-divider class="inner-divider" />

            <div class="row">
              <div class="row-label">
                <span class="row-title">硬伤时暂停</span>
                <n-text depth="3" class="row-hint">
                  章后叙事同步失败（<span class="mono">narrative_sync_ok=false</span>），或文风在有限次改写后仍低于阈值告警时，停机待人而非直接开写下一章。
                </n-text>
              </div>
              <n-switch
                :value="auditPauseOnHardFail"
                :loading="patching === 'audit_pause_on_hard_fail'"
                size="large"
                @update:value="(v: boolean) => onAuditGatePref('audit_pause_on_hard_fail', v)"
              >
                <template #checked>已启用</template>
                <template #unchecked>已关闭</template>
              </n-switch>
            </div>

            <n-divider class="inner-divider" />

            <div class="row">
              <div class="row-label">
                <span class="row-title">Anti-AI「严重」时暂停</span>
                <n-text depth="3" class="row-hint">
                  仅当本章 Anti-AI 综合判定为「严重」时进入待审阅（「中等」仍只告警）。
                </n-text>
              </div>
              <n-switch
                :value="auditPauseOnAntiAiSevere"
                :loading="patching === 'audit_pause_on_anti_ai_severe'"
                size="large"
                @update:value="(v: boolean) => onAuditGatePref('audit_pause_on_anti_ai_severe', v)"
              >
                <template #checked>已启用</template>
                <template #unchecked>已关闭</template>
              </n-switch>
            </div>
          </n-card>

          <!-- 指挥器相位 -->
          <n-card size="small" :bordered="true" class="prefs-card prefs-card-advanced">
            <div class="card-head">
              <span class="card-title">指挥器相位</span>
              <n-text depth="3" class="card-caption">
                按本章已消耗字数占预算的比例切换铺陈 / 收束 / 着陆提示。留空则使用内置
                {{ (DEFAULT_CONVERGE * 100).toFixed(0) }}% / {{ (DEFAULT_LAND * 100).toFixed(0) }}%。
              </n-text>
            </div>
            <n-divider class="card-divider" />

            <n-grid cols="1 520:2" :x-gap="20" :y-gap="16">
              <n-gi>
                <div class="field-block">
                  <span class="field-label">铺陈 → 收束</span>
                  <n-text depth="3" class="field-sublabel">消耗占比 &lt; 该值时保持铺陈</n-text>
                  <n-input-number
                    v-model:value="convergeInput"
                    class="field-input"
                    :min="0.01"
                    :max="0.99"
                    :step="0.01"
                    :precision="2"
                    clearable
                    placeholder="例如 0.75"
                  />
                </div>
              </n-gi>
              <n-gi>
                <div class="field-block">
                  <span class="field-label">收束 → 着陆</span>
                  <n-text depth="3" class="field-sublabel">达到该占比后进入着陆提示</n-text>
                  <n-input-number
                    v-model:value="landInput"
                    class="field-input"
                    :min="0.02"
                    :max="1"
                    :step="0.01"
                    :precision="2"
                    clearable
                    placeholder="例如 0.92"
                  />
                </div>
              </n-gi>
            </n-grid>

            <n-text v-if="conductorError" type="warning" class="conductor-error">
              {{ conductorError }}
            </n-text>

            <div class="actions">
              <n-button quaternary size="small" :loading="savingConductor" @click="resetConductorDefaults">
                恢复内置默认
              </n-button>
              <n-button type="primary" size="small" :loading="savingConductor" @click="saveConductorThresholds">
                保存相位阈值
              </n-button>
            </div>
          </n-card>
        </div>
      </n-spin>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { novelApi, type GenerationPrefsDTO } from '@/api/novel'
import { WORKBENCH_GENERATION_PREFS_UPDATED_EVENT } from '@/workbench/deskEvents'

const route = useRoute()
const message = useMessage()

const DEFAULT_CONVERGE = 0.75
const DEFAULT_LAND = 0.92

const novelSlug = computed(() => String(route.params.slug ?? '').trim())

const loading = ref(false)
const novelTitle = ref('')
const patching = ref<string | null>(null)
const savingConductor = ref(false)

const smartTruncate = ref(false)
const beatHardCap = ref(false)

const pauseAfterEachAudit = ref(false)
const auditPauseOnHardFail = ref(false)
const auditPauseOnAntiAiSevere = ref(false)

const convergeInput = ref<number | null>(null)
const landInput = ref<number | null>(null)

const conductorError = ref('')

function applyPrefs(p?: GenerationPrefsDTO | null) {
  const p2 = p ?? {}
  smartTruncate.value = Object.prototype.hasOwnProperty.call(p2, 'smart_truncate_enabled')
    ? Boolean(p2.smart_truncate_enabled)
    : false
  beatHardCap.value = Object.prototype.hasOwnProperty.call(p2, 'beat_hard_cap_enabled')
    ? Boolean(p2.beat_hard_cap_enabled)
    : false

  pauseAfterEachAudit.value = Boolean(p2.pause_after_each_chapter_audit)
  auditPauseOnHardFail.value = Boolean(p2.audit_pause_on_hard_fail)
  auditPauseOnAntiAiSevere.value = Boolean(p2.audit_pause_on_anti_ai_severe)

  convergeInput.value =
    typeof p2.conductor_converge_threshold === 'number' && Number.isFinite(p2.conductor_converge_threshold)
      ? p2.conductor_converge_threshold
      : null
  landInput.value =
    typeof p2.conductor_land_threshold === 'number' && Number.isFinite(p2.conductor_land_threshold)
      ? p2.conductor_land_threshold
      : null
  conductorError.value = ''
}

function validateConductorInputs(): boolean {
  const cv = convergeInput.value
  const lv = landInput.value
  if (cv != null && !(cv > 0 && cv < 1)) {
    conductorError.value = '「铺陈 → 收束」须在 0 与 1 之间（不含端点）。'
    return false
  }
  if (lv != null && !(lv > 0 && lv <= 1)) {
    conductorError.value = '「收束 → 着陆」须在 0 与 1 之间（可等于 1）。'
    return false
  }
  if (cv != null && lv != null && cv >= lv) {
    conductorError.value = '「铺陈 → 收束」须小于「收束 → 着陆」。'
    return false
  }
  const effLand = lv ?? DEFAULT_LAND
  const effConv = cv ?? DEFAULT_CONVERGE
  if (cv != null && cv >= effLand) {
    conductorError.value = `「铺陈 → 收束」须小于实际着陆阈值（当前另一项为空，内置着陆为 ${effLand}）。`
    return false
  }
  if (lv != null && effConv >= lv) {
    conductorError.value = `「收束 → 着陆」须大于实际铺陈阈值（当前另一项为空，内置铺陈切换点为 ${effConv}）。`
    return false
  }
  conductorError.value = ''
  return true
}

watch([convergeInput, landInput], () => {
  if (conductorError.value) validateConductorInputs()
})

async function loadNovel() {
  const slug = novelSlug.value
  if (!slug) return
  loading.value = true
  try {
    const n = await novelApi.getNovel(slug)
    novelTitle.value = n.title || slug
    applyPrefs(n.generation_prefs)
  } catch (e) {
    message.error(e instanceof Error ? e.message : '加载书目失败')
  } finally {
    loading.value = false
  }
}

async function mergePrefs(patch: Partial<GenerationPrefsDTO>) {
  const slug = novelSlug.value
  if (!slug) return
  const n = await novelApi.updateNovel(slug, { generation_prefs: patch })
  applyPrefs(n.generation_prefs)
  window.dispatchEvent(new CustomEvent(WORKBENCH_GENERATION_PREFS_UPDATED_EVENT))
}

async function onAuditGatePref(
  key:
    | 'pause_after_each_chapter_audit'
    | 'audit_pause_on_hard_fail'
    | 'audit_pause_on_anti_ai_severe',
  value: boolean
) {
  const slug = novelSlug.value
  if (!slug) return
  patching.value = key
  try {
    await mergePrefs({ [key]: value })
    message.success('已保存')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    patching.value = null
  }
}

async function onBoolPref(
  key: 'smart_truncate_enabled' | 'beat_hard_cap_enabled',
  value: boolean
) {
  const slug = novelSlug.value
  if (!slug) return
  patching.value = key
  try {
    await mergePrefs({ [key]: value })
    message.success('已保存')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    patching.value = null
  }
}

async function saveConductorThresholds() {
  if (!validateConductorInputs()) return
  const slug = novelSlug.value
  if (!slug) return
  savingConductor.value = true
  try {
    await mergePrefs({
      conductor_converge_threshold: convergeInput.value,
      conductor_land_threshold: landInput.value,
    })
    message.success('相位阈值已保存')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    savingConductor.value = false
  }
}

async function resetConductorDefaults() {
  const slug = novelSlug.value
  if (!slug) return
  savingConductor.value = true
  try {
    await mergePrefs({
      conductor_converge_threshold: null,
      conductor_land_threshold: null,
    })
    convergeInput.value = null
    landInput.value = null
    conductorError.value = ''
    message.success('已恢复内置默认')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    savingConductor.value = false
  }
}

watch(
  novelSlug,
  (s) => {
    if (s) void loadNovel()
    else {
      novelTitle.value = ''
      applyPrefs(null)
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.writing-prefs {
  max-width: 720px;
}

.prefs-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.prefs-title {
  margin: 0 0 0.375rem;
  font-size: var(--font-size-xl);
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--app-text-primary, #0f172a);
}

.prefs-sub {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.55;
  color: var(--app-text-secondary, #64748b);
  max-width: 520px;
}

.book-tag {
  flex-shrink: 0;
  font-weight: 500;
  border-radius: 999px;
  background: var(--app-surface-muted, rgba(148, 163, 184, 0.18)) !important;
}

.prefs-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.prefs-card {
  border-radius: 12px;
  overflow: hidden;
}

.prefs-card :deep(.n-card__content) {
  padding: 18px 20px 20px;
}

.prefs-card-advanced :deep(.n-card__content) {
  padding-bottom: 16px;
}

.card-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-title {
  font-size: calc(var(--font-size-base) * 1.06);
  font-weight: 600;
  color: var(--app-text-primary, #0f172a);
}

.card-caption {
  font-size: var(--font-size-xs);
  line-height: 1.5;
  max-width: 640px;
}

.card-divider {
  margin: 14px 0 16px;
}

.inner-divider {
  margin: 18px 0;
}

.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.row-valign {
  align-items: center;
}

.row-label {
  flex: 1;
  min-width: 0;
}

.row-title {
  display: block;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--app-text-primary, #1e293b);
  margin-bottom: 0.25rem;
}

.row-hint {
  font-size: var(--font-size-xs);
  line-height: 1.55;
  display: block;
  max-width: 460px;
}

.row-muted {
  opacity: 0.55;
}

.row-title.solo-title {
  margin-bottom: 0;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--app-text-primary, #1e293b);
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--app-text-primary, #334155);
}

.field-sublabel {
  font-size: calc(var(--font-size-xs) * 0.92);
  line-height: 1.45;
  margin-bottom: 0.25rem;
}

.field-input {
  width: 100%;
  max-width: 280px;
}

.conductor-error {
  display: block;
  margin-top: 0.75rem;
  font-size: var(--font-size-xs);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
  padding-top: 4px;
}

.empty-state {
  padding: 28px 8px 8px;
  border-radius: 12px;
  border: 1px dashed var(--app-border-soft, rgba(148, 163, 184, 0.45));
  background: var(--app-surface-subtle, rgba(248, 250, 252, 0.6));
}

.empty-title {
  font-size: calc(var(--font-size-base) * 1.06);
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--app-text-primary, #0f172a);
}

.empty-desc {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--app-text-secondary, #64748b);
}

.mono {
  font-size: var(--font-size-xs);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--app-surface-muted, rgba(148, 163, 184, 0.15));
}
</style>
