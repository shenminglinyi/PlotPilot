<template>
  <teleport to="body">
    <div class="plaza-fab-shell">
      <!-- FAB 主按钮 -->
      <button
        ref="fabRef"
        type="button"
        class="plaza-fab-main"
        :class="{ 'is-open': showDrawer }"
        aria-label="打开提示词广场"
        @click="toggleDrawer"
      >
        <span class="fab-glow"></span>
        <span class="fab-content">
          <span class="fab-icon">🏪</span>
          <span v-if="showDrawer" class="fab-label">提示词广场</span>
        </span>
        <!-- 角标：提示词数量 -->
        <span v-if="promptCount > 0" class="fab-badge">{{ promptCount }}</span>
      </button>

      <!-- 抽屉 -->
      <n-drawer
        :show="showDrawer"
        placement="right"
        :width="720"
        :close-on-esc="true"
        :mask-closable="true"
        @update:show="handleDrawerChange"
      >
        <n-drawer-content
          closable
          :header-style="{ padding: '16px 20px' }"
          :native-scrollbar="false"
          :body-content-style="{ padding: 0, overflow: 'hidden' }"
        >
          <template #header>
            <div class="drawer-header">
              <div class="drawer-title-row">
                <span class="drawer-icon">🏪</span>
                <span class="drawer-title">提示词广场</span>
                <n-tag size="small" type="info" :bordered="false" v-if="stats">
                  {{ stats.total_nodes }} 个 · {{ stats.total_versions }} 版本
                </n-tag>
              </div>
              <p class="drawer-subtitle">
                浏览、编辑、版本管理所有 AI 提示词
              </p>
            </div>
          </template>

          <PromptPlaza @refresh-stats="loadStats" />
        </n-drawer-content>
      </n-drawer>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NDrawer, NDrawerContent, NTag } from 'naive-ui'
import PromptPlaza from '../workbench/PromptPlaza.vue'
import { promptPlazaApi, type PromptStats } from '../../api/llmControl'

const fabRef = ref<HTMLButtonElement>()
const showDrawer = ref(false)
const promptCount = ref(0)
const stats = ref<PromptStats | null>(null)

function toggleDrawer() {
  showDrawer.value = !showDrawer.value
}

function handleDrawerChange(val: boolean) {
  showDrawer.value = val
}

async function loadStats() {
  try {
    const res = await promptPlazaApi.getStats()
    const data = res as unknown as PromptStats
    stats.value = data
    promptCount.value = data?.total_nodes || 0
  } catch {
    // 静默失败
  }
}

onMounted(() => {
  loadStats()
})

// 暴露方法供外部调用
defineExpose({
  open: () => { showDrawer.value = true },
  close: () => { showDrawer.value = false },
})
</script>

<style scoped>
.plaza-fab-shell {
  position: fixed;
  z-index: 890; /* 略低于 AI 控制台的 900 */
}

/* ---- FAB 主按钮 ---- */
.plaza-fab-main {
  position: fixed;
  bottom: 24px;
  right: 80px; /* 在 AI 控制台左边 */
  width: 52px;
  height: 52px;
  border-radius: 16px;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  box-shadow:
    0 4px 14px rgba(99, 102, 241, 0.35),
    0 2px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  outline: none;
  overflow: visible;
}
.plaza-fab-main:hover {
  transform: translateY(-2px) scale(1.05);
  box-shadow:
    0 8px 24px rgba(99, 102, 241, 0.45),
    0 4px 10px rgba(0, 0, 0, 0.15);
}
.plaza-fab-main:active {
  transform: scale(0.96);
}
.plaza-fab-main.is-open {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  box-shadow:
    0 2px 8px rgba(79, 70, 229, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.fab-glow {
  position: absolute;
  inset: -2px;
  border-radius: 18px;
  background: conic-gradient(
    from 180deg,
    transparent,
    rgba(167, 139, 250, 0.4),
    transparent,
    rgba(99, 102, 241, 0.4),
    transparent
  );
  opacity: 0;
  transition: opacity 0.3s;
  z-index: -1;
  animation: glow-spin 4s linear infinite paused;
}
.plaza-fab-main:hover .fab-glow,
.plaza-fab-main.is-open .fab-glow {
  opacity: 1;
  animation-play-state: running;
}
@keyframes glow-spin {
  to { transform: rotate(360deg); }
}

.fab-content {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
  z-index: 1;
}
.fab-icon {
  font-size: 22px;
  line-height: 1;
  transition: transform 0.3s;
}
.plaza-fab-main:hover .fab-icon,
.plaza-fab-main.is-open .fab-icon {
  transform: scale(1.15) rotate(-5deg);
}
.fab-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.3px;
  animation: fade-in 0.25s ease-out;
}
@keyframes fade-in {
  from { opacity: 0; transform: translateX(8px); }
  to { opacity: 1; transform: translateX(0); }
}

/* 角标 */
.fab-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background: #ef4444;
  color: white;
  font-size: 11px;
  font-weight: 700;
  line-height: 20px;
  text-align: center;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.35);
  pointer-events: none;
}

/* ---- 抽屉头部 ---- */
.drawer-header {
  width: 100%;
}
.drawer-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.drawer-icon {
  font-size: 22px;
}
.drawer-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--n-text-color-1, #333);
}
.drawer-subtitle {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--n-text-color-3, #999);
  letter-spacing: 0.2px;
}
</style>
