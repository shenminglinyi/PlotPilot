<template>
  <div class="vd-panel">
    <div class="vd-head">
      <span class="vd-title">版本历史</span>
      <n-button size="tiny" :loading="loadingVersions" @click="fetchVersions">
        {{ versions.length ? '刷新' : '加载版本' }}
      </n-button>
    </div>

    <template v-if="loadingVersions && !versions.length">
      <div class="vd-loading">
        <n-spin size="small" />
        <n-text depth="3" style="margin-left: 8px">加载中…</n-text>
      </div>
    </template>

    <template v-else-if="versions.length">
      <div class="vd-body">
        <div class="vd-sidebar">
          <div
            v-for="v in versions"
            :key="v.version_id"
            class="vd-version-item"
            :class="{
              'vd-version-item--selected': selectedVersionId === v.version_id,
              'vd-version-item--compare': compareVersionId === v.version_id,
            }"
            @click="selectVersion(v)"
          >
            <div class="vd-version-time">{{ formatTime(v.created_at) }}</div>
            <div v-if="v.summary" class="vd-version-summary">{{ v.summary }}</div>
            <div class="vd-version-actions">
              <n-button
                size="tiny"
                :type="compareVersionId === v.version_id ? 'warning' : 'default'"
                @click.stop="toggleCompare(v.version_id)"
              >
                {{ compareVersionId === v.version_id ? '取消对比' : '对比' }}
              </n-button>
            </div>
          </div>
        </div>

        <div class="vd-main">
          <template v-if="diffResult">
            <div class="vd-diff-head">
              <n-text strong>差异对比</n-text>
              <n-space :size="8" align="center">
                <n-tag size="small" type="success" round>新增 {{ diffResult.additions.length }}</n-tag>
                <n-tag size="small" type="error" round>删除 {{ diffResult.deletions.length }}</n-tag>
              </n-space>
            </div>
            <n-scrollbar class="vd-diff-scroll">
              <div class="vd-diff-content">
                <div
                  v-for="(line, i) in diffResult.deletions"
                  :key="'d-' + i"
                  class="vd-diff-line vd-diff-line--del"
                >
                  <span class="vd-diff-marker">-</span>
                  <span>{{ line }}</span>
                </div>
                <div
                  v-for="(line, i) in diffResult.additions"
                  :key="'a-' + i"
                  class="vd-diff-line vd-diff-line--add"
                >
                  <span class="vd-diff-marker">+</span>
                  <span>{{ line }}</span>
                </div>
              </div>
            </n-scrollbar>
          </template>

          <template v-else-if="selectedVersionId && compareVersionId">
            <div class="vd-diff-head">
              <n-text depth="3">点击「加载差异」查看对比</n-text>
              <n-button size="tiny" type="primary" :loading="loadingDiff" @click="fetchDiff">
                加载差异
              </n-button>
            </div>
          </template>

          <template v-else-if="selectedVersionId">
            <div class="vd-diff-head">
              <n-text depth="3">请选择第二个版本进行对比</n-text>
            </div>
          </template>

          <n-empty v-else description="选择版本查看历史" size="small" class="vd-empty" />
        </div>
      </div>

      <div v-if="selectedVersionId" class="vd-footer">
        <n-button
          type="warning"
          size="small"
          :loading="rollingBack"
          @click="showRollbackConfirm = true"
        >
          回滚到此版本
        </n-button>
      </div>
    </template>

    <n-empty v-else description="暂无版本记录" size="small" class="vd-empty" />

    <n-modal
      v-model:show="showRollbackConfirm"
      preset="dialog"
      title="确认回滚"
      content="回滚将保存当前内容为新版本快照，然后恢复选中版本的内容。确认继续？"
      positive-text="确认回滚"
      negative-text="取消"
      type="warning"
      @positive-click="handleRollback"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { chapterVersionApi } from '../../api/chapterVersion'
import type { VersionItem, DiffResponse } from '../../api/chapterVersion'

interface Props {
  slug: string
  chapterNumber: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{ rolledBack: [] }>()

const message = useMessage()

const versions = ref<VersionItem[]>([])
const loadingVersions = ref(false)
const selectedVersionId = ref<string | null>(null)
const compareVersionId = ref<string | null>(null)
const diffResult = ref<DiffResponse | null>(null)
const loadingDiff = ref(false)
const rollingBack = ref(false)
const showRollbackConfirm = ref(false)

watch(
  () => [props.slug, props.chapterNumber],
  () => {
    versions.value = []
    selectedVersionId.value = null
    compareVersionId.value = null
    diffResult.value = null
  },
)

async function fetchVersions() {
  if (!props.slug || props.chapterNumber == null) return
  loadingVersions.value = true
  try {
    const res = await chapterVersionApi.listVersions(props.slug, props.chapterNumber)
    versions.value = res.versions
  } catch {
    message.error('加载版本列表失败')
  } finally {
    loadingVersions.value = false
  }
}

function selectVersion(v: VersionItem) {
  if (selectedVersionId.value === v.version_id) {
    selectedVersionId.value = null
    diffResult.value = null
    return
  }
  if (selectedVersionId.value && compareVersionId.value) {
    compareVersionId.value = null
    diffResult.value = null
  }
  selectedVersionId.value = v.version_id
}

function toggleCompare(versionId: string) {
  if (compareVersionId.value === versionId) {
    compareVersionId.value = null
    diffResult.value = null
  } else {
    compareVersionId.value = versionId
    diffResult.value = null
  }
}

async function fetchDiff() {
  if (!props.slug || props.chapterNumber == null) return
  if (!selectedVersionId.value || !compareVersionId.value) return
  loadingDiff.value = true
  try {
    diffResult.value = await chapterVersionApi.diff(
      props.slug,
      props.chapterNumber,
      selectedVersionId.value,
      compareVersionId.value,
    )
  } catch {
    message.error('加载差异失败')
  } finally {
    loadingDiff.value = false
  }
}

async function handleRollback() {
  if (!props.slug || props.chapterNumber == null || !selectedVersionId.value) return
  rollingBack.value = true
  try {
    await chapterVersionApi.rollback(props.slug, props.chapterNumber, selectedVersionId.value)
    message.success('回滚成功')
    emit('rolledBack')
    await fetchVersions()
    selectedVersionId.value = null
    compareVersionId.value = null
    diffResult.value = null
  } catch {
    message.error('回滚失败')
  } finally {
    rollingBack.value = false
  }
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}
</script>

<style scoped>
.vd-panel {
  border: 1px solid var(--aitext-split-border, #e0e0e6);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--aitext-panel-muted, rgba(0, 0, 0, 0.02));
  max-height: min(70vh, 640px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.vd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.vd-title {
  font-weight: 600;
  font-size: 14px;
}

.vd-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}

.vd-body {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.vd-sidebar {
  width: 200px;
  flex-shrink: 0;
  overflow-y: auto;
  border-right: 1px solid var(--aitext-split-border, #e0e0e6);
  padding-right: 8px;
}

.vd-version-item {
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 4px;
}

.vd-version-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.vd-version-item--selected {
  background: rgba(24, 160, 88, 0.1);
  border: 1px solid rgba(24, 160, 88, 0.3);
}

.vd-version-item--compare {
  background: rgba(240, 160, 32, 0.1);
  border: 1px solid rgba(240, 160, 32, 0.3);
}

.vd-version-time {
  font-size: 12px;
  font-weight: 500;
  color: var(--n-text-color);
}

.vd-version-summary {
  font-size: 11px;
  color: var(--n-text-color-3);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vd-version-actions {
  margin-top: 4px;
}

.vd-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.vd-diff-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.vd-diff-scroll {
  flex: 1;
  min-height: 0;
}

.vd-diff-content {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  line-height: 1.6;
}

.vd-diff-line {
  padding: 1px 8px;
  border-radius: 2px;
}

.vd-diff-line--add {
  background: rgba(24, 160, 88, 0.12);
  color: #18a058;
}

.vd-diff-line--del {
  background: rgba(208, 48, 80, 0.12);
  color: #d03050;
}

.vd-diff-marker {
  display: inline-block;
  width: 16px;
  font-weight: 600;
  user-select: none;
}

.vd-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--aitext-split-border, #e0e0e6);
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.vd-empty {
  padding: 24px 0;
}
</style>
