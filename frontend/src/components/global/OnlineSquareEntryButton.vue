<template>
  <!-- 线上提示词广场入口（应用内路由，界面自渲染）：点击进入 /square，
       数据由本地内核 /cloud/* 代理拉取。与本地 PromptPlaza（提示词版本管理）
       分工：这里连的是线上社区广场（官方书元/社区共享/热榜）。 -->
  <button
    type="button"
    class="online-square-btn"
    :class="{ 'is-opening': opening }"
    :disabled="opening"
    @click="openSquare"
  >
    <span class="online-square-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M12 3v10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M8.5 7.5 12 4l3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="6" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8"/>
        <circle cx="18" cy="17.5" r="2.4" stroke="currentColor" stroke-width="1.8"/>
        <path d="M8.4 17.5h7.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
    </span>
    <span class="online-square-title">线上提示词广场</span>
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
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-primary);
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.online-square-btn:hover {
  border-color: var(--color-plaza, #059669);
  transform: translateY(-1px);
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
  color: var(--color-plaza, #059669);
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
}

.online-square-hint {
  flex: none;
  font-size: 11px;
  color: var(--app-text-muted);
}
</style>
