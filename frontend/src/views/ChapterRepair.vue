<template>
  <n-spin :show="pageLoading" class="repair-spin" description="加载中…">
  <div class="chapter-repair">
    <!-- 顶栏 -->
    <header class="repair-header">
      <n-space align="center" :wrap="false">
        <n-button quaternary round @click="goBack">
          <template #icon><span class="ico-back">←</span></template>
          工作台
        </n-button>
        <n-divider vertical />
        <h2 class="repair-heading">章节修复</h2>
      </n-space>

      <n-space :size="8" :wrap="false">
        <n-input-number
          v-model:value="threshold"
          :min="500"
          :max="20000"
          :step="500"
          size="small"
          placeholder="字数阈值"
          style="width: 120px"
        />
        <n-button type="primary" size="small" :loading="scanning" @click="scan">
          扫描短章节
        </n-button>
        <n-button
          type="warning"
          size="small"
          :loading="batchExpanding"
          :disabled="!scanResult || scanResult.short_chapters.length === 0"
          @click="oneClickRepair"
        >
          一键审查续写
        </n-button>
      </n-space>
    </header>

    <!-- 统计栏 -->
    <div v-if="scanResult" class="repair-stats">
      <n-space>
        <n-statistic label="总章节" :value="scanResult.total_chapters" />
        <n-statistic label="严重 (<1000字)" :value="scanResult.summary.critical">
          <template #prefix>
            <n-tag type="error" size="small">严重</n-tag>
          </template>
        </n-statistic>
        <n-statistic label="警告 (<2500字)" :value="scanResult.summary.warning">
          <template #prefix>
            <n-tag type="warning" size="small">警告</n-tag>
          </template>
        </n-statistic>
        <n-statistic label="提示 (<阈值)" :value="scanResult.summary.info">
          <template #prefix>
            <n-tag type="info" size="small">提示</n-tag>
          </template>
        </n-statistic>
      </n-space>
    </div>

    <!-- 无数据 -->
    <n-empty v-if="scanResult && scanResult.short_chapters.length === 0" description="所有章节字数均达标" style="margin-top: 40px" />

    <!-- 主体：表格 + 详情 -->
    <div v-if="scanResult && scanResult.short_chapters.length > 0" class="repair-body">
      <n-split direction="horizontal" :default-size="0.45" :min="0.3" :max="0.7">
        <template #1>
          <!-- 左侧：章节表格 -->
          <div class="repair-table-area">
            <n-data-table
              :columns="columns"
              :data="scanResult.short_chapters"
              :row-class-name="rowClassName"
              :row-props="rowProps"
              :checked-row-keys="selectedRows"
              @update:checked-row-keys="onCheckedRowKeysChange"
              :row-key="(row: ShortChapterDTO) => row.chapter_number"
              :scrollbar-props="{ style: { maxHeight: 'calc(100vh - 280px)' } }"
              max-height="calc(100vh - 280px)"
              size="small"
            />
          </div>
        </template>
        <template #2>
          <!-- 右侧：详情 + 扩写 -->
          <div class="repair-detail-area" v-if="selectedChapter">
            <n-tabs type="segment" v-model:value="detailTab">
              <n-tab-pane name="preview" tab="当前内容">
                <n-scrollbar style="max-height: calc(100vh - 380px)">
                  <div class="content-preview">{{ fullContent || selectedChapter.content_preview }}</div>
                </n-scrollbar>
              </n-tab-pane>
              <n-tab-pane name="expanded" tab="扩写结果">
                <n-scrollbar style="max-height: calc(100vh - 380px)">
                  <div class="content-expanded" v-if="expandedContent">{{ expandedContent }}</div>
                  <n-empty v-else description="点击「扩写此章」开始" style="margin-top: 40px" />
                </n-scrollbar>
              </n-tab-pane>
              <n-tab-pane name="diff" tab="对比">
                <n-scrollbar style="max-height: calc(100vh - 380px)">
                  <div class="diff-area" v-if="expandedContent">
                    <div class="diff-before">
                      <h4>修复前 ({{ selectedChapter.word_count }} 字)</h4>
                      <pre>{{ fullContent || selectedChapter.content_preview }}</pre>
                    </div>
                    <div class="diff-after">
                      <h4>修复后 ({{ expandedWordCount }} 字)</h4>
                      <pre>{{ expandedContent }}</pre>
                    </div>
                  </div>
                  <n-empty v-else description="扩写后可在此对比" style="margin-top: 40px" />
                </n-scrollbar>
              </n-tab-pane>
            </n-tabs>

            <!-- 操作栏 -->
            <div class="repair-actions">
              <n-space align="center">
                <n-text>目标字数：</n-text>
                <n-input-number
                  v-model:value="targetWords"
                  :min="2000"
                  :max="20000"
                  :step="500"
                  size="small"
                  style="width: 120px"
                />
                <n-button
                  type="primary"
                  size="small"
                  :loading="expanding"
                  @click="expandSelected"
                >
                  扩写此章
                </n-button>
                <n-button
                  size="small"
                  @click="selectAll"
                >
                  全选 ({{ scanResult?.short_chapters.length || 0 }})
                </n-button>
                <n-button
                  size="small"
                  :loading="batchExpanding"
                  :disabled="selectedRows.length === 0"
                  @click="batchExpand"
                >
                  批量扩写选中 ({{ selectedRows.length }})
                </n-button>
                <n-button
                  v-if="expandedContent"
                  type="success"
                  size="small"
                  @click="goToChapter"
                >
                  查看章节
                </n-button>
              </n-space>
            </div>
          </div>
          <div v-else class="repair-detail-empty">
            <n-empty description="选择左侧章节查看详情" />
          </div>
        </template>
      </n-split>
    </div>

    <!-- 批量进度弹窗 -->
    <n-modal v-model:show="showBatchProgress" :closable="false" :mask-closable="false">
      <n-card title="批量扩写进度" style="width: 500px">
        <n-space vertical>
          <n-progress
            type="line"
            :percentage="batchProgressPercent"
            :indicator-placement="'inside'"
          />
          <n-text>{{ batchProgressText }}</n-text>
          <n-text depth="3" v-if="currentBatchChapter">
            正在扩写第 {{ currentBatchChapter }} 章...
          </n-text>
        </n-space>
        <template #action>
          <n-button size="small" @click="cancelBatch">取消</n-button>
        </template>
      </n-card>
    </n-modal>
  </div>
  </n-spin>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, NButton, NTag } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { novelApi } from '../api/novel'
import {
  chapterRepairApi,
  consumeExpandChapterStream,
  consumeBatchExpandStream,
} from '../api/chapterRepair'
import type { ShortChapterDTO, ChapterRepairScanResult } from '../api/chapterRepair'
import { chapterApi } from '../api/chapter'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const slug = route.params.slug as string

// ── 状态 ──

const pageLoading = ref(true)
const scanning = ref(false)
const threshold = ref(4000)
const scanResult = ref<ChapterRepairScanResult | null>(null)
const selectedChapter = ref<ShortChapterDTO | null>(null)
const selectedRows = ref<number[]>([])
const detailTab = ref('preview')

const fullContent = ref('')
const targetWords = ref(4000)
const expanding = ref(false)
const expandedContent = ref('')
const expandedWordCount = ref(0)

const showBatchProgress = ref(false)
const batchExpanding = ref(false)
const batchProgressPercent = ref(0)
const batchProgressText = ref('')
const currentBatchChapter = ref<number | null>(null)
let batchAbortController: AbortController | null = null

let novelId = ''

// ── 表格列 ──

const columns: DataTableColumns<ShortChapterDTO> = [
  {
    type: 'selection',
  },
  {
    title: '章节',
    key: 'chapter_number',
    width: 70,
    sorter: (a, b) => a.chapter_number - b.chapter_number,
    render: (row) => h('span', { style: 'font-weight: 600' }, `第${row.chapter_number}章`),
  },
  {
    title: '标题',
    key: 'title',
    ellipsis: { tooltip: true },
  },
  {
    title: '字数',
    key: 'word_count',
    width: 80,
    sorter: (a, b) => a.word_count - b.word_count,
    render: (row) => {
      const type = row.severity === 'critical' ? 'error' : row.severity === 'warning' ? 'warning' : 'info'
      return h(NTag, { type, size: 'small', round: true }, () => row.word_count)
    },
  },
  {
    title: '严重程度',
    key: 'severity',
    width: 90,
    render: (row) => {
      const map = {
        critical: { type: 'error' as const, label: '严重' },
        warning: { type: 'warning' as const, label: '警告' },
        info: { type: 'info' as const, label: '提示' },
      }
      const { type, label } = map[row.severity] || map.info
      return h(NTag, { type, size: 'small' }, () => label)
    },
  },
  {
    title: '状态',
    key: 'status',
    width: 70,
    render: (row) => {
      const map: Record<string, string> = { draft: '草稿', reviewing: '审阅中', completed: '已完成' }
      return map[row.status] || row.status
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 80,
    render: (row) =>
      h(
        NButton,
        {
          size: 'tiny',
          type: 'primary',
          secondary: true,
          onClick: (e: Event) => {
            e.stopPropagation()
            selectChapter(row)
          },
        },
        () => '查看'
      ),
  },
]

const rowClassName = (row: ShortChapterDTO) => {
  if (selectedChapter.value?.chapter_number === row.chapter_number) return 'row-selected'
  return ''
}

const rowProps = (row: ShortChapterDTO) => ({
  style: 'cursor: pointer',
  onClick: () => selectChapter(row),
})

function onCheckedRowKeysChange(keys: Array<string | number>) {
  selectedRows.value = keys as number[]
}

// ── 操作 ──

async function loadNovelId() {
  try {
    const novel = await novelApi.getNovel(slug)
    novelId = novel.id
  } catch {
    message.error('加载小说信息失败')
  }
}

async function scan() {
  if (!novelId) return
  scanning.value = true
  try {
    scanResult.value = await chapterRepairApi.scanShortChapters(novelId, threshold.value)
    selectedChapter.value = null
    expandedContent.value = ''
    fullContent.value = ''
    message.success(`扫描完成，发现 ${scanResult.value.short_chapters.length} 个短章节`)
  } catch (e: unknown) {
    message.error(`扫描失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    scanning.value = false
  }
}

async function selectChapter(ch: ShortChapterDTO) {
  selectedChapter.value = ch
  expandedContent.value = ''
  expandedWordCount.value = 0
  detailTab.value = 'preview'

  // 加载完整内容
  try {
    const full = await chapterApi.getChapter(novelId, ch.chapter_number)
    fullContent.value = full.content || ''
  } catch {
    fullContent.value = ch.content_preview
  }
}

async function expandSelected() {
  if (!selectedChapter.value || !novelId) return
  expanding.value = true
  expandedContent.value = ''
  expandedWordCount.value = 0
  detailTab.value = 'expanded'

  try {
    await consumeExpandChapterStream(
      novelId,
      selectedChapter.value.chapter_number,
      targetWords.value,
      {
        onChunk: (text) => {
          expandedContent.value += text
        },
        onDone: (result) => {
          expandedContent.value = result.content
          expandedWordCount.value = result.word_count
          message.success(`扩写完成: ${result.word_count} 字`)
          // 刷新表格字数
          refreshChapterInTable(selectedChapter.value!.chapter_number, result.word_count)
        },
        onError: (msg) => {
          message.error(`扩写失败: ${msg}`)
        },
      }
    )
  } catch (e: unknown) {
    message.error(`扩写异常: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    expanding.value = false
  }
}

async function batchExpand() {
  if (selectedRows.value.length === 0 || !novelId) return
  batchExpanding.value = true
  showBatchProgress.value = true
  batchProgressPercent.value = 0
  batchProgressText.value = `准备扩写 ${selectedRows.value.length} 个章节...`
  currentBatchChapter.value = null
  batchAbortController = new AbortController()

  const total = selectedRows.value.length
  let done = 0

  try {
    await consumeBatchExpandStream(
      novelId,
      [...selectedRows.value].sort((a, b) => a - b),
      targetWords.value,
      {
        signal: batchAbortController.signal,
        onChapterStart: (chNum, idx) => {
          currentBatchChapter.value = chNum
          batchProgressText.value = `正在扩写第 ${chNum} 章 (${idx}/${total})`
        },
        onChunk: (text, chNum) => {
          if (chNum === selectedChapter.value?.chapter_number) {
            expandedContent.value += text
          }
        },
        onChapterDone: (chNum, idx) => {
          done++
          batchProgressPercent.value = Math.round((done / total) * 100)
          refreshChapterInTable(chNum, 0) // 刷新字数需要重新扫描
        },
        onDone: () => {
          batchProgressPercent.value = 100
          batchProgressText.value = '全部扩写完成'
          message.success(`批量扩写完成: ${done} 个章节`)
          // 重新扫描以刷新字数
          scan()
        },
        onError: (msg) => {
          message.error(`批量扩写出错: ${msg}`)
        },
      }
    )
  } catch (e: unknown) {
    if (!(e instanceof Error && e.name === 'AbortError')) {
      message.error(`批量扩写异常: ${e instanceof Error ? e.message : String(e)}`)
    }
  } finally {
    batchExpanding.value = false
    showBatchProgress.value = false
    currentBatchChapter.value = null
    batchAbortController = null
  }
}

function cancelBatch() {
  batchAbortController?.abort()
  showBatchProgress.value = false
}

function selectAll() {
  if (!scanResult.value) return
  if (selectedRows.value.length === scanResult.value.short_chapters.length) {
    selectedRows.value = []
  } else {
    selectedRows.value = scanResult.value.short_chapters.map((c) => c.chapter_number)
  }
}

async function oneClickRepair() {
  if (!novelId) return
  // 先扫描
  if (!scanResult.value) {
    await scan()
  }
  if (!scanResult.value || scanResult.value.short_chapters.length === 0) {
    message.info('没有需要修复的章节')
    return
  }
  // 全选并开始批量扩写
  selectedRows.value = scanResult.value.short_chapters.map((c) => c.chapter_number)
  await batchExpand()
}

function refreshChapterInTable(chapterNumber: number, newWordCount: number) {
  if (!scanResult.value) return
  const ch = scanResult.value.short_chapters.find((c) => c.chapter_number === chapterNumber)
  if (ch && newWordCount > 0) {
    ch.word_count = newWordCount
    ch.severity = newWordCount < 1000 ? 'critical' : newWordCount < 2500 ? 'warning' : 'info'
  }
}

function goToChapter() {
  if (selectedChapter.value) {
    router.push(`/book/${slug}/chapter/${selectedChapter.value.chapter_number}`)
  }
}

function goBack() {
  router.push(`/book/${slug}/workbench`)
}

// ── 初始化 ──

onMounted(async () => {
  await loadNovelId()
  pageLoading.value = false
  if (novelId) {
    await scan()
  }
})
</script>

<style scoped>
.chapter-repair {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px 16px;
  gap: 12px;
}

.repair-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.repair-heading {
  margin: 0;
  font-size: 18px;
}

.repair-stats {
  flex-shrink: 0;
  padding: 8px 0;
}

.repair-body {
  flex: 1;
  min-height: 0;
}

.repair-table-area {
  padding-right: 8px;
}

.repair-detail-area {
  padding-left: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repair-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.content-preview,
.content-expanded {
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 12px;
}

.repair-actions {
  flex-shrink: 0;
  padding: 8px 0;
  border-top: 1px solid var(--n-border-color);
}

.diff-area {
  display: flex;
  gap: 16px;
  padding: 12px;
}

.diff-area > div {
  flex: 1;
}

.diff-area h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.diff-area pre {
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow-y: auto;
  background: var(--n-color);
  padding: 8px;
  border-radius: 4px;
}

.ico-back {
  font-size: 16px;
}

:deep(.row-selected) {
  background-color: var(--n-color-target) !important;
}

.repair-spin {
  height: 100%;
}
</style>
