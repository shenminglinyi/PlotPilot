<template>
  <teleport to="body">
    <div
      v-if="show"
      class="builder-mask"
      role="dialog"
      aria-modal="true"
      aria-label="打包制作叙事模组"
      @click.self="$emit('close')"
    >
      <div class="builder-dialog">
        <header class="builder-head">
          <div>
            <h3 class="builder-title">打包制作叙事模组</h3>
            <p class="builder-sub">
              将你调优过的提示词节点封装为标准 <code>plotpilot-mod/v1</code> 清单，一键分享至 GitHub 社区。
            </p>
          </div>
          <button type="button" class="builder-close" aria-label="关闭" @click="$emit('close')">
            <svg viewBox="0 0 24 24" fill="none" width="18" height="18" aria-hidden="true">
              <path
                d="M18 6 6 18M6 6l12 12"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>

        <div class="builder-body">
          <!-- 基本元数据 -->
          <div class="form-grid">
            <label class="field-item">
              <span class="field-label">模组名称</span>
              <input
                v-model="form.name"
                type="text"
                class="field-input"
                placeholder="例如：硬核刑侦·冷峻程序流"
              />
            </label>
            <label class="field-item is-narrow">
              <span class="field-label">方章单字</span>
              <input
                v-model="form.glyph"
                type="text"
                maxlength="2"
                class="field-input"
                placeholder="刑"
              />
            </label>
            <label class="field-item">
              <span class="field-label">作者署名</span>
              <input
                v-model="form.author"
                type="text"
                class="field-input"
                placeholder="你的笔名或 GitHub ID"
              />
            </label>
            <label class="field-item">
              <span class="field-label">能力分区</span>
              <select v-model="form.roleCategory" class="field-input">
                <option
                  v-for="cat in roleOptions"
                  :key="cat.key"
                  :value="cat.key"
                >
                  {{ cat.label }}
                </option>
              </select>
            </label>
          </div>

          <label class="field-item">
            <span class="field-label">一句话人话价值（展示在卡片正面，让读者 3 秒看懂有什么用）</span>
            <textarea
              v-model="form.summary"
              rows="2"
              class="field-textarea"
              placeholder="例如：消除悬浮推理套话，强制按现场物证链与审讯心理博弈推进章节正文。"
            />
          </label>

          <!-- 选择要打包的引擎节点 -->
          <div class="node-picker-block">
            <div class="picker-head">
              <span class="field-label">
                选择要纳入模组的引擎节点（已选 <strong class="numeric">{{ selectedKeys.length }}</strong> 个）
              </span>
              <input
                v-model="nodeFilter"
                type="text"
                class="picker-search"
                placeholder="筛选节点名称或键…"
              />
            </div>

            <div class="picker-list">
              <label
                v-for="node in sortedNodes"
                :key="node.node_key"
                class="picker-row"
                :class="{ 'is-checked': selectedKeys.includes(node.node_key) }"
              >
                <input
                  type="checkbox"
                  :value="node.node_key"
                  v-model="selectedKeys"
                />
                <span class="picker-node-name">{{ node.name }}</span>
                <code class="picker-node-key">{{ node.node_key }}</code>
                <span v-if="node.has_user_edit" class="edited-pill">已调优</span>
              </label>
            </div>
          </div>

          <!-- 可选样章对比 -->
          <details class="showcase-details">
            <summary class="showcase-summary">附带实测样章对比（选填，强烈推荐填写以提升社区安装率）</summary>
            <div class="showcase-fields">
              <input
                v-model="form.scenario"
                type="text"
                class="field-input"
                placeholder="测试场景，例如：雨夜勘查失踪案第一现场"
              />
              <div class="showcase-pair">
                <textarea
                  v-model="form.beforeExcerpt"
                  rows="3"
                  class="field-textarea"
                  placeholder="未装模组时的默认 AI 味片段…"
                />
                <textarea
                  v-model="form.afterExcerpt"
                  rows="3"
                  class="field-textarea"
                  placeholder="启用你的模组后生成的样章片段…"
                />
              </div>
            </div>
          </details>
        </div>

        <footer class="builder-foot">
          <span class="foot-hint">导出后放入 GitHub 仓库根目录并命名为 <code>plotpilot-mod.json</code>，他人即可通过 <code>github:owner/repo</code> 一键安装。</span>
          <div class="foot-btns">
            <button
              type="button"
              class="builder-btn"
              :disabled="submitting || !canSubmit"
              @click="handleSaveLocal"
            >
              保存到本地已安装
            </button>
            <button
              type="button"
              class="builder-btn is-primary"
              :disabled="submitting || !canSubmit"
              @click="handleExportFile"
            >
              {{ submitting ? '正在打包…' : '导出 plotpilot-mod.json' }}
            </button>
          </div>
        </footer>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { promptPlazaApi, type PromptNode, type PromptNodeDetail } from '@/api/llmControl'
import {
  MOD_ROLE_CATEGORIES,
  type ModNodeOverride,
  type ModRoleCategory,
  type NarrativeModPack,
} from '@/domain/modPack/types'
import {
  stripModDelimiterComments,
  useModHubStore,
} from '@/stores/modHubStore'

const props = defineProps<{
  show: boolean
  nodes: PromptNode[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', pack: NarrativeModPack): void
}>()

const message = useMessage()
const modHubStore = useModHubStore()

const roleOptions = MOD_ROLE_CATEGORIES.filter(c => c.key !== 'all') as Array<{
  key: Exclude<ModRoleCategory, 'all'>
  label: string
}>

const form = reactive({
  name: '',
  glyph: '',
  author: '',
  roleCategory: 'style-anti-ai' as Exclude<ModRoleCategory, 'all'>,
  summary: '',
  scenario: '',
  beforeExcerpt: '',
  afterExcerpt: '',
})

const nodeFilter = ref('')
const selectedKeys = ref<string[]>([])
const submitting = ref(false)

watch(
  () => props.show,
  (open) => {
    if (!open) return
    // 默认自动勾选用户已修改过的节点，降低打包操作成本
    const edited = props.nodes.filter(n => n.has_user_edit).map(n => n.node_key)
    selectedKeys.value = edited.slice(0, 6)
  },
)

const sortedNodes = computed(() => {
  const q = nodeFilter.value.trim().toLowerCase()
  const list = q
    ? props.nodes.filter(
        n =>
          n.name.toLowerCase().includes(q) ||
          n.node_key.toLowerCase().includes(q),
      )
    : props.nodes
  return [...list].sort((a, b) => {
    if (a.has_user_edit !== b.has_user_edit) return a.has_user_edit ? -1 : 1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
})

const canSubmit = computed(
  () => form.name.trim().length > 0 && selectedKeys.value.length > 0,
)

async function assemblePack(forLocalInstall = false): Promise<NarrativeModPack> {
  const packId = `mod-custom-${Date.now().toString(36)}`
  const overrides: ModNodeOverride[] = []
  for (const key of selectedKeys.value) {
    const detail = (await promptPlazaApi.getNodeDetail(key)) as unknown as PromptNodeDetail
    const cleanedSystem = stripModDelimiterComments(detail.system || '').trim()
    overrides.push({
      nodeKey:
        !detail.is_builtin && forLocalInstall
          ? `${packId}-${detail.node_key}`.slice(0, 120)
          : detail.node_key,
      nodeLabel: detail.name,
      mode: detail.is_builtin ? 'replace_system' : 'standalone_node',
      systemContent: cleanedSystem || `### ${detail.name}\n${detail.description || form.name.trim()}`,
      userTemplate: detail.user_template || undefined,
      backendCategory: detail.category,
    })
  }

  const roleMeta = roleOptions.find(r => r.key === form.roleCategory)
  const cleanName = form.name.trim()
  const cleanAuthor = form.author.trim() || '本地创作者'

  return {
    id: packId,
    name: cleanName,
    glyph: (form.glyph.trim() || cleanName.charAt(0) || '模').slice(0, 2),
    author: cleanAuthor,
    repoOrOrigin: '本地打包工坊',
    trustLevel: 'local',
    roleCategory: form.roleCategory,
    roleLabel: roleMeta?.label || '自定义模组',
    summary:
      form.summary.trim() ||
      `由 ${cleanAuthor} 封装的叙事模组，包含 ${overrides.length} 个引擎节点配置。`,
    readmeSections: [
      {
        heading: '模组说明',
        body:
          form.summary.trim() ||
          `包含对 ${overrides.map(o => o.nodeLabel).join('、')} 的定制化提示词调优。`,
      },
    ],
    version: 'v1.0.0',
    license: 'MIT',
    updatedAt: new Date().toISOString().slice(0, 10),
    usageLabel: '本地自制',
    replacesBuiltin: overrides.some(o => o.mode !== 'standalone_node'),
    overrides,
    showcase:
      form.beforeExcerpt.trim() && form.afterExcerpt.trim()
        ? {
            scenario: form.scenario.trim() || '创作实测片段',
            beforeExcerpt: form.beforeExcerpt.trim(),
            afterExcerpt: form.afterExcerpt.trim(),
          }
        : undefined,
    tags: [roleMeta?.label || '自定义', `${overrides.length} 节点`],
  }
}

async function handleExportFile(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const pack = await assemblePack()
    const manifest = modHubStore.createManifestFromPack(pack)
    const blob = new Blob([JSON.stringify(manifest, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'plotpilot-mod.json'
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出 plotpilot-mod.json 清单文件')
    emit('created', pack)
    emit('close')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '打包失败')
  } finally {
    submitting.value = false
  }
}

async function handleSaveLocal(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const pack = await assemblePack(true)
    await modHubStore.installModPack(pack, props.nodes)
    message.success(`已保存并启用「${pack.name}」`)
    emit('created', pack)
    emit('close')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.builder-mask {
  position: fixed;
  inset: 0;
  z-index: 3150;
  background: rgba(15, 15, 14, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.builder-dialog {
  width: 100%;
  max-width: 680px;
  max-height: 86vh;
  background: var(--app-surface);
  border: 1px solid var(--app-border-strong);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.builder-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--app-border);
}

.builder-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.builder-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-text-muted);
}

.builder-sub code,
.foot-hint code {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--app-surface-subtle);
}

.builder-close {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--app-text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.builder-close:hover {
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
}

.builder-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 92px 1fr 1fr;
  gap: 10px;
}

.field-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.field-input,
.field-textarea,
.picker-search {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  color: var(--app-text-primary);
  font-size: 13.5px;
  padding: 8px 10px;
  font-family: inherit;
  outline: none;
}

.field-input:focus,
.field-textarea:focus,
.picker-search:focus {
  border-color: var(--color-brand);
}

.node-picker-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.picker-search {
  width: 190px;
  padding: 5px 10px;
  font-size: 12.5px;
}

.picker-list {
  max-height: 190px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface-subtle);
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.picker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 13px;
  color: var(--app-text-primary);
}

.picker-row:hover {
  background: var(--app-surface);
}

.picker-row.is-checked {
  background: var(--color-brand-light);
}

.picker-node-name {
  font-weight: 500;
}

.picker-node-key {
  font-size: 11.5px;
  font-family: var(--font-mono);
  color: var(--app-text-muted);
}

.edited-pill {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-warning-light);
  color: var(--color-warning);
  font-weight: 600;
}

.showcase-details {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--app-surface-subtle);
}

.showcase-summary {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
  cursor: pointer;
}

.showcase-fields {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.showcase-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.builder-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 22px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
}

.foot-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  max-width: 340px;
  line-height: 1.45;
}

.foot-btns {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.builder-btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface);
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.builder-btn.is-primary {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: var(--app-text-inverse);
}

.builder-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr 1fr;
  }
  .showcase-pair {
    grid-template-columns: 1fr;
  }
}
</style>
