<template>
  <div class="ctx-panel">
    <header class="ctx-header">
      <h3 class="ctx-title">当前语境</h3>
      <n-button size="tiny" secondary :loading="loading" @click="reload">刷新</n-button>
    </header>

    <div class="ctx-body">
      <!-- 世界规则 -->
      <section class="ctx-section">
        <div class="section-label">世界规则</div>
        <n-spin :show="loadingWorld" size="small">
          <n-empty v-if="!loadingWorld && !hasWorldRules" description="未填写世界规则" size="small" />
          <div v-else class="rules-list">
            <div v-if="worldRules.power_system" class="rule-row">
              <span class="rule-key">力量体系</span>
              <span class="rule-val">{{ worldRules.power_system }}</span>
            </div>
            <div v-if="worldRules.physics_rules" class="rule-row">
              <span class="rule-key">物理规律</span>
              <span class="rule-val">{{ worldRules.physics_rules }}</span>
            </div>
            <div v-if="worldRules.magic_tech" class="rule-row">
              <span class="rule-key">魔法/科技</span>
              <span class="rule-val">{{ worldRules.magic_tech }}</span>
            </div>
          </div>
        </n-spin>
      </section>

      <!-- 人物心理 -->
      <section class="ctx-section">
        <div class="section-label">人物心理</div>
        <n-spin :show="loadingChars" size="small">
          <n-empty v-if="!loadingChars && characters.length === 0" description="暂无角色心理档案" size="small" />
          <div v-else class="char-list">
            <div v-for="c in characters" :key="c.name" class="char-row">
              <div class="char-name">{{ c.name }}</div>
              <div v-if="c.wound" class="char-wound">
                <span class="wound-label">伤</span>{{ c.wound }}
              </div>
              <div v-if="c.core_belief" class="char-belief">
                <span class="belief-label">信</span>{{ c.core_belief }}
              </div>
            </div>
          </div>
        </n-spin>
      </section>

      <!-- 本章到期伏笔 -->
      <section class="ctx-section">
        <div class="section-label">
          本章到期伏笔
          <n-badge
            v-if="dueForeshadows.length > 0"
            :value="dueForeshadows.length"
            type="error"
            style="margin-left: 6px"
          />
        </div>
        <n-spin :show="loadingFs" size="small">
          <n-empty
            v-if="!loadingFs && dueForeshadows.length === 0"
            description="本章无到期伏笔"
            size="small"
          />
          <div v-else class="fs-list">
            <div
              v-for="f in dueForeshadows"
              :key="f.id"
              class="fs-row"
              :class="`fs-row--${f.importance}`"
            >
              <span class="fs-importance">{{ importanceLabel(f.importance) }}</span>
              <span class="fs-question">{{ f.question }}</span>
              <span class="fs-chapter">埋于第{{ f.chapter }}章</span>
            </div>
          </div>
        </n-spin>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { worldbuildingApi } from '@/api/worldbuilding'
import { characterPsycheApi, type CharacterPsycheDTO } from '@/api/engineCore'
import { foreshadowApi, type ForeshadowEntry } from '@/api/foreshadow'

interface Props {
  slug: string
  currentChapter?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapter: null,
})

// ── world ──────────────────────────────────────────────────────
const loadingWorld = ref(false)
const worldRules = ref({ power_system: '', physics_rules: '', magic_tech: '' })
const hasWorldRules = computed(() =>
  !!(worldRules.value.power_system || worldRules.value.physics_rules || worldRules.value.magic_tech)
)

async function fetchWorld() {
  loadingWorld.value = true
  try {
    const wb = await worldbuildingApi.getWorldbuilding(props.slug)
    const cr = wb?.core_rules
    worldRules.value = {
      power_system: cr?.power_system ?? '',
      physics_rules: cr?.physics_rules ?? '',
      magic_tech: cr?.magic_tech ?? '',
    }
  } catch {
    /* silent */
  } finally {
    loadingWorld.value = false
  }
}

// ── characters ─────────────────────────────────────────────────
const loadingChars = ref(false)
const characters = ref<CharacterPsycheDTO[]>([])

async function fetchChars() {
  loadingChars.value = true
  try {
    const res = await characterPsycheApi.list(props.slug)
    characters.value = (res?.characters ?? []).slice(0, 5)
  } catch {
    /* silent */
  } finally {
    loadingChars.value = false
  }
}

// ── foreshadows ────────────────────────────────────────────────
const loadingFs = ref(false)
const allPendingFs = ref<ForeshadowEntry[]>([])

const dueForeshadows = computed(() => {
  const ch = props.currentChapter
  if (ch == null) return allPendingFs.value.filter(f => f.suggested_resolve_chapter != null).slice(0, 5)
  const window = ch + 2
  const importanceOrder: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 }
  return allPendingFs.value
    .filter(f => f.suggested_resolve_chapter != null && f.suggested_resolve_chapter <= window)
    .sort((a, b) => (importanceOrder[b.importance] ?? 2) - (importanceOrder[a.importance] ?? 2))
    .slice(0, 5)
})

async function fetchForeshadows() {
  loadingFs.value = true
  try {
    allPendingFs.value = await foreshadowApi.list(props.slug, 'pending')
  } catch {
    /* silent */
  } finally {
    loadingFs.value = false
  }
}

// ── loading ────────────────────────────────────────────────────
const loading = computed(() => loadingWorld.value || loadingChars.value || loadingFs.value)

function reload() {
  fetchWorld()
  fetchChars()
  fetchForeshadows()
}

onMounted(reload)
watch(() => props.slug, reload)

function importanceLabel(imp: string): string {
  const map: Record<string, string> = { critical: '关键', high: '重要', medium: '一般', low: '次要' }
  return map[imp] ?? imp
}
</script>

<style scoped>
.ctx-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.ctx-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
}

.ctx-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.ctx-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ctx-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  display: flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--app-text-muted);
  text-transform: uppercase;
}

/* ── world rules ── */
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.rule-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.rule-key {
  flex-shrink: 0;
  color: var(--app-text-muted);
  width: 56px;
}

.rule-val {
  color: var(--app-text-secondary);
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── characters ── */
.char-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.char-row {
  background: var(--app-surface);
  border: 1px solid var(--plotpilot-split-border);
  border-radius: 6px;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.char-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin-bottom: 2px;
}

.char-wound,
.char-belief {
  font-size: 11px;
  color: var(--app-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wound-label,
.belief-label {
  display: inline-block;
  width: 14px;
  height: 14px;
  line-height: 14px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  border-radius: 2px;
  margin-right: 4px;
  flex-shrink: 0;
}

.wound-label {
  background: rgba(var(--warning-color-rgb, 240, 160, 32), 0.15);
  color: var(--n-warning-color, #f0a020);
}

.belief-label {
  background: rgba(var(--info-color-rgb, 32, 128, 240), 0.12);
  color: var(--n-info-color, #2080f0);
}

/* ── foreshadows ── */
.fs-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fs-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  padding: 4px 6px;
  border-radius: 4px;
  background: var(--app-surface);
  border-left: 3px solid transparent;
}

.fs-row--critical { border-left-color: var(--n-error-color, #d03050); }
.fs-row--high     { border-left-color: var(--n-warning-color, #f0a020); }
.fs-row--medium   { border-left-color: var(--n-info-color, #2080f0); }
.fs-row--low      { border-left-color: var(--plotpilot-split-border); }

.fs-importance {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--app-text-muted);
  width: 26px;
}

.fs-question {
  flex: 1;
  color: var(--app-text-secondary);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.fs-chapter {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--app-text-muted);
}
</style>
