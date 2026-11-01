<template>
  <!-- 云端读取失败/需登录的统一占位块 -->
  <div class="square-state" :class="{ 'needs-login': needsLogin, 'is-suspended': suspended }">
    <span class="state-icon" aria-hidden="true">
      <svg v-if="suspended" viewBox="0 0 24 24" fill="none">
        <path d="M20 13.2A7.6 7.6 0 0 1 10.8 4 7.9 7.9 0 1 0 20 13.2Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
      </svg>
      <svg v-else-if="needsLogin" viewBox="0 0 24 24" fill="none">
        <rect x="5" y="10.5" width="14" height="9.5" rx="2.2" stroke="currentColor" stroke-width="1.8"/>
        <path d="M8.5 10.5V7.8a3.5 3.5 0 0 1 7 0v2.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <circle cx="12" cy="15.2" r="1.4" fill="currentColor"/>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none">
        <path d="M5 12.5a7 7 0 0 1 14 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M2.8 15a9.6 9.6 0 0 1 18.4 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <circle cx="12" cy="18.4" r="1.6" fill="currentColor"/>
      </svg>
    </span>
    <p class="state-title">{{ title }}</p>
    <p v-if="hint" class="state-hint">{{ hint }}</p>
    <div class="state-actions">
      <button v-if="suspended" type="button" class="state-btn ghost" @click="$emit('retry')">稍后再试</button>
      <template v-else>
        <button v-if="needsLogin" type="button" class="state-btn primary" @click="$emit('login')">登录云端</button>
        <button type="button" class="state-btn" @click="$emit('retry')">重试</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CloudSquareError } from '@/api/cloudSquare'

const props = defineProps<{
  error: CloudSquareError | null
  showLogin?: boolean
}>()

defineEmits<{
  (e: 'retry'): void
  (e: 'login'): void
}>()

/** 管理端斩断：整页只留一句「线上暂未提供服务，静待～」+ 轻刷新 */
const suspended = computed(() => props.error?.kind === 'suspended')

const needsLogin = computed(() => props.error?.kind === 'auth' && props.showLogin !== false)

const title = computed(() => {
  if (suspended.value) return props.error?.message || '线上暂未提供服务，静待～'
  if (props.error?.kind === 'auth') return needsLogin.value ? '登录后查看' : '需要登录云端'
  if (props.error?.kind === 'unreachable') return '云端暂不可达'
  if (props.error?.kind === 'upstream') return props.error.message || '云端暂无数据'
  return '加载失败'
})

const hint = computed(() => {
  if (suspended.value) return ''
  if (props.error?.kind === 'auth') {
    return '这部分内容需要登录 plotpilot.xyz 账号；凭证只存本地内核，浏览器零凭证。'
  }
  if (props.error?.kind === 'unreachable') {
    return '检查网络连接，或稍后重试。'
  }
  return props.error?.message || ''
})
</script>

<style scoped>
.square-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 56px 24px;
  text-align: center;
}

.square-state.is-suspended {
  padding: 110px 24px 90px;
}

.square-state.is-suspended .state-icon {
  color: var(--color-gold, #f59e0b);
  opacity: 0.55;
}

.square-state.is-suspended .state-title {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.state-btn.ghost {
  background: transparent;
}

.state-icon {
  width: 40px;
  height: 40px;
  color: var(--app-text-muted);
  opacity: 0.6;
}

.state-icon svg {
  width: 40px;
  height: 40px;
}

.state-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.state-hint {
  margin: 0;
  max-width: 360px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--app-text-muted);
}

.state-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.state-btn {
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
  border-radius: 9px;
  padding: 8px 20px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.state-btn:hover {
  border-color: var(--color-brand, #4f46e5);
  color: var(--color-brand, #4f46e5);
}

.state-btn.primary {
  background: var(--color-brand, #4f46e5);
  border-color: var(--color-brand, #4f46e5);
  color: #fff;
}

.state-btn.primary:hover {
  filter: brightness(1.08);
}
</style>
