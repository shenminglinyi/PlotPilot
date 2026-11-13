<template>
  <div class="mod-hub" :class="{ 'is-fullpage': fullPage }">
    <!-- 顶栏：主视图切换 + 模组打包工坊 + 搜索框 -->
    <div class="hub-topbar">
      <nav class="hub-nav-pills" role="tablist" aria-label="模组中心视图">
        <button
          type="button"
          role="tab"
          class="hub-pill"
          :class="{ 'is-active': mainTab === 'discover' }"
          :aria-selected="mainTab === 'discover'"
          @click="switchMainTab('discover')"
        >
          发现
        </button>
        <button
          type="button"
          role="tab"
          class="hub-pill"
          :class="{ 'is-active': mainTab === 'installed' }"
          :aria-selected="mainTab === 'installed'"
          @click="switchMainTab('installed')"
        >
          已安装
          <span class="pill-count numeric">{{ modHubStore.installedCount }}</span>
        </button>
        <button
          type="button"
          role="tab"
          class="hub-pill"
          :class="{ 'is-active': mainTab === 'nodes' }"
          :aria-selected="mainTab === 'nodes'"
          @click="switchMainTab('nodes')"
        >
          内置内核
          <span class="pill-count numeric">{{ stats?.total_nodes || allNodes.length || 0 }}</span>
        </button>
        <button
          type="button"
          role="tab"
          class="hub-pill"
          :class="{ 'is-active': mainTab === 'anti-ai' }"
          :aria-selected="mainTab === 'anti-ai'"
          @click="switchMainTab('anti-ai')"
        >
          反 AI 质检
        </button>
      </nav>

      <div class="hub-topbar-right">
        <button
          type="button"
          class="hub-ghost-btn"
          @click="showBuilderModal = true"
        >
          打包制作模组
        </button>

        <template v-if="mainTab === 'nodes'">
          <button type="button" class="hub-ghost-btn" @click="handleExportJson">
            导出备份
          </button>
          <button type="button" class="hub-ghost-btn" @click="showImportModal = true">
            导入备份
          </button>
          <button type="button" class="hub-ghost-btn is-accent" @click="showCreateModal = true">
            新建节点
          </button>
        </template>

        <div v-if="mainTab !== 'anti-ai'" class="hub-search">
          <svg viewBox="0 0 20 20" fill="none" class="search-svg" aria-hidden="true">
            <circle cx="9" cy="9" r="5.6" stroke="currentColor" stroke-width="1.6" />
            <path d="M13.4 13.4 17 17" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            class="search-field"
            :placeholder="searchPlaceholder"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="search-clear"
            aria-label="清空搜索"
            @click="searchQuery = ''"
          >
            ×
          </button>
        </div>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════
         1. 发现（Discover）：墨枢精选 + 云端书元 + 社区共享 + 热榜
         ══════════════════════════════════════════════ -->
    <template v-if="mainTab === 'discover'">
      <div class="discover-filter-bar">
        <div v-if="discoverSource !== 'hot'" class="role-chips" role="list">
          <button
            v-for="cat in MOD_ROLE_CATEGORIES"
            :key="cat.key"
            type="button"
            class="role-chip"
            :class="{ 'is-active': activeRole === cat.key }"
            :title="cat.shortHint"
            @click="activeRole = cat.key"
          >
            {{ cat.label }}
            <span class="chip-num numeric">{{ roleCounts[cat.key] ?? 0 }}</span>
          </button>
        </div>
        <div v-else class="hot-hint-text">
          实时追踪主流阅读平台在读风向与高频题材热词
        </div>

        <div class="source-segmented" role="group" aria-label="数据来源筛选">
          <button
            v-for="src in DISCOVER_SOURCES"
            :key="src.key"
            type="button"
            class="source-btn"
            :class="{ 'is-active': discoverSource === src.key }"
            @click="selectDiscoverSource(src.key)"
          >
            {{ src.label }}
          </button>
        </div>
      </div>

      <!-- 云端书元专属题材细分条 -->
      <div
        v-if="discoverSource === 'cloud-official' && cloudGenres.length"
        class="genre-subbar"
      >
        <button
          type="button"
          class="sub-chip"
          :class="{ 'is-active': !selectedCloudGenre }"
          @click="selectCloudGenre('')"
        >
          全部题材
        </button>
        <button
          v-for="g in cloudGenres"
          :key="g.slug"
          type="button"
          class="sub-chip"
          :class="{ 'is-active': selectedCloudGenre === g.slug }"
          @click="selectCloudGenre(g.slug)"
        >
          {{ g.label }}
        </button>
      </div>

      <div class="hub-scroll-body">
        <!-- 非阻断式云端状态提示（仿 Magpie 离线缓存提示，不遮挡本地可用模组） -->
        <div v-if="cloudInlineNotice && discoverSource !== 'curated' && discoverSource !== 'hot'" class="cloud-inline-notice">
          <span>{{ cloudInlineNotice }}</span>
          <button type="button" class="inline-retry-btn" @click="refreshCloudFeeds(true)">
            重试同步
          </button>
        </div>

        <!-- 热榜子视图 -->
        <template v-if="discoverSource === 'hot'">
          <StateBlock
            v-if="hotState.error"
            :error="hotState.error"
            :show-login="true"
            @retry="loadHotFeed(true)"
            @login="$emit('request-cloud-login')"
          />
          <div v-else-if="hotState.loading" class="loading-wrap">
            <n-spin size="medium">正在同步热榜风向…</n-spin>
          </div>
          <div v-else class="hot-panel">
            <div v-if="hotState.terms.length" class="hot-terms-bar">
              <span class="terms-title">近期热词</span>
              <span v-for="t in hotState.terms.slice(0, 12)" :key="t.term" class="term-pill">
                {{ t.term }}
              </span>
            </div>
            <ol v-if="filteredHotItems.length" class="hot-rank-list">
              <li
                v-for="(item, idx) in filteredHotItems"
                :key="`${item.source_key}-${item.rank}-${item.title}`"
                class="hot-rank-row"
              >
                <span class="rank-index numeric" :class="{ 'is-top': idx < 3 }">{{ idx + 1 }}</span>
                <div class="rank-body">
                  <div class="rank-head-line">
                    <strong class="rank-book-title">{{ item.title }}</strong>
                    <span v-if="item.author" class="rank-book-author">{{ item.author }}</span>
                  </div>
                  <p v-if="item.intro" class="rank-book-intro">{{ item.intro }}</p>
                </div>
                <div class="rank-meta-right">
                  <span class="rank-platform">{{ item.source_label }}</span>
                  <div v-if="item.tags?.length" class="rank-tag-row">
                    <span v-for="t in item.tags.slice(0, 2)" :key="t" class="rank-mini-tag">{{ t }}</span>
                  </div>
                </div>
              </li>
            </ol>
            <div v-else class="empty-pane">
              <p class="empty-title">暂无热榜条目</p>
              <p class="empty-sub">登录云端账号后可查看完整多平台聚合热榜。</p>
            </div>
          </div>
        </template>

        <!-- 模组卡片网格 -->
        <template v-else>
          <div v-if="isDiscoverLoading && !displayedPacks.length" class="loading-wrap">
            <n-spin size="medium">正在加载模组目录…</n-spin>
          </div>

          <div v-else-if="displayedPacks.length" class="mod-section">
            <div class="mod-section-head">
              <span class="mod-section-title">{{ activeRoleTitle }}</span>
              <span class="mod-section-count numeric">{{ displayedPacks.length }}</span>
            </div>

            <div class="mod-cards-grid">
              <ModPackCard
                v-for="pack in displayedPacks"
                :key="pack.id"
                :pack="pack"
                :installed="modHubStore.isInstalled(pack.id)"
                :busy="modHubStore.isBusy(pack.id)"
                @select="openPackDetail"
                @install="handleInstallPack"
                @manage="openPackDetail"
              />
            </div>

            <div
              v-if="discoverSource === 'cloud-official' && cloudOfficial.nextCursor"
              class="load-more-row"
            >
              <button
                type="button"
                class="hub-ghost-btn"
                :disabled="cloudOfficial.loading"
                @click="loadCloudOfficial(false)"
              >
                {{ cloudOfficial.loading ? '加载中…' : '加载更多云端书元' }}
              </button>
            </div>
          </div>

          <div v-else class="empty-pane">
            <p class="empty-title">没有找到匹配的叙事模组</p>
            <p class="empty-sub">换个分类关键词，或使用底部地址栏直接从 GitHub 仓库安装。</p>
          </div>
        </template>
      </div>
    </template>

    <!-- ══════════════════════════════════════════════
         2. 已安装（Installed）：查看与一键回滚
         ══════════════════════════════════════════════ -->
    <template v-else-if="mainTab === 'installed'">
      <div class="hub-scroll-body">
        <div v-if="filteredInstalledRecords.length" class="mod-section">
          <div class="installed-banner">
            <span>
              当前已启用 <strong class="numeric">{{ modHubStore.installedCount }}</strong> 个叙事模组。点击任意卡片可查看接管节点或一键卸载回滚。
            </span>
          </div>

          <div class="mod-cards-grid">
            <ModPackCard
              v-for="rec in filteredInstalledRecords"
              :key="rec.pack.id"
              :pack="rec.pack"
              :installed="true"
              :busy="modHubStore.isBusy(rec.pack.id)"
              @select="openPackDetail"
              @install="handleInstallPack"
              @manage="openPackDetail"
            />
          </div>
        </div>

        <div v-else class="empty-pane">
          <p class="empty-title">尚未安装任何扩展模组</p>
          <p class="empty-sub">
            引擎正以出厂默认规则运行。前往「发现」挑选文风去 AI 味、潜台词博弈或毒点审稿模组，一键装入工作流。
          </p>
          <button type="button" class="empty-cta-btn" @click="switchMainTab('discover')">
            浏览精选模组
          </button>
        </div>
      </div>
    </template>

    <!-- ══════════════════════════════════════════════
         3. 内置内核（Engine Nodes · 78）
         ══════════════════════════════════════════════ -->
    <template v-else-if="mainTab === 'nodes'">
      <div v-if="categories.length" class="engine-cat-bar">
        <button
          type="button"
          class="role-chip"
          :class="{ 'is-active': activeCategory === null }"
          @click="activeCategory = null"
        >
          全部环节
          <span class="chip-num numeric">{{ stats?.total_nodes || allNodes.length }}</span>
        </button>
        <button
          v-for="cat in categories"
          :key="cat.key"
          type="button"
          class="role-chip"
          :class="{ 'is-active': activeCategory === cat.key }"
          @click="activeCategory = cat.key"
        >
          {{ stripLeadingSymbol(cat.name) }}
          <span class="chip-num numeric">{{ cat.count }}</span>
        </button>
      </div>

      <div class="hub-scroll-body">
        <div v-if="loading" class="loading-wrap">
          <n-spin size="medium">正在读取引擎内核节点…</n-spin>
        </div>

        <template v-else-if="searchQuery.trim()">
          <div v-if="filteredNodes.length" class="mod-section">
            <div class="mod-section-head">
              <span class="mod-section-title">匹配「{{ searchQuery }}」的内核节点</span>
              <span class="mod-section-count numeric">{{ filteredNodes.length }}</span>
            </div>
            <div class="node-grid">
              <NodeCard
                v-for="node in filteredNodes"
                :key="node.id"
                :node="node"
                @click="openDetail(node)"
              />
            </div>
          </div>
          <n-empty v-else description="没有找到匹配的内核节点" />
        </template>

        <template v-else>
          <div
            v-for="(nodes, catKey) in groupedNodes"
            :key="catKey"
            class="category-section"
          >
            <div class="mod-section-head">
              <span class="mod-section-title">{{ getCategoryName(String(catKey)) }}</span>
              <span class="mod-section-count numeric">{{ nodes.length }}</span>
            </div>
            <div class="node-grid">
              <NodeCard
                v-for="node in nodes"
                :key="node.id"
                :node="node"
                @click="openDetail(node)"
              />
            </div>
          </div>
          <n-empty
            v-if="Object.keys(groupedNodes).length === 0"
            description="暂无内核节点数据"
          />
        </template>
      </div>
    </template>

    <!-- ══════════════════════════════════════════════
         4. 反 AI 质检（Anti-AI Dashboard）
         ══════════════════════════════════════════════ -->
    <div v-else class="hub-scroll-body">
      <Suspense>
        <template #default>
          <AntiAIDashboard />
        </template>
        <template #fallback>
          <div class="loading-wrap">
            <n-spin size="medium">加载反 AI 质检面板…</n-spin>
          </div>
        </template>
      </Suspense>
    </div>

    <!-- ══════════════════════════════════════════════
         底部去中心化安装栏（对标 Magpie：GitHub 仓库 / JSON 链接 / 本机文件）
         ══════════════════════════════════════════════ -->
    <footer v-if="mainTab === 'discover' || mainTab === 'installed'" class="hub-install-dock">
      <span class="dock-label">已有想装的模组？</span>
      <input
        v-model="quickInstallInput"
        type="text"
        class="dock-input"
        placeholder="输入 GitHub 仓库（github:owner/repo）、模组 JSON 直链，或选择本机文件"
        @keydown.enter="handleQuickSourceInstall"
      />
      <input
        ref="localModFileInput"
        type="file"
        accept=".json,application/json"
        class="hidden-file-input"
        @change="onLocalModFilePicked"
      />
      <button
        type="button"
        class="dock-file-btn"
        title="从本机选择 plotpilot-mod.json 文件"
        aria-label="选择本机模组文件"
        @click="triggerLocalFilePicker"
      >
        <svg viewBox="0 0 20 20" fill="none" width="16" height="16" aria-hidden="true">
          <path
            d="M2.8 5.5A1.8 1.8 0 0 1 4.6 3.7h3.5l1.6 1.8h5.7a1.8 1.8 0 0 1 1.8 1.8v7.2a1.8 1.8 0 0 1-1.8 1.8H4.6a1.8 1.8 0 0 1-1.8-1.8V5.5Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <button
        type="button"
        class="dock-submit-btn"
        :disabled="quickInstalling || !quickInstallInput.trim()"
        @click="handleQuickSourceInstall"
      >
        {{ quickInstalling ? '安装中…' : '安装' }}
      </button>
    </footer>

    <!-- 模组详情弹窗（四宫格 + 样章对比 + 接管明细） -->
    <ModPackDetailModal
      :show="Boolean(activePackDetail)"
      :pack="activePackDetail"
      :installed="activePackDetail ? modHubStore.isInstalled(activePackDetail.id) : false"
      :busy="activePackDetail ? modHubStore.isBusy(activePackDetail.id) : false"
      @close="activePackDetail = null"
      @install="handleInstallPack"
      @uninstall="handleUninstallPack"
      @export-pack="handleExportSinglePack"
      @inspect-node="handleInspectEngineNode"
    />

    <!-- 模组打包工坊弹窗 -->
    <ModPackBuilderModal
      :show="showBuilderModal"
      :nodes="allNodes"
      @close="showBuilderModal = false"
      @created="loadData"
    />

    <!-- 内核单节点编辑器弹窗 -->
    <div
      v-if="showDetailModal && selectedNode"
      class="detail-overlay"
      @click.self="closeDetail"
    >
      <div class="detail-modal" :class="{ 'is-entering': detailEntering }">
        <div class="detail-modal-header">
          <div class="dm-header-left">
            <div class="dm-icon-badge">{{ selectedNode.name.charAt(0) }}</div>
            <div class="dm-title-block">
              <h3 class="dm-title">{{ selectedNode.name }}</h3>
              <div class="dm-meta-row">
                <code class="dm-key">{{ selectedNode.node_key }}</code>
                <n-tag
                  :type="selectedNode.is_builtin ? 'info' : 'success'"
                  size="tiny"
                  :bordered="false"
                >
                  {{ selectedNode.is_builtin ? '内置内核' : '自定义' }}
                </n-tag>
              </div>
            </div>
          </div>
          <button type="button" class="dm-close-btn" aria-label="关闭" @click="closeDetail">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="currentColor"
                d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
              />
            </svg>
          </button>
        </div>

        <div class="detail-modal-body">
          <Suspense>
            <template #default>
              <PromptDetailPanel
                v-if="showDetailModal && selectedNode"
                :node-key="selectedNode.node_key"
                @updated="onNodeUpdated"
                @close="closeDetail"
              />
            </template>
            <template #fallback>
              <div class="detail-panel-loading">
                <n-spin size="medium" description="加载编辑器…" />
              </div>
            </template>
          </Suspense>
        </div>
      </div>
    </div>

    <!-- 导入整库备份弹窗 -->
    <n-modal
      v-model:show="showImportModal"
      preset="dialog"
      title="导入提示词备份"
      positive-text="导入"
      negative-text="取消"
      style="max-width: 520px"
      @positive-click="handleImportJson"
    >
      <div class="import-body">
        <p class="import-hint">
          支持导入整库备份 JSON（含 <code>prompts</code> 数组）或单个 <code>plotpilot-mod/v1</code> 模组文件。
        </p>
        <n-upload
          accept=".json,application/json"
          :max="1"
          :show-file-list="true"
          @change="onImportFile"
        >
          <n-button>选择 JSON 文件</n-button>
        </n-upload>
      </div>
    </n-modal>

    <!-- 新建自定义内核节点弹窗 -->
    <n-modal
      v-model:show="showCreateModal"
      preset="dialog"
      title="创建自定义内核节点"
      positive-text="创建"
      negative-text="取消"
      style="max-width: 560px"
      @positive-click="handleCreate"
    >
      <n-form ref="createFormRef" :model="createForm" label-placement="left" label-width="auto">
        <n-form-item label="名称" ruleRequired>
          <n-input v-model:value="createForm.name" placeholder="如：悬疑线索回收检查器" />
        </n-form-item>
        <n-form-item label="标识键">
          <n-input v-model:value="createForm.node_key" placeholder="mystery-clue-checker（留空自动生成）" />
        </n-form-item>
        <n-form-item label="分类">
          <n-select
            v-model:value="createForm.category"
            :options="categoryOptions"
            placeholder="选择环节分类"
          />
        </n-form-item>
        <n-form-item label="System 提示词">
          <n-input
            v-model:value="createForm.system"
            type="textarea"
            :rows="4"
            placeholder="System 角色与规则指令…"
          />
        </n-form-item>
        <n-form-item label="User 模板">
          <n-input
            v-model:value="createForm.user_template"
            type="textarea"
            :rows="3"
            placeholder="User 模板（支持 {context} 等变量）…"
          />
        </n-form-item>
        <n-form-item label="用途说明">
          <n-input v-model:value="createForm.description" placeholder="一句话说明该节点解决什么问题" />
        </n-form-item>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  onUnmounted,
  reactive,
  nextTick,
  watch,
  defineAsyncComponent,
} from 'vue'
import {
  NButton,
  NTag,
  NInput,
  NSpin,
  NEmpty,
  NModal,
  NForm,
  NFormItem,
  NSelect,
  NUpload,
  useMessage,
} from 'naive-ui'
import {
  promptPlazaApi,
  type PromptNode,
  type PromptCategoryInfo,
  type PromptStats,
  type PlazaInitResult,
} from '../../api/llmControl'
import {
  CloudSquareError,
  fetchHotNovels,
  fetchSquareAssets,
  fetchSquareCommunity,
  fetchSquareGenres,
  type HotNovelItem,
  type HotNovelTerm,
  type SquareAsset,
  type SquareCommunityAsset,
  type SquareGenre,
} from '@/api/cloudSquare'
import {
  MOD_ROLE_CATEGORIES,
  type ModRoleCategory,
  type NarrativeModPack,
} from '@/domain/modPack/types'
import { useModHubStore, parseAnyModJson } from '@/stores/modHubStore'
import { formatApiError } from '../../utils/apiError'
import { runtimePerformance } from '../../config/performance'
import ModPackCard from '@/components/modhub/ModPackCard.vue'
import ModPackDetailModal from '@/components/modhub/ModPackDetailModal.vue'
import ModPackBuilderModal from '@/components/modhub/ModPackBuilderModal.vue'
import StateBlock from '@/components/square/SquareStateBlock.vue'
import NodeCard from './promptPlaza/NodeCard.vue'

const PromptDetailPanel = defineAsyncComponent(() => import('./promptPlaza/PromptDetailPanel.vue'))
const AntiAIDashboard = defineAsyncComponent(() => import('./promptPlaza/AntiAIDashboard.vue'))

export type ModHubMainTab = 'discover' | 'installed' | 'nodes' | 'anti-ai'
export type DiscoverSourceKey = 'all' | 'curated' | 'cloud-official' | 'cloud-community' | 'hot'

const DISCOVER_SOURCES: Array<{ key: DiscoverSourceKey; label: string }> = [
  { key: 'all', label: '全部来源' },
  { key: 'curated', label: '墨枢精选' },
  { key: 'cloud-official', label: '云端书元' },
  { key: 'cloud-community', label: '社区共享' },
  { key: 'hot', label: '热榜风向' },
]

const props = withDefaults(
  defineProps<{
    seedStats?: PromptStats | null
    initialTab?: ModHubMainTab
    initialDiscoverSource?: DiscoverSourceKey
    fullPage?: boolean
  }>(),
  {
    seedStats: null,
    initialTab: 'discover',
    initialDiscoverSource: 'all',
    fullPage: false,
  },
)

const emit = defineEmits<{
  (e: 'refresh-stats', payload: PromptStats | null): void
  (e: 'request-cloud-login'): void
}>()

const message = useMessage()
const modHubStore = useModHubStore()

const loading = ref(true)
const searchQuery = ref('')
const mainTab = ref<ModHubMainTab>(props.initialTab)
const activeRole = ref<ModRoleCategory>('all')
const discoverSource = ref<DiscoverSourceKey>(props.initialDiscoverSource)
const activeCategory = ref<string | null>(null)

const selectedNode = ref<PromptNode | null>(null)
const showDetailModal = ref(false)
const detailEntering = ref(false)
let closeDetailTimer: ReturnType<typeof setTimeout> | null = null

const activePackDetail = ref<NarrativeModPack | null>(null)
const showBuilderModal = ref(false)
const showCreateModal = ref(false)
const showImportModal = ref(false)
const importFileText = ref('')

const quickInstallInput = ref('')
const quickInstalling = ref(false)
const localModFileInput = ref<HTMLInputElement | null>(null)

const stats = ref<PromptStats | null>(null)
const categories = ref<PromptCategoryInfo[]>([])
const allNodes = ref<PromptNode[]>([])

// ── 云端数据状态（plotpilot.xyz 代理） ──
const cloudGenres = ref<SquareGenre[]>([])
const selectedCloudGenre = ref('')
const cloudOfficial = reactive<{
  assets: SquareAsset[]
  nextCursor: string
  loading: boolean
  error: CloudSquareError | null
}>({
  assets: [],
  nextCursor: '',
  loading: false,
  error: null,
})

const cloudCommunity = reactive<{
  assets: SquareCommunityAsset[]
  loading: boolean
  error: CloudSquareError | null
}>({
  assets: [],
  loading: false,
  error: null,
})

const hotState = reactive<{
  items: HotNovelItem[]
  terms: HotNovelTerm[]
  loading: boolean
  error: CloudSquareError | null
}>({
  items: [],
  terms: [],
  loading: false,
  error: null,
})

watch(
  () => props.seedStats,
  (s) => {
    if (s) stats.value = s
  },
  { immediate: true },
)

const createFormRef = ref()
const createForm = reactive({
  name: '',
  node_key: '',
  category: 'generation',
  system: '',
  user_template: '',
  description: '',
})

const searchPlaceholder = computed(() => {
  if (mainTab.value === 'nodes') return '搜索内核节点名称、键或描述…'
  if (mainTab.value === 'installed') return '筛选已启用的模组…'
  if (discoverSource.value === 'hot') return '筛选热榜书名或标签…'
  return '搜索模组、文风、题材 Hook 或作者…'
})

// ── 将精选包 + 云端资产统一映射为标准模组卡片 ──
const officialCloudPacks = computed<NarrativeModPack[]>(() =>
  cloudOfficial.assets.map(a => modHubStore.convertOfficialAssetToPack(a)),
)

const communityCloudPacks = computed<NarrativeModPack[]>(() =>
  cloudCommunity.assets.map(c => modHubStore.convertCommunityAssetToPack(c)),
)

const sourceFilteredPool = computed<NarrativeModPack[]>(() => {
  if (discoverSource.value === 'curated') return modHubStore.curatedPacks
  if (discoverSource.value === 'cloud-official') return officialCloudPacks.value
  if (discoverSource.value === 'cloud-community') return communityCloudPacks.value
  if (discoverSource.value === 'hot') return []
  return [
    ...modHubStore.curatedPacks,
    ...officialCloudPacks.value,
    ...communityCloudPacks.value,
  ]
})

const queryFilteredPool = computed<NarrativeModPack[]>(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return sourceFilteredPool.value
  return sourceFilteredPool.value.filter(
    p =>
      p.name.toLowerCase().includes(q) ||
      p.summary.toLowerCase().includes(q) ||
      p.author.toLowerCase().includes(q) ||
      p.roleLabel.toLowerCase().includes(q) ||
      p.tags.some(t => t.toLowerCase().includes(q)),
  )
})

const roleCounts = computed<Record<ModRoleCategory, number>>(() => {
  const counts: Record<ModRoleCategory, number> = {
    all: queryFilteredPool.value.length,
    'style-anti-ai': 0,
    'opening-hook': 0,
    'pacing-plot': 0,
    'dialogue-voice': 0,
    'review-guard': 0,
    worldbuilding: 0,
  }
  for (const p of queryFilteredPool.value) {
    counts[p.roleCategory] = (counts[p.roleCategory] ?? 0) + 1
  }
  return counts
})

const displayedPacks = computed<NarrativeModPack[]>(() => {
  if (activeRole.value === 'all') return queryFilteredPool.value
  return queryFilteredPool.value.filter(p => p.roleCategory === activeRole.value)
})

const activeRoleTitle = computed(() => {
  const found = MOD_ROLE_CATEGORIES.find(c => c.key === activeRole.value)
  if (!found || found.key === 'all') {
    if (discoverSource.value === 'curated') return '墨枢官方精选模组'
    if (discoverSource.value === 'cloud-official') return '云端官方书元库'
    if (discoverSource.value === 'cloud-community') return '社区作者共享'
    return '推荐叙事模组与书元'
  }
  return found.label
})

const isDiscoverLoading = computed(
  () => cloudOfficial.loading || cloudCommunity.loading,
)

const cloudInlineNotice = computed(() => {
  const err = cloudOfficial.error || cloudCommunity.error
  if (!err) return ''
  if (err.kind === 'suspended') return err.message || '云端广场暂未开放服务，当前展示本地精选模组。'
  return `未能同步 plotpilot.xyz 云端目录（${err.message}），当前展示本机可用精选模组。`
})

const filteredHotItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return hotState.items
  return hotState.items.filter(
    i =>
      i.title.toLowerCase().includes(q) ||
      (i.author || '').toLowerCase().includes(q) ||
      (i.tags || []).some(t => t.toLowerCase().includes(q)),
  )
})

const filteredInstalledRecords = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return modHubStore.installedList
  return modHubStore.installedList.filter(
    r =>
      r.pack.name.toLowerCase().includes(q) ||
      r.pack.summary.toLowerCase().includes(q) ||
      r.pack.roleLabel.toLowerCase().includes(q),
  )
})

// ── 内置内核节点计算 ──
const filteredNodes = computed(() => {
  if (!searchQuery.value.trim()) return allNodes.value
  const q = searchQuery.value.toLowerCase().trim()
  return allNodes.value.filter(
    n =>
      n.name.toLowerCase().includes(q) ||
      (n.description || '').toLowerCase().includes(q) ||
      n.node_key.toLowerCase().includes(q) ||
      n.tags.some(t => t.toLowerCase().includes(q)),
  )
})

const groupedNodes = computed<Record<string, PromptNode[]>>(() => {
  const result: Record<string, PromptNode[]> = {}
  for (const node of filteredNodes.value) {
    const cat = activeCategory.value
      ? node.category === activeCategory.value
        ? node.category
        : null
      : node.category
    if (cat) {
      ;(result[cat] ||= []).push(node)
    }
  }
  return result
})

const categoryOptions = computed(() =>
  categories.value.map(c => ({
    label: stripLeadingSymbol(c.name),
    value: c.key,
  })),
)

function stripLeadingSymbol(raw: string): string {
  const parts = raw.trim().split(/\s+/)
  if (parts.length > 1 && parts[0].length <= 3) {
    return parts.slice(1).join(' ')
  }
  return raw
}

function getCategoryName(catKey: string): string {
  const cat = categories.value.find(c => c.key === catKey)
  return cat ? stripLeadingSymbol(cat.name) : catKey
}

function switchMainTab(tab: ModHubMainTab): void {
  mainTab.value = tab
}

function selectDiscoverSource(src: DiscoverSourceKey): void {
  discoverSource.value = src
  if (src === 'cloud-community' && !cloudCommunity.assets.length && !cloudCommunity.loading) {
    void loadCloudCommunity(true)
  } else if (src === 'hot' && !hotState.items.length && !hotState.loading) {
    void loadHotFeed(true)
  }
}

function selectCloudGenre(slug: string): void {
  selectedCloudGenre.value = slug
  void loadCloudOfficial(true)
}

// ── 数据加载 ──
async function loadData(): Promise<void> {
  loading.value = true
  try {
    const res = (await promptPlazaApi.plazaInit()) as unknown as PlazaInitResult
    if (res.stats) stats.value = res.stats
    categories.value = res.categories || []
    const nodesMap = res.nodes_by_category || {}
    allNodes.value = Object.values(nodesMap).flat()
    modHubStore.syncWithBackendNodes(allNodes.value)
  } catch {
    try {
      const [statsRes, catsRes, nodesRes] = await Promise.all([
        promptPlazaApi.getStats().catch(() => null),
        promptPlazaApi.getCategoriesInfo().catch(() => []),
        promptPlazaApi.listNodesByCategory().catch(() => ({})),
      ])
      if (statsRes) stats.value = statsRes as unknown as PromptStats
      categories.value = (catsRes as unknown as PromptCategoryInfo[]) || []
      const nodesMap = (nodesRes as unknown as Record<string, PromptNode[]>) || {}
      allNodes.value = Object.values(nodesMap).flat()
      modHubStore.syncWithBackendNodes(allNodes.value)
    } catch {
      message.error('加载本地提示词内核失败')
    }
  } finally {
    loading.value = false
  }
  emit('refresh-stats', stats.value)
}

async function loadCloudGenres(): Promise<void> {
  try {
    cloudGenres.value = await fetchSquareGenres()
  } catch {
    cloudGenres.value = []
  }
}

async function loadCloudOfficial(reset: boolean): Promise<void> {
  cloudOfficial.loading = true
  cloudOfficial.error = null
  if (reset) {
    cloudOfficial.assets = []
    cloudOfficial.nextCursor = ''
  }
  try {
    const data = await fetchSquareAssets({
      genre: selectedCloudGenre.value || undefined,
      cursor: reset ? undefined : cloudOfficial.nextCursor || undefined,
      limit: 24,
    })
    cloudOfficial.assets = reset ? data.assets : [...cloudOfficial.assets, ...data.assets]
    cloudOfficial.nextCursor = data.next_cursor ?? ''
  } catch (e) {
    cloudOfficial.error =
      e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
  } finally {
    cloudOfficial.loading = false
  }
}

async function loadCloudCommunity(reset: boolean): Promise<void> {
  cloudCommunity.loading = true
  cloudCommunity.error = null
  if (reset) cloudCommunity.assets = []
  try {
    const data = await fetchSquareCommunity({ sort: 'hot', limit: 24 })
    cloudCommunity.assets = data.assets ?? []
  } catch (e) {
    cloudCommunity.error =
      e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
  } finally {
    cloudCommunity.loading = false
  }
}

async function loadHotFeed(reset: boolean): Promise<void> {
  if (!reset && hotState.items.length) return
  hotState.loading = true
  hotState.error = null
  try {
    const feed = await fetchHotNovels(30)
    hotState.items = feed.highlights ?? []
    hotState.terms = feed.terms ?? []
    if (!hotState.items.length) {
      const seen = new Set<string>()
      for (const s of feed.sources ?? []) {
        for (const item of s.items ?? []) {
          const k = `${item.source_key}-${item.title}`
          if (seen.has(k)) continue
          seen.add(k)
          hotState.items.push(item)
        }
      }
    }
  } catch (e) {
    hotState.error =
      e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
  } finally {
    hotState.loading = false
  }
}

async function refreshCloudFeeds(force = false): Promise<void> {
  await Promise.all([
    loadCloudGenres(),
    loadCloudOfficial(true),
    discoverSource.value === 'all' || discoverSource.value === 'cloud-community'
      ? loadCloudCommunity(true)
      : Promise.resolve(),
    discoverSource.value === 'hot' ? loadHotFeed(force) : Promise.resolve(),
  ])
}

// ── 模组安装 / 卸载 / 详情 / 导出 ──
async function openPackDetail(pack: NarrativeModPack): Promise<void> {
  activePackDetail.value = pack
  if (pack.cloudSourceId) {
    const hydrated = await modHubStore.hydrateCloudPackDetail(pack)
    if (activePackDetail.value?.id === pack.id) {
      activePackDetail.value = hydrated
    }
  }
}

async function handleInstallPack(pack: NarrativeModPack): Promise<void> {
  try {
    const record = await modHubStore.installModPack(pack, allNodes.value)
    if (activePackDetail.value?.id === pack.id) {
      activePackDetail.value = record.pack
    }
    message.success(`已启用模组「${record.pack.name}」`)
    await loadData()
  } catch (e) {
    message.error(formatApiError(e, '模组安装失败'))
  }
}

async function handleUninstallPack(pack: NarrativeModPack): Promise<void> {
  try {
    await modHubStore.uninstallModPack(pack.id)
    message.success(`已卸载「${pack.name}」并回滚受影响的引擎节点`)
    activePackDetail.value = null
    await loadData()
  } catch (e) {
    message.error(formatApiError(e, '卸载模组失败'))
  }
}

function handleExportSinglePack(pack: NarrativeModPack): void {
  const manifest = modHubStore.createManifestFromPack(pack)
  const blob = new Blob([JSON.stringify(manifest, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${pack.id}.plotpilot-mod.json`
  a.click()
  URL.revokeObjectURL(url)
  message.success('已导出模组 JSON 清单')
}

function handleInspectEngineNode(nodeKey: string): void {
  activePackDetail.value = null
  selectNodeByKey(nodeKey)
}

// ── 底部快捷安装栏（GitHub / URL / 本机 JSON） ──
async function handleQuickSourceInstall(): Promise<void> {
  const raw = quickInstallInput.value.trim()
  if (!raw) return
  quickInstalling.value = true
  try {
    const record = await modHubStore.installFromSourceInput(raw, allNodes.value)
    quickInstallInput.value = ''
    message.success(`成功安装模组「${record.pack.name}」`)
    await loadData()
    activePackDetail.value = record.pack
  } catch (e) {
    message.error(e instanceof Error ? e.message : '外部模组安装失败')
  } finally {
    quickInstalling.value = false
  }
}

function triggerLocalFilePicker(): void {
  localModFileInput.value?.click()
}

async function onLocalModFilePicked(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  quickInstalling.value = true
  try {
    const record = await modHubStore.installFromLocalFile(file, allNodes.value)
    message.success(`已从本机文件安装「${record.pack.name}」`)
    await loadData()
    activePackDetail.value = record.pack
  } catch (err) {
    message.error(err instanceof Error ? err.message : '读取模组文件失败')
  } finally {
    quickInstalling.value = false
  }
}

// ── 内核节点详情与备份导入导出 ──
function openDetail(node: PromptNode): void {
  if (closeDetailTimer) {
    clearTimeout(closeDetailTimer)
    closeDetailTimer = null
  }
  selectedNode.value = node
  showDetailModal.value = true
  nextTick(() => {
    detailEntering.value = true
  })
}

function closeDetail(): void {
  detailEntering.value = false
  if (closeDetailTimer) clearTimeout(closeDetailTimer)
  closeDetailTimer = setTimeout(() => {
    closeDetailTimer = null
    showDetailModal.value = false
    selectedNode.value = null
  }, runtimePerformance.workbench.promptPlazaCloseAnimationMs)
}

function onNodeUpdated(): void {
  void loadData()
}

async function handleExportJson(): Promise<void> {
  try {
    const res = await promptPlazaApi.exportAll()
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prompts-backup-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出整库备份')
  } catch (e: unknown) {
    const err = e as { message?: string }
    message.error(err?.message || '导出失败')
  }
}

function onImportFile(data: {
  file: { file?: File | null }
  fileList: Array<{ file?: File | null }>
}): void {
  const f = data.file?.file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    importFileText.value = (ev.target?.result as string) || ''
  }
  reader.readAsText(f)
}

async function handleImportJson(): Promise<boolean> {
  if (!importFileText.value.trim()) {
    message.warning('请先选择 JSON 文件')
    return false
  }
  try {
    const parsed = JSON.parse(importFileText.value) as Record<string, unknown>
    if (parsed.schema === 'plotpilot-mod/v1' || Array.isArray(parsed.overrides)) {
      const pack = parseAnyModJson(parsed, '手动导入', 'local')
      await modHubStore.installModPack(pack, allNodes.value)
      message.success(`已安装模组「${pack.name}」`)
      showImportModal.value = false
      importFileText.value = ''
      await loadData()
      return true
    }
    if (!parsed.prompts || !Array.isArray(parsed.prompts)) {
      message.error('JSON 中需包含 prompts 数组或 plotpilot-mod/v1 清单')
      return false
    }
    const result = await promptPlazaApi.importData(
      parsed as Parameters<typeof promptPlazaApi.importData>[0],
    )
    message.success(result.message || '导入完成')
    showImportModal.value = false
    importFileText.value = ''
    await loadData()
    return true
  } catch (e: unknown) {
    message.error(formatApiError(e, '导入失败'))
    return false
  }
}

async function handleCreate(): Promise<boolean> {
  if (!createForm.name.trim()) {
    message.warning('请输入节点名称')
    return false
  }
  try {
    await promptPlazaApi.createNode({
      name: createForm.name,
      node_key: createForm.node_key || undefined,
      category: createForm.category,
      system: createForm.system,
      user_template: createForm.user_template,
      description: createForm.description,
    })
    message.success('节点创建成功')
    showCreateModal.value = false
    Object.assign(createForm, {
      name: '',
      node_key: '',
      category: 'generation',
      system: '',
      user_template: '',
      description: '',
    })
    await loadData()
    return true
  } catch (e: unknown) {
    message.error(formatApiError(e, '创建失败'))
    return false
  }
}

function selectNodeByKey(nodeKey: string): void {
  mainTab.value = 'nodes'
  const node = allNodes.value.find(n => n.node_key === nodeKey)
  if (node) {
    openDetail(node)
  } else {
    searchQuery.value = nodeKey
  }
}

onMounted(() => {
  void loadData()
  void loadCloudGenres()
  void loadCloudOfficial(true)
  void loadCloudCommunity(true)
})

onUnmounted(() => {
  if (closeDetailTimer) {
    clearTimeout(closeDetailTimer)
    closeDetailTimer = null
  }
})

defineExpose({ loadData, selectNodeByKey, refreshCloudFeeds })
</script>

<style scoped>
.mod-hub {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--app-page-bg);
  color: var(--app-text-primary);
}

.mod-hub.is-fullpage {
  flex: 1;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

/* ── 顶栏主视图胶囊条（对标 Magpie：内置 | 发现 | 已安装） ── */
.hub-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 20px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  flex-shrink: 0;
}

.hub-nav-pills {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
}

.hub-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--app-text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

.hub-pill:hover {
  color: var(--app-text-primary);
}

.hub-pill.is-active {
  background: var(--app-surface);
  border-color: var(--app-border);
  color: var(--app-text-primary);
  font-weight: 600;
}

.pill-count {
  font-size: 12px;
  color: var(--app-text-muted);
}

.hub-pill.is-active .pill-count {
  color: var(--color-brand);
}

.hub-topbar-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.hub-ghost-btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.hub-ghost-btn:hover:not(:disabled) {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.hub-ghost-btn.is-accent {
  border-color: var(--color-brand);
  color: var(--color-brand);
  background: var(--color-brand-light);
}

.hub-search {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  width: min(260px, 52vw);
}

.hub-search:focus-within {
  border-color: var(--color-brand);
  background: var(--app-surface);
}

.search-svg {
  width: 15px;
  height: 15px;
  color: var(--app-text-muted);
  flex-shrink: 0;
}

.search-field {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  color: var(--app-text-primary);
  font-size: 13px;
  outline: none;
}

.search-clear {
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

/* ── 二级筛选栏：创作角色芯片 + 来源切换 ── */
.discover-filter-bar,
.engine-cat-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 20px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  flex-shrink: 0;
}

.engine-cat-bar {
  justify-content: flex-start;
  gap: 6px;
}

.role-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.role-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 11px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

.role-chip:hover {
  color: var(--app-text-primary);
  border-color: var(--app-border);
}

.role-chip.is-active {
  background: var(--color-brand-light);
  border-color: color-mix(in srgb, var(--color-brand) 30%, var(--app-border));
  color: var(--color-brand);
  font-weight: 600;
}

.chip-num {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.role-chip.is-active .chip-num {
  color: var(--color-brand);
}

.source-segmented {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
}

.source-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.source-btn:hover {
  color: var(--app-text-primary);
}

.source-btn.is-active {
  background: var(--app-surface);
  color: var(--app-text-primary);
  font-weight: 600;
}

.hot-hint-text {
  font-size: 13px;
  color: var(--app-text-muted);
}

.genre-subbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 20px;
  background: var(--app-surface-subtle);
  border-bottom: 1px solid var(--app-border);
}

.sub-chip {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.sub-chip.is-active {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: var(--app-text-inverse);
}

/* ── 主体滚动区 ── */
.hub-scroll-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 20px 24px;
}

.cloud-inline-notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 9px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  font-size: 13px;
  color: var(--app-text-secondary);
}

.inline-retry-btn {
  border: none;
  background: transparent;
  color: var(--color-brand);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
}

.inline-retry-btn:hover {
  text-decoration: underline;
}

.mod-section,
.category-section {
  margin-bottom: 24px;
}

.mod-section-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}

.mod-section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.mod-section-count {
  font-size: 13px;
  color: var(--app-text-muted);
}

.mod-cards-grid,
.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(296px, 1fr));
  gap: 14px;
}

.load-more-row {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

.installed-banner {
  padding: 11px 14px;
  margin-bottom: 14px;
  border-radius: 10px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  font-size: 13.5px;
  color: var(--app-text-secondary);
}

.empty-pane {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 56px 20px;
  gap: 8px;
}

.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.empty-sub {
  margin: 0;
  font-size: 14px;
  color: var(--app-text-muted);
  max-width: 46ch;
  line-height: 1.6;
}

.empty-cta-btn {
  margin-top: 8px;
  height: 36px;
  padding: 0 18px;
  border-radius: 9px;
  border: 1px solid var(--color-brand);
  background: var(--color-brand);
  color: var(--app-text-inverse);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

/* ── 热榜视图 ── */
.hot-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hot-terms-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}

.terms-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-right: 4px;
}

.term-pill {
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
  font-size: 12px;
}

.hot-rank-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hot-rank-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}

.rank-index {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--app-surface-subtle);
  color: var(--app-text-muted);
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rank-index.is-top {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.rank-body {
  flex: 1;
  min-width: 0;
}

.rank-head-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.rank-book-title {
  font-size: 15px;
  color: var(--app-text-primary);
}

.rank-book-author {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.rank-book-intro {
  margin: 4px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  max-width: 65ch;
}

.rank-meta-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.rank-platform {
  font-size: 12px;
  color: var(--app-text-muted);
}

.rank-tag-row {
  display: flex;
  gap: 4px;
}

.rank-mini-tag {
  font-size: 11.5px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
}

/* ── 底部去中心化安装条（对标 Magpie） ── */
.hub-install-dock {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 20px;
  background: var(--app-surface);
  border-top: 1px solid var(--app-border);
  flex-shrink: 0;
}

.dock-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-secondary);
  white-space: nowrap;
}

.dock-input {
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
  font-size: 13px;
  outline: none;
}

.dock-input:focus {
  border-color: var(--color-brand);
  background: var(--app-surface);
}

.hidden-file-input {
  display: none;
}

.dock-file-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}

.dock-file-btn:hover {
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.dock-submit-btn {
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  border: 1px solid var(--color-brand);
  background: var(--color-brand);
  color: var(--app-text-inverse);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}

.dock-submit-btn:hover:not(:disabled) {
  background: var(--color-brand-hover);
  border-color: var(--color-brand-hover);
}

.dock-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-wrap,
.detail-panel-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56px 20px;
}

/* ── 内核节点详情弹窗（无阴影渐变，克制干净） ── */
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(15, 15, 14, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.detail-modal {
  width: 100%;
  max-width: 880px;
  height: 85vh;
  max-height: 800px;
  background: var(--app-surface);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--app-border-strong);
  transform: scale(0.96);
  opacity: 0;
  transition: transform 0.2s ease, opacity 0.18s ease;
}

.detail-modal.is-entering {
  transform: scale(1);
  opacity: 1;
}

.detail-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 22px 14px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
  flex-shrink: 0;
}

.dm-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.dm-icon-badge {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  color: var(--app-text-primary);
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.dm-title-block {
  min-width: 0;
}

.dm-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dm-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
}

.dm-key {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--app-text-muted);
}

.dm-close-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.dm-close-btn:hover {
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
}

.detail-modal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 22px 22px;
}

.import-body {
  margin-top: 8px;
}

.import-hint {
  font-size: 13.5px;
  color: var(--app-text-secondary);
  margin-bottom: 12px;
  line-height: 1.55;
}

.import-hint code {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--app-surface-subtle);
}

@media (max-width: 640px) {
  .hub-topbar,
  .discover-filter-bar,
  .hub-scroll-body,
  .hub-install-dock {
    padding-left: 16px;
    padding-right: 16px;
  }

  .hub-search {
    width: 100%;
  }

  .hub-install-dock {
    flex-wrap: wrap;
  }

  .dock-label {
    width: 100%;
  }
}
</style>
