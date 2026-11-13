<template>
  <button
    type="button"
    class="online-square-btn"
    :class="{ 'is-opening': opening }"
    :disabled="opening"
    @click="openSquare"
  >
    <span class="online-square-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 3v10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        <path
          d="M8.5 7.5 12 4l3.5 3.5"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle cx="6" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8" />
        <circle cx="18" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8" />
        <path d="M8.4 17.5h7.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>
    </span>
    <span class="online-square-title">线上模组广场</span>
    <span class="online-square-hint" aria-hidden="true">↗</span>
  </button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const opening = ref(false)

function openSquare(): void {
  opening.value = true
  void router.push('/square').finally(() => {
    opening.value = false
  })
}
</script>

<style scoped>
.online-square-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  box-sizing: border-box;
  min-height: 38px;
  padding: 0 12px;
  border-radius: 9px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-primary);
  cursor: pointer;
  transition: border-color 0.16s ease, color 0.16s ease;
}

.online-square-btn:hover:not(:disabled) {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.online-square-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.online-square-icon {
  flex: none;
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-brand);
}

.online-square-icon svg {
  width: 16px;
  height: 16px;
}

.online-square-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  text-align: left;
}

.online-square-hint {
  flex: none;
  font-size: 11px;
  color: var(--app-text-muted);
}
</style>
