<template>
  <header class="ap-shell-nav" role="navigation" aria-label="托管工作区分页">
    <div class="ap-shell-nav__brand">
      <span class="ap-shell-nav__mark" aria-hidden="true" />
      <div class="ap-shell-nav__titles">
        <span class="ap-shell-nav__eyebrow">Autopilot</span>
        <span class="ap-shell-nav__active-label">{{ activeMeta.label }}</span>
      </div>
    </div>
    <div
      class="ap-shell-nav__segments"
      role="tablist"
      aria-label="切换托管视图"
    >
      <button
        v-for="tab in AUTOPILOT_WORKSPACE_TABS"
        :key="tab.id"
        type="button"
        role="tab"
        class="ap-shell-nav__segment"
        :class="{ 'is-active': workspace.activeTab === tab.id }"
        :aria-selected="workspace.activeTab === tab.id"
        @click="workspace.setTab(tab.id)"
      >
        <span class="ap-shell-nav__segment-label">{{ tab.short }}</span>
        <span class="ap-shell-nav__segment-hint">{{ tab.description }}</span>
      </button>
    </div>
    <p class="ap-shell-nav__desc">{{ activeMeta.description }}</p>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AUTOPILOT_WORKSPACE_TABS,
  useAutopilotWorkspaceStore,
} from '@/stores/autopilotWorkspaceStore'

const workspace = useAutopilotWorkspaceStore()

const activeMeta = computed(() => {
  return (
    AUTOPILOT_WORKSPACE_TABS.find(t => t.id === workspace.activeTab)
    ?? AUTOPILOT_WORKSPACE_TABS[0]
  )
})
</script>

<style scoped>
.ap-shell-nav {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: minmax(140px, auto) 1fr;
  grid-template-rows: auto auto;
  gap: 10px 20px;
  padding: 14px 18px 12px;
  border-bottom: 1px solid var(--app-border);
  background: linear-gradient(
    165deg,
    color-mix(in srgb, var(--color-primary, #2563eb) 6%, var(--app-surface)) 0%,
    var(--app-surface) 48%
  );
  box-shadow: var(--app-shadow-sm);
}

.ap-shell-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  grid-row: 1 / 3;
  align-self: center;
}

.ap-shell-nav__mark {
  width: 10px;
  height: 36px;
  border-radius: 999px;
  background: linear-gradient(
    180deg,
    var(--color-primary, #2563eb),
    color-mix(in srgb, var(--color-success, #16a34a) 70%, var(--color-primary, #2563eb))
  );
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary, #2563eb) 12%, transparent);
}

.ap-shell-nav__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ap-shell-nav__eyebrow {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.ap-shell-nav__active-label {
  font-size: 15px;
  font-weight: 650;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.ap-shell-nav__segments {
  display: flex;
  gap: 6px;
  padding: 4px;
  border-radius: var(--app-radius-lg);
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  grid-column: 2;
  grid-row: 1;
  justify-self: end;
  max-width: 100%;
  overflow-x: auto;
}

.ap-shell-nav__segment {
  flex: 1 1 0;
  min-width: 108px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 14px;
  border: none;
  border-radius: calc(var(--app-radius-lg) - 4px);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition:
    background var(--app-transition),
    box-shadow var(--app-transition),
    color var(--app-transition);
  color: var(--app-text-secondary);
}

.ap-shell-nav__segment:hover:not(.is-active) {
  background: color-mix(in srgb, var(--app-text-primary) 4%, transparent);
  color: var(--app-text-primary);
}

.ap-shell-nav__segment.is-active {
  background: var(--app-surface);
  box-shadow: var(--app-shadow-sm);
  color: var(--app-text-primary);
}

.ap-shell-nav__segment-label {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
}

.ap-shell-nav__segment-hint {
  font-size: 10px;
  line-height: 1.3;
  color: var(--app-text-muted);
  white-space: nowrap;
}

.ap-shell-nav__segment.is-active .ap-shell-nav__segment-hint {
  color: color-mix(in srgb, var(--color-primary, #2563eb) 55%, var(--app-text-muted));
}

.ap-shell-nav__desc {
  margin: 0;
  grid-column: 2;
  grid-row: 2;
  justify-self: end;
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: right;
  max-width: 520px;
}

@media (max-width: 900px) {
  .ap-shell-nav {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto;
  }

  .ap-shell-nav__brand {
    grid-row: 1;
  }

  .ap-shell-nav__segments {
    grid-column: 1;
    grid-row: 2;
    justify-self: stretch;
  }

  .ap-shell-nav__desc {
    grid-column: 1;
    grid-row: 3;
    justify-self: start;
    text-align: left;
  }

  .ap-shell-nav__segment {
    min-width: 88px;
  }

  .ap-shell-nav__segment-hint {
    display: none;
  }
}
</style>
