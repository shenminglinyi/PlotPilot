<template>
  <article
    class="mod-card"
    :class="{ 'is-installed': installed }"
    role="button"
    tabindex="0"
    :aria-label="`${pack.name}，${pack.summary}`"
    @click="$emit('select', pack)"
    @keydown.enter.prevent="$emit('select', pack)"
  >
    <div class="mod-card-head">
      <div class="mod-glyph" aria-hidden="true">{{ pack.glyph }}</div>

      <div class="mod-title-group">
        <h4 class="mod-name" :title="pack.name">{{ pack.name }}</h4>
        <div class="mod-author-row">
          <span class="mod-author">{{ pack.author }}</span>
          <span class="mod-trust" :class="`trust-${pack.trustLevel}`">
            <svg
              v-if="pack.trustLevel === 'official' || pack.trustLevel === 'cloud-verified'"
              viewBox="0 0 16 16"
              fill="none"
              class="trust-icon"
              aria-hidden="true"
            >
              <path
                d="M13.2 4.6 6.6 11.2 3.2 7.8"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span v-else class="trust-dot" aria-hidden="true" />
            <span>{{ trustLabel }}</span>
          </span>
        </div>
      </div>

      <button
        type="button"
        class="mod-cta"
        :class="{ 'is-installed': installed, 'is-busy': busy }"
        :disabled="busy"
        @click.stop="onActionClick"
      >
        <template v-if="busy">处理中…</template>
        <template v-else-if="installed">
          <svg viewBox="0 0 16 16" fill="none" class="cta-icon" aria-hidden="true">
            <path
              d="M13.2 4.6 6.6 11.2 3.2 7.8"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span>已启用</span>
        </template>
        <template v-else>
          <svg viewBox="0 0 16 16" fill="none" class="cta-icon" aria-hidden="true">
            <path
              d="M8 2.8v7.6M4.8 7.6 8 10.8l3.2-3.2M3.2 13.2h9.6"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span>安装</span>
        </template>
      </button>
    </div>

    <p class="mod-summary">{{ pack.summary }}</p>

    <footer class="mod-meta">
      <span class="meta-item meta-role">
        <svg viewBox="0 0 16 16" fill="none" class="meta-icon" aria-hidden="true">
          <path
            d="M5.5 2.5v3M10.5 2.5v3M3.5 5.5h9v3a4.5 4.5 0 0 1-9 0v-3ZM8 13v1.5"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        {{ pack.roleLabel }}
      </span>
      <span class="meta-item numeric">{{ pack.usageLabel }}</span>
      <span class="meta-item numeric">{{ pack.version }}</span>
      <span v-if="pack.replacesBuiltin" class="scope-pill">
        替代内置 · {{ pack.overrides.length }}
      </span>
      <span v-else class="scope-pill is-addon">独立扩展</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NarrativeModPack } from '@/domain/modPack/types'

const props = defineProps<{
  pack: NarrativeModPack
  installed: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', pack: NarrativeModPack): void
  (e: 'install', pack: NarrativeModPack): void
  (e: 'manage', pack: NarrativeModPack): void
}>()

const trustLabel = computed(() => {
  switch (props.pack.trustLevel) {
    case 'official':
      return '墨枢精选'
    case 'cloud-verified':
      return '云端书元'
    case 'local':
      return '本地自制'
    default:
      return '未审核'
  }
})

function onActionClick(): void {
  if (props.installed) {
    emit('manage', props.pack)
  } else {
    emit('install', props.pack)
  }
}
</script>

<style scoped>
.mod-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 12px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
  text-align: left;
  outline: none;
}

.mod-card:hover,
.mod-card:focus-visible {
  border-color: var(--app-border-strong);
}

.mod-card.is-installed {
  border-color: color-mix(in srgb, var(--color-brand) 32%, var(--app-border));
}

.mod-card-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.mod-glyph {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-primary);
  font-size: 16px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  user-select: none;
}

.mod-title-group {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mod-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mod-author-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12.5px;
  line-height: 1.3;
}

.mod-author {
  color: var(--app-text-muted);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mod-trust {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
}

.mod-trust.trust-official,
.mod-trust.trust-cloud-verified {
  background: var(--color-success-light);
  color: var(--color-success);
}

.mod-trust.trust-community-unreviewed {
  background: var(--color-warning-light);
  color: var(--color-warning);
}

.mod-trust.trust-local {
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
  border: 1px solid var(--app-border);
}

.trust-icon {
  width: 12px;
  height: 12px;
}

.trust-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.mod-cta {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface);
  color: var(--app-text-primary);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background-color 0.15s ease;
  white-space: nowrap;
}

.mod-cta:hover:not(:disabled) {
  border-color: var(--color-brand);
  color: var(--color-brand);
  background: var(--color-brand-light);
}

.mod-cta.is-installed {
  border-color: transparent;
  background: transparent;
  color: var(--color-success);
  padding-right: 4px;
}

.mod-cta.is-installed:hover:not(:disabled) {
  background: var(--color-success-light);
  border-color: transparent;
  color: var(--color-success);
}

.mod-cta:disabled {
  opacity: 0.6;
  cursor: wait;
}

.cta-icon {
  width: 13px;
  height: 13px;
}

.mod-summary {
  margin: 0;
  font-size: 14px;
  line-height: 1.58;
  color: var(--app-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 44px;
  max-width: 58ch;
}

.mod-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
  padding-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-role {
  color: var(--color-brand);
  font-weight: 500;
}

.meta-icon {
  width: 13px;
  height: 13px;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.scope-pill {
  margin-left: auto;
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-secondary);
  font-size: 11.5px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.scope-pill.is-addon {
  color: var(--app-text-muted);
}
</style>
