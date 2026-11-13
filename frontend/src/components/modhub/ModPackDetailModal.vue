<template>
  <teleport to="body">
    <div
      v-if="show && pack"
      class="mod-detail-mask"
      role="dialog"
      aria-modal="true"
      :aria-label="pack.name"
      @click.self="$emit('close')"
    >
      <div class="mod-detail-dialog">
        <!-- 顶栏：印章 + 标题 + 作者源 + 主操作按钮 -->
        <header class="detail-head">
          <div class="detail-glyph" aria-hidden="true">{{ pack.glyph }}</div>
          <div class="detail-title-col">
            <h3 class="detail-title">{{ pack.name }}</h3>
            <div class="detail-origin">
              <span>{{ pack.author }}</span>
              <span class="origin-sep">·</span>
              <span>{{ pack.repoOrOrigin }}</span>
            </div>
          </div>
          <div class="detail-head-actions">
            <template v-if="installed">
              <span class="installed-state-pill">
                <svg viewBox="0 0 16 16" fill="none" class="btn-svg" aria-hidden="true">
                  <path
                    d="M13.2 4.6 6.6 11.2 3.2 7.8"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                已启用
              </span>
              <button
                type="button"
                class="detail-action-btn is-uninstall"
                :disabled="busy"
                @click="$emit('uninstall', pack)"
              >
                {{ busy ? '正在回滚…' : '卸载并回滚' }}
              </button>
            </template>
            <button
              v-else
              type="button"
              class="detail-action-btn is-primary"
              :disabled="busy"
              @click="$emit('install', pack)"
            >
              <svg viewBox="0 0 16 16" fill="none" class="btn-svg" aria-hidden="true">
                <path
                  d="M8 2.8v7.6M4.8 7.6 8 10.8l3.2-3.2M3.2 13.2h9.6"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span>{{ busy ? '安装中…' : '安装模组' }}</span>
            </button>

            <button
              type="button"
              class="detail-close-btn"
              aria-label="关闭详情"
              @click="$emit('close')"
            >
              <svg viewBox="0 0 24 24" fill="none" width="18" height="18" aria-hidden="true">
                <path
                  d="M18 6 6 18M6 6l12 12"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </div>
        </header>

        <!-- 主体滚动区 -->
        <div class="detail-scroll">
          <p class="detail-lead">{{ pack.summary }}</p>

          <!-- 对标 Magpie 详情页的四宫格契约条 -->
          <div class="contract-grid">
            <div class="contract-cell">
              <span class="contract-label">版本</span>
              <strong class="contract-val numeric">{{ pack.version }}</strong>
            </div>
            <div class="contract-cell">
              <span class="contract-label">接管范围</span>
              <strong class="contract-val numeric">{{ scopeSummary }}</strong>
            </div>
            <div class="contract-cell">
              <span class="contract-label">许可证</span>
              <strong class="contract-val">{{ pack.license }}</strong>
            </div>
            <div class="contract-cell">
              <span class="contract-label">更新于</span>
              <strong class="contract-val numeric">{{ pack.updatedAt }}</strong>
            </div>
          </div>

          <!-- 来源与分享芯片 -->
          <div class="chip-toolbar">
            <span class="origin-badge">{{ pack.roleLabel }}</span>
            <span v-for="tag in pack.tags" :key="tag" class="tag-badge">{{ tag }}</span>
            <button type="button" class="export-pack-btn" @click="$emit('export-pack', pack)">
              导出 plotpilot-mod.json
            </button>
          </div>

          <!-- 安全边界与可回滚说明条 -->
          <div
            class="safety-banner"
            :class="{ 'is-unreviewed': pack.trustLevel === 'community-unreviewed' }"
          >
            <svg viewBox="0 0 20 20" fill="none" class="safety-icon" aria-hidden="true">
              <path
                d="M10 2.5 3.5 5.4v4.4c0 4.1 2.8 7.8 6.5 8.7 3.7-.9 6.5-4.6 6.5-8.7V5.4L10 2.5Z"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linejoin="round"
              />
              <path
                d="M7.5 10.2 9.2 11.9 12.8 8.3"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <p v-if="pack.trustLevel === 'community-unreviewed'" class="safety-text">
              <strong>非官方社区模组：</strong>由 {{ pack.author }} 发布，尚未经过官方人工审阅。安装后将修改「{{ overrideNamesText }}」的生成提示词，卸载时可一键回滚至原版。
            </p>
            <p v-else class="safety-text">
              <strong>无损快照保护：</strong>安装后将自动注入「{{ overrideNamesText }}」环节，完整保留引擎原有模板变量与输出格式；卸载时一键恢复原版快照。
            </p>
          </div>

          <!-- 内部视图切换：效果样章 vs 节点源码 -->
          <div class="detail-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              class="detail-tab"
              :class="{ 'is-active': activeTab === 'readme' }"
              :aria-selected="activeTab === 'readme'"
              @click="activeTab = 'readme'"
            >
              效果对比与说明
            </button>
            <button
              type="button"
              role="tab"
              class="detail-tab"
              :class="{ 'is-active': activeTab === 'nodes' }"
              :aria-selected="activeTab === 'nodes'"
              @click="activeTab = 'nodes'"
            >
              接管节点明细 ({{ pack.overrides.length }})
            </button>
          </div>

          <!-- 视图 1：Before/After 样章对比 + Readme -->
          <div v-if="activeTab === 'readme'" class="tab-pane">
            <section v-if="pack.showcase" class="showcase-block">
              <div class="showcase-head">
                <h4 class="section-heading">实测样章对比</h4>
                <span class="showcase-scenario">测试命题：{{ pack.showcase.scenario }}</span>
              </div>
              <div class="showcase-columns">
                <div class="showcase-col is-before">
                  <div class="col-badge">{{ pack.showcase.beforeLabel || '未装模组（默认生成）' }}</div>
                  <p class="col-excerpt">{{ pack.showcase.beforeExcerpt }}</p>
                </div>
                <div class="showcase-col is-after">
                  <div class="col-badge is-good">{{ pack.showcase.afterLabel || '启用本模组后' }}</div>
                  <p class="col-excerpt">{{ pack.showcase.afterExcerpt }}</p>
                </div>
              </div>
            </section>

            <section
              v-for="(sec, idx) in pack.readmeSections"
              :key="idx"
              class="readme-section"
            >
              <h4 class="section-heading">{{ sec.heading }}</h4>
              <p class="readme-body">{{ sec.body }}</p>
            </section>
          </div>

          <!-- 视图 2：接管节点技术明细 -->
          <div v-else class="tab-pane nodes-pane">
            <div
              v-for="ov in pack.overrides"
              :key="ov.nodeKey"
              class="override-card"
            >
              <div class="override-head">
                <div class="override-title-wrap">
                  <strong class="override-label">{{ ov.nodeLabel }}</strong>
                  <code class="override-key">{{ ov.nodeKey }}</code>
                  <span class="override-mode">{{ modeLabel(ov.mode) }}</span>
                </div>
                <button
                  type="button"
                  class="inspect-node-btn"
                  @click="$emit('inspect-node', ov.nodeKey)"
                >
                  在内核编辑器中查看 →
                </button>
              </div>
              <pre class="override-code">{{ ov.systemContent || '（点击安装后自动从云端同步完整模板正文）' }}</pre>
            </div>
          </div>
        </div>

        <!-- 底部说明栏 -->
        <footer class="detail-foot">
          <span class="foot-note">
            模组仅修改本机 SQLite 提示词快照，不会读取或外发你的书稿内容。
          </span>
          <button type="button" class="foot-close-btn" @click="$emit('close')">关闭</button>
        </footer>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ModNodeOverride, NarrativeModPack } from '@/domain/modPack/types'

const props = defineProps<{
  show: boolean
  pack: NarrativeModPack | null
  installed: boolean
  busy?: boolean
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'install', pack: NarrativeModPack): void
  (e: 'uninstall', pack: NarrativeModPack): void
  (e: 'export-pack', pack: NarrativeModPack): void
  (e: 'inspect-node', nodeKey: string): void
}>()

const activeTab = ref<'readme' | 'nodes'>('readme')

watch(
  () => props.pack?.id,
  () => {
    activeTab.value = 'readme'
  },
)

const scopeSummary = computed(() => {
  if (!props.pack) return ''
  const count = props.pack.overrides.length
  return props.pack.replacesBuiltin ? `替代内置 · ${count} 节点` : `新增扩展 · ${count} 节点`
})

const overrideNamesText = computed(() => {
  if (!props.pack) return ''
  const labels = props.pack.overrides.map(o => o.nodeLabel)
  if (labels.length <= 3) return labels.join('、')
  return `${labels.slice(0, 3).join('、')} 等 ${labels.length} 个`
})

function modeLabel(mode: ModNodeOverride['mode']): string {
  if (mode === 'append_protocol') return '无损协议挂载'
  if (mode === 'replace_system') return '完整接管 System'
  return '独立自定义节点'
}
</script>

<style scoped>
.mod-detail-mask {
  position: fixed;
  inset: 0;
  z-index: 3100;
  background: rgba(15, 15, 14, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.mod-detail-dialog {
  width: 100%;
  max-width: 720px;
  max-height: 86vh;
  background: var(--app-surface);
  border: 1px solid var(--app-border-strong);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 22px 16px;
  border-bottom: 1px solid var(--app-border);
  flex-shrink: 0;
}

.detail-glyph {
  width: 44px;
  height: 44px;
  border-radius: 11px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-primary);
  font-size: 18px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.detail-title-col {
  flex: 1;
  min-width: 0;
}

.detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--app-text-primary);
}

.detail-origin {
  margin-top: 3px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13px;
  color: var(--app-text-muted);
}

.origin-sep {
  opacity: 0.6;
}

.detail-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.installed-state-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 10px;
  border-radius: 8px;
  background: var(--color-success-light);
  color: var(--color-success);
  font-size: 13px;
  font-weight: 600;
}

.detail-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.detail-action-btn.is-primary {
  background: var(--color-brand);
  border: 1px solid var(--color-brand);
  color: var(--app-text-inverse);
}

.detail-action-btn.is-primary:hover:not(:disabled) {
  background: var(--color-brand-hover);
  border-color: var(--color-brand-hover);
}

.detail-action-btn.is-uninstall {
  background: var(--app-surface);
  border: 1px solid var(--app-border-strong);
  color: var(--app-text-secondary);
}

.detail-action-btn.is-uninstall:hover:not(:disabled) {
  border-color: var(--color-error);
  color: var(--color-error);
  background: var(--color-error-light);
}

.detail-action-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.btn-svg {
  width: 14px;
  height: 14px;
}

.detail-close-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--app-text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.detail-close-btn:hover {
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
}

.detail-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 20px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-lead {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--app-text-primary);
  max-width: 58ch;
}

.contract-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface-subtle);
  overflow: hidden;
}

.contract-cell {
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-right: 1px solid var(--app-border);
}

.contract-cell:last-child {
  border-right: none;
}

.contract-label {
  font-size: 12px;
  color: var(--app-text-muted);
}

.contract-val {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.chip-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.origin-badge {
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 600;
}

.tag-badge {
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-secondary);
  font-size: 12px;
}

.export-pack-btn {
  margin-left: auto;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.export-pack-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.safety-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-secondary);
}

.safety-banner.is-unreviewed {
  background: var(--color-warning-light);
  border-color: color-mix(in srgb, var(--color-warning) 28%, var(--app-border));
  color: var(--color-warning);
}

.safety-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-brand);
}

.safety-banner.is-unreviewed .safety-icon {
  color: var(--color-warning);
}

.safety-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  max-width: 58ch;
}

.detail-tabs {
  display: flex;
  gap: 18px;
  border-bottom: 1px solid var(--app-border);
  margin-top: 2px;
}

.detail-tab {
  padding: 8px 2px 10px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  margin-bottom: -1px;
}

.detail-tab:hover {
  color: var(--app-text-primary);
}

.detail-tab.is-active {
  color: var(--color-brand);
  border-bottom-color: var(--color-brand);
  font-weight: 600;
}

.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.showcase-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.showcase-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.section-heading {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.showcase-scenario {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.showcase-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.showcase-col {
  padding: 14px;
  border-radius: 10px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.showcase-col.is-after {
  background: var(--app-surface);
  border-color: color-mix(in srgb, var(--color-brand) 38%, var(--app-border));
}

.col-badge {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.col-badge.is-good {
  background: var(--color-brand-light);
  border-color: transparent;
  color: var(--color-brand);
}

.col-excerpt {
  margin: 0;
  font-size: 14px;
  line-height: 1.68;
  color: var(--app-text-primary);
}

.readme-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.readme-body {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--app-text-secondary);
  max-width: 58ch;
  white-space: pre-line;
}

.nodes-pane {
  gap: 12px;
}

.override-card {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface-subtle);
  overflow: hidden;
}

.override-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
}

.override-title-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.override-label {
  font-size: 13.5px;
  color: var(--app-text-primary);
}

.override-key {
  font-size: 12px;
  font-family: var(--font-mono);
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--app-surface-subtle);
  color: var(--app-text-muted);
}

.override-mode {
  font-size: 11.5px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-weight: 500;
}

.inspect-node-btn {
  border: none;
  background: transparent;
  color: var(--color-brand);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 4px;
}

.inspect-node-btn:hover {
  text-decoration: underline;
}

.override-code {
  margin: 0;
  padding: 12px 14px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
}

.detail-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 22px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  flex-shrink: 0;
}

.foot-note {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.foot-close-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.foot-close-btn:hover {
  border-color: var(--app-border-strong);
  color: var(--app-text-primary);
}

@media (max-width: 640px) {
  .contract-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .contract-cell:nth-child(2) {
    border-right: none;
  }
  .contract-cell:nth-child(1),
  .contract-cell:nth-child(2) {
    border-bottom: 1px solid var(--app-border);
  }
  .showcase-columns {
    grid-template-columns: 1fr;
  }
  .detail-head {
    flex-wrap: wrap;
  }
  .detail-head-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
