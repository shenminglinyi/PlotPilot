<template>
  <section class="about-brand">
    <div class="brand-panel">
      <div class="brand-mark" aria-hidden="true">墨</div>
      <div class="brand-main">
        <div class="brand-kicker">{{ BRAND.descriptor }}</div>
        <h2 class="brand-title">{{ BRAND.displayName }}</h2>
        <p class="brand-line">{{ BRAND.credit }}</p>
      </div>
    </div>

    <div class="update-panel">
      <div class="update-copy">
        <span class="info-label">应用更新</span>
        <strong>当前版本 {{ currentVersion || '开发模式' }}</strong>
        <span class="update-status">{{ updateStatusText }}</span>
      </div>
      <n-space v-if="desktopRuntime" :size="8" align="center">
        <n-button
          v-if="status === 'available'"
          size="small"
          type="primary"
          secondary
          @click="downloadUpdate"
        >
          下载 {{ availableVersion }}
        </n-button>
        <n-button
          v-else-if="status === 'ready'"
          size="small"
          type="primary"
          @click="installAndRestart"
        >
          安装并重启
        </n-button>
        <n-button
          v-else
          size="small"
          :loading="status === 'checking' || status === 'downloading' || status === 'installing'"
          @click="checkForUpdate({ manual: true })"
        >
          检查更新
        </n-button>
      </n-space>
    </div>

    <div class="info-grid">
      <div class="info-item">
        <span class="info-label">产品定位</span>
        <span class="info-value">{{ BRAND.chineseName }} · {{ BRAND.tagline }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">开发团队</span>
        <span class="info-value">{{ BRAND.team }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">直播时间</span>
        <span class="info-value">{{ BRAND.liveSchedule }}</span>
      </div>
      <a
        class="info-item info-item--link"
        :href="BRAND.douyinUrl"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span class="info-label">抖音</span>
        <span class="info-value">{{ BRAND.douyinLabel }}</span>
      </a>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { BRAND } from '@/constants/brand'
import { useAppUpdateStore } from '@/stores/appUpdateStore'

const updater = useAppUpdateStore()
const {
  status,
  currentVersion,
  availableVersion,
  errorText,
} = storeToRefs(updater)
const { checkForUpdate, downloadUpdate, initialize, installAndRestart } = updater
const desktopRuntime = updater.desktopRuntime

const updateStatusText = computed(() => {
  if (!desktopRuntime) return '自动更新仅在桌面安装版中启用'
  if (status.value === 'checking') return '正在检查新版本…'
  if (status.value === 'available') return `发现新版本 ${availableVersion.value}`
  if (status.value === 'downloading') return `正在下载 ${availableVersion.value}`
  if (status.value === 'ready') return `${availableVersion.value} 已下载，等待安装`
  if (status.value === 'installing') return '正在安全退出并安装…'
  if (status.value === 'up-to-date') return '当前已是最新版本'
  if (status.value === 'error') return errorText.value || '检查更新失败'
  return '启动后自动检查，也可以手动检查'
})

onMounted(() => { void initialize() })
</script>

<style scoped>
.about-brand {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.brand-panel {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 1rem;
  align-items: center;
  padding: 1.125rem;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background:
    linear-gradient(90deg, var(--color-brand-light), transparent 62%),
    var(--app-surface);
}

.brand-mark {
  width: 3.25rem;
  height: 3.25rem;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  font-size: 1.5rem;
  font-weight: 800;
}

.brand-main {
  min-width: 0;
}

.brand-kicker {
  font-size: var(--font-size-xs);
  color: var(--app-text-muted);
  margin-bottom: 0.25rem;
}

.brand-title {
  margin: 0;
  font-size: 1.35rem;
  line-height: 1.25;
  color: var(--app-text-primary);
}

.brand-line {
  margin: 0.375rem 0 0;
  color: var(--app-text-secondary);
  line-height: 1.55;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.update-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.875rem;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface);
}

.update-copy {
  min-width: 0;
  display: grid;
  gap: 0.25rem;
}

.update-copy strong {
  font-size: var(--font-size-base);
}

.update-status {
  color: var(--app-text-muted);
  font-size: var(--font-size-xs);
  line-height: var(--line-height-ui);
  overflow-wrap: anywhere;
}

.info-item {
  min-width: 0;
  padding: 0.875rem;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  color: inherit;
  text-decoration: none;
}

.info-item--link {
  transition: border-color 0.2s ease, background 0.2s ease;
}

.info-item--link:hover {
  border-color: var(--color-brand);
  background: var(--color-brand-light);
}

.info-label,
.info-value {
  display: block;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--app-text-muted);
  margin-bottom: 0.375rem;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--app-text-primary);
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .brand-panel,
  .info-grid,
  .update-panel {
    grid-template-columns: 1fr;
  }

  .update-panel {
    align-items: flex-start;
    flex-direction: column;
  }

  .brand-mark {
    width: 2.75rem;
    height: 2.75rem;
  }
}
</style>
