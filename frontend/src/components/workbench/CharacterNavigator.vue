<template>
  <div class="cn">
    <div class="cn-header">
      <span class="cn-header-title">角色导航</span>
      <span v-if="characters.length > 0" class="cn-header-count">{{ characters.length }}</span>
    </div>

    <n-spin :show="loading" class="cn-spin" size="small">
      <div v-if="characters.length > 0" class="cn-list">
        <div
          v-for="char in characters"
          :key="char.id"
          class="cn-item"
          :class="{ 'cn-item--active': selectedCharacterId === char.id }"
          @click="selectCharacter(char.id)"
        >
          <div class="cn-avatar" :style="{ background: getRoleColor(char.role ?? '') }">
            {{ (char.name ?? '').slice(0, 1) || '?' }}
          </div>
          <div class="cn-info">
            <div class="cn-name-row">
              <span class="cn-name">{{ char.name }}</span>
              <span
                v-if="getStateDotClass(char.mental_state ?? '')"
                class="cn-dot"
                :class="getStateDotClass(char.mental_state ?? '')"
              />
            </div>
            <span class="cn-role-tag" :class="`cn-role-tag--${getRoleCssKey(char.role ?? '')}`">
              {{ getRoleLabel(char.role ?? '') }}
            </span>
          </div>
        </div>
      </div>

      <n-empty
        v-else-if="!loading"
        description="暂无角色"
        size="small"
        style="margin-top: 24px; padding: 0 12px"
      >
        <template #extra>
          <n-button size="small" @click="goToWorldbuilding">
            前往世界观
          </n-button>
        </template>
      </n-empty>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'
import { WORKBENCH_OPEN_SETTINGS_PANEL_EVENT } from '@/workbench/deskEvents'
import {
  classifyCharacterMentalState,
  getCharacterRoleColor,
  getCharacterRoleCssKey,
  getCharacterRoleLabel,
} from '@/domain/character'

interface Props {
  slug: string
  selectedCharacterId: string | null
}

const props = defineProps<Props>()
const emit  = defineEmits<{ 'select-character': [characterId: string | null] }>()

const message    = useMessage()
const loading    = ref(false)
const characters = ref<CharacterDTO[]>([])

function getRoleColor(role: string): string {
  return getCharacterRoleColor(role, 'var(--app-border)')
}

const getRoleCssKey = getCharacterRoleCssKey

const getRoleLabel = getCharacterRoleLabel

// ── Mental state dot ──────────────────────────────────────────────
function getStateDotClass(mental: string): string {
  const severity = classifyCharacterMentalState(mental)
  if (severity === 'normal') return ''
  if (severity === 'danger') return 'cn-dot--danger'
  return 'cn-dot--warning'
}

// ── Selection ─────────────────────────────────────────────────────
function selectCharacter(id: string | null) {
  emit('select-character', id)
}

function goToWorldbuilding() {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'worldbuilding' } }),
  )
}

// ── Data loading ──────────────────────────────────────────────────
async function loadCharacters() {
  if (!props.slug) return
  loading.value = true
  try {
    const bible = await bibleApi.getBible(props.slug)
    characters.value = bible.characters ?? []
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '加载角色失败')
    characters.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => void loadCharacters(), { immediate: true })
onMounted(() => { void loadCharacters() })
useWorkbenchDeskTickReload(() => void loadCharacters())

defineExpose({ loadCharacters })
</script>

<style scoped>
.cn {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--plotpilot-split-border);
}

/* ── Header ──────────────────────────────────────────────────────── */

.cn-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 14px;
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.cn-header-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.cn-header-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
  background: var(--app-border);
  color: var(--app-text-muted);
  line-height: 1;
}

/* ── Spin ────────────────────────────────────────────────────────── */

.cn-spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.cn-spin :deep(.n-spin-content) {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── List ────────────────────────────────────────────────────────── */

.cn-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--app-border) transparent;
}

.cn-list::-webkit-scrollbar       { width: 4px; }
.cn-list::-webkit-scrollbar-track { background: transparent; }
.cn-list::-webkit-scrollbar-thumb { background: var(--app-border); border-radius: 2px; }

/* ── Item ────────────────────────────────────────────────────────── */

.cn-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.cn-item:hover {
  border-color: var(--color-brand-border, rgba(37,99,235,0.3));
  background: var(--color-brand-light, rgba(37,99,235,0.03));
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

.cn-item--active {
  border-color: var(--color-brand, #2563eb) !important;
  border-left-width: 3px;
  background: var(--color-brand-light, rgba(37,99,235,0.05)) !important;
  padding-left: 8px; /* compensate for thicker left border */
}

/* ── Avatar ──────────────────────────────────────────────────────── */

.cn-avatar {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  line-height: 1;
  user-select: none;
  text-shadow: 0 1px 2px rgba(0,0,0,0.2);
  letter-spacing: 0;
}

/* ── Info ────────────────────────────────────────────────────────── */

.cn-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.cn-name-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.cn-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.25;
}

/* ── Mental state dot ────────────────────────────────────────────── */

.cn-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.cn-dot--danger  { background: var(--color-danger,  #ef4444); }
.cn-dot--warning { background: var(--color-warning, #f59e0b); }

/* ── Role tag ────────────────────────────────────────────────────── */

.cn-role-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.03em;
  align-self: flex-start;
}

.cn-role-tag--protagonist {
  background: var(--color-brand-light, rgba(37,99,235,0.09));
  color: var(--color-brand, #2563eb);
}

.cn-role-tag--supporting {
  background: var(--color-warning-dim, rgba(245,158,11,0.09));
  color: var(--color-warning, #f59e0b);
}

.cn-role-tag--minor {
  background: var(--app-border);
  color: var(--app-text-muted);
}
</style>
