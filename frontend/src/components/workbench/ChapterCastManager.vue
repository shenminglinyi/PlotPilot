<template>
  <div class="ccm">
    <!-- Header -->
    <div class="ccm-header">
      <span class="ccm-title">选角台</span>
      <span v-if="chapterNumber" class="ccm-chapter-tag">第 {{ chapterNumber }} 章</span>
      <div class="ccm-actions">
        <n-button
          size="tiny"
          secondary
          :loading="scheduling"
          @click="runSchedule"
        >
          智能排班
        </n-button>
        <n-button
          v-if="suggestions.length > 0"
          size="tiny"
          type="primary"
          :loading="applying"
          @click="applyAll"
        >
          采纳全部
        </n-button>
      </div>
    </div>

    <!-- New character hints -->
    <div v-if="newCharHints.length > 0" class="ccm-hints">
      <span class="ccm-hints-label">大纲新角色：</span>
      <n-tag
        v-for="hint in newCharHints"
        :key="hint"
        size="tiny"
        round
        class="ccm-hint-tag"
      >{{ hint }}</n-tag>
    </div>

    <!-- Suggestions list -->
    <div v-if="suggestions.length > 0" class="ccm-section">
      <div class="ccm-section-label">建议出场</div>
      <div class="ccm-list">
        <div
          v-for="item in suggestions"
          :key="item.character_id"
          class="ccm-item"
          :class="`ccm-item--${item.importance}`"
        >
          <div class="ccm-avatar">{{ item.name.slice(0, 1) }}</div>
          <div class="ccm-info">
            <span class="ccm-name">{{ item.name }}</span>
            <span class="ccm-imp-tag" :class="`ccm-imp-tag--${item.importance}`">
              {{ IMPORTANCE_LABELS[item.importance] }}
            </span>
          </div>
          <n-button
            size="tiny"
            secondary
            style="flex-shrink:0"
            :loading="applying"
            @click="applySingle(item)"
          >
            采纳
          </n-button>
        </div>
      </div>
    </div>

    <!-- Empty / idle state -->
    <n-empty
      v-else-if="!scheduling"
      size="small"
      description="点击「智能排班」生成本章选角建议"
      style="margin-top: 32px; padding: 0 16px"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { castApi, type ScheduledCharacterItem } from '@/api/cast'

interface Props {
  slug: string
  chapterNumber?: number | null
  outline?: string
}

const props  = withDefaults(defineProps<Props>(), { chapterNumber: null, outline: '' })
const message = useMessage()

const scheduling  = ref(false)
const applying    = ref(false)
const suggestions = ref<ScheduledCharacterItem[]>([])
const newCharHints = ref<string[]>([])

const IMPORTANCE_LABELS: Record<string, string> = {
  major:  '主要',
  normal: '普通',
  minor:  '次要',
}

async function runSchedule() {
  if (!props.slug) return
  scheduling.value = true
  suggestions.value = []
  newCharHints.value = []
  try {
    const res = await castApi.analyzeOutline(
      props.slug,
      props.chapterNumber ?? 1,
      props.outline ?? '',
    )
    suggestions.value    = res.cast
    newCharHints.value   = res.new_character_hints
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '智能排班失败')
  } finally {
    scheduling.value = false
  }
}

async function applyAll() {
  if (!props.slug || suggestions.value.length === 0) return
  applying.value = true
  try {
    await castApi.scheduleAndPersist(props.slug, {
      chapter_number: props.chapterNumber ?? 1,
      outline: props.outline ?? '',
      mode: 'apply',
    })
    message.success(`已写入 ${suggestions.value.length} 个角色到选角表`)
    suggestions.value = []
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '写入失败')
  } finally {
    applying.value = false
  }
}

async function applySingle(item: ScheduledCharacterItem) {
  if (!props.slug) return
  applying.value = true
  try {
    await castApi.scheduleAndPersist(props.slug, {
      chapter_number: props.chapterNumber ?? 1,
      outline: '',
      mode: 'apply',
    })
    message.success(`已采纳 ${item.name}`)
    suggestions.value = suggestions.value.filter(s => s.character_id !== item.character_id)
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '采纳失败')
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.ccm {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

/* ── Header ───────────────────────────────────────────────────────── */

.ccm-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.ccm-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.ccm-chapter-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-brand-light, rgba(37,99,235,0.08));
  color: var(--color-brand, #2563eb);
  font-weight: 500;
}

.ccm-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}

/* ── Hints ────────────────────────────────────────────────────────── */

.ccm-hints {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  background: var(--color-warning-dim, rgba(245,158,11,0.04));
}

.ccm-hints-label {
  font-size: 11px;
  color: var(--app-text-muted);
}

.ccm-hint-tag {
  font-size: 11px;
  background: var(--color-warning-dim, rgba(245,158,11,0.1));
  color: var(--color-warning, #f59e0b);
  border: none;
}

/* ── Section ──────────────────────────────────────────────────────── */

.ccm-section {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--app-border) transparent;
}

.ccm-section::-webkit-scrollbar       { width: 4px; }
.ccm-section::-webkit-scrollbar-track { background: transparent; }
.ccm-section::-webkit-scrollbar-thumb { background: var(--app-border); border-radius: 2px; }

.ccm-section-label {
  padding: 8px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.ccm-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 8px 8px;
}

/* ── Item ─────────────────────────────────────────────────────────── */

.ccm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-left-width: 3px;
}

.ccm-item--major  { border-left-color: var(--color-brand, #2563eb); }
.ccm-item--normal { border-left-color: var(--color-warning, #f59e0b); }
.ccm-item--minor  { border-left-color: var(--app-border); }

.ccm-avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--app-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--app-text-primary);
  user-select: none;
}

.ccm-item--major .ccm-avatar {
  background: var(--color-brand-light, rgba(37,99,235,0.1));
  color: var(--color-brand, #2563eb);
}

.ccm-item--normal .ccm-avatar {
  background: var(--color-warning-dim, rgba(245,158,11,0.1));
  color: var(--color-warning, #f59e0b);
}

.ccm-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ccm-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ccm-imp-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  align-self: flex-start;
  letter-spacing: 0.03em;
}

.ccm-imp-tag--major  {
  background: var(--color-brand-light, rgba(37,99,235,0.08));
  color: var(--color-brand, #2563eb);
}
.ccm-imp-tag--normal {
  background: var(--color-warning-dim, rgba(245,158,11,0.08));
  color: var(--color-warning, #f59e0b);
}
.ccm-imp-tag--minor  {
  background: var(--app-border);
  color: var(--app-text-muted);
}
</style>
