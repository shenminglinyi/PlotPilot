<template>
  <div class="square-shell">
    <header class="square-topbar">
      <button type="button" class="square-back" aria-label="返回书架" @click="goBack">
        <svg viewBox="0 0 20 20" fill="none" class="back-icon" aria-hidden="true">
          <path
            d="M12.5 15 7.5 10l5-5"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span>返回</span>
      </button>

      <div class="square-brand-group">
        <h1 class="square-title">墨枢模组中心</h1>
        <span class="square-sub">本地叙事模组 · plotpilot.xyz 云端书元 · GitHub 开源生态</span>
      </div>

      <div class="square-session">
        <template v-if="session?.logged_in">
          <span class="session-chip" :title="session.username">
            <span class="session-dot" />
            {{ session.display_name || session.username }}
          </span>
          <button type="button" class="top-btn" @click="handleLogout">退出云端</button>
        </template>
        <template v-else>
          <button type="button" class="top-btn is-primary" @click="showLogin = true">
            登录云端
          </button>
        </template>
        <button
          type="button"
          class="top-btn"
          :disabled="refreshing"
          @click="handleRefreshAll"
        >
          {{ refreshing ? '同步中…' : '刷新' }}
        </button>
      </div>
    </header>

    <main class="square-main">
      <PromptPlaza
        ref="hubRef"
        :full-page="true"
        :initial-tab="initialTab"
        :initial-discover-source="initialSource"
        @request-cloud-login="showLogin = true"
      />
    </main>

    <!-- 云端账号登录弹窗 -->
    <n-modal
      v-model:show="showLogin"
      preset="dialog"
      title="登录 plotpilot.xyz 云端账号"
      positive-text="登录"
      negative-text="取消"
      :loading="loginLoading"
      @positive-click="handleLogin"
    >
      <div class="login-form">
        <p class="login-hint">
          登录后可解锁全网小说热榜风向与社区互动；凭证仅保存在本机后端会话，浏览器侧零明文存储。
        </p>
        <label class="login-field">
          <span>账号</span>
          <input
            v-model="loginForm.username"
            type="text"
            autocomplete="username"
            placeholder="输入云端用户名"
          />
        </label>
        <label class="login-field">
          <span>密码</span>
          <input
            v-model="loginForm.password"
            type="password"
            autocomplete="current-password"
            placeholder="输入密码"
            @keydown.enter="handleLogin"
          />
        </label>
        <p v-if="loginError" class="login-error">{{ loginError }}</p>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NModal } from 'naive-ui'
import {
  fetchCloudSession,
  loginCloudSession,
  logoutCloudSession,
  type CloudSessionStatus,
} from '@/api/cloudSquare'
import PromptPlaza, {
  type DiscoverSourceKey,
  type ModHubMainTab,
} from '@/components/workbench/PromptPlaza.vue'

const router = useRouter()
const route = useRoute()

const hubRef = ref<{
  loadData: () => Promise<void>
  refreshCloudFeeds: (force?: boolean) => Promise<void>
} | null>(null)

const initialTab = computed<ModHubMainTab>(() => {
  const q = String(route.query.tab || '')
  if (q === 'installed' || q === 'nodes' || q === 'anti-ai') return q
  return 'discover'
})

const initialSource = computed<DiscoverSourceKey>(() => {
  const s = String(route.query.source || '')
  if (
    s === 'curated' ||
    s === 'cloud-official' ||
    s === 'cloud-community' ||
    s === 'hot'
  ) {
    return s
  }
  return 'all'
})

const session = ref<CloudSessionStatus | null>(null)
const refreshing = ref(false)
const showLogin = ref(false)
const loginLoading = ref(false)
const loginError = ref('')
const loginForm = reactive({ username: '', password: '' })

async function loadSession(): Promise<void> {
  try {
    session.value = await fetchCloudSession()
  } catch {
    session.value = { logged_in: false }
  }
}

async function handleLogin(): Promise<boolean> {
  if (!loginForm.username.trim() || !loginForm.password) {
    loginError.value = '请输入用户名和密码'
    return false
  }
  loginLoading.value = true
  loginError.value = ''
  try {
    session.value = await loginCloudSession(
      loginForm.username.trim(),
      loginForm.password,
    )
    showLogin.value = false
    loginForm.password = ''
    await hubRef.value?.refreshCloudFeeds(true)
    return true
  } catch (e) {
    loginError.value = e instanceof Error ? e.message : '登录失败'
    return false
  } finally {
    loginLoading.value = false
  }
}

async function handleLogout(): Promise<void> {
  try {
    await logoutCloudSession()
    session.value = { logged_in: false }
  } catch {
    // 忽略网络抖动
  }
}

async function handleRefreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.all([
      loadSession(),
      hubRef.value?.loadData(),
      hubRef.value?.refreshCloudFeeds(true),
    ])
  } finally {
    refreshing.value = false
  }
}

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    void router.push('/')
  }
}

onMounted(() => {
  void loadSession()
})
</script>

<style scoped>
.square-shell {
  min-height: 100vh;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--app-page-bg);
  color: var(--app-text-primary);
  overflow: hidden;
}

.square-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  flex-shrink: 0;
}

.square-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 34px;
  padding: 0 12px 0 8px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.square-back:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.back-icon {
  width: 16px;
  height: 16px;
}

.square-brand-group {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}

.square-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.square-sub {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.square-session {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.session-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--color-success-light);
  color: var(--color-success);
  font-size: 12.5px;
  font-weight: 600;
}

.session-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.top-btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.top-btn:hover:not(:disabled) {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.top-btn.is-primary {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: var(--app-text-inverse);
  font-weight: 600;
}

.top-btn.is-primary:hover:not(:disabled) {
  background: var(--color-brand-hover);
  border-color: var(--color-brand-hover);
  color: var(--app-text-inverse);
}

.top-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.square-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
}

.login-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--app-text-muted);
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.login-field input {
  height: 36px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-primary);
  font-size: 13.5px;
  outline: none;
}

.login-field input:focus {
  border-color: var(--color-brand);
}

.login-error {
  margin: 0;
  font-size: 12.5px;
  color: var(--color-error);
}

@media (max-width: 640px) {
  .square-topbar {
    padding: 10px 14px;
    flex-wrap: wrap;
  }
  .square-sub {
    display: none;
  }
}
</style>
