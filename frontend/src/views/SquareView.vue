<template>
  <div class="square-view">
    <!-- 顶栏：返回 + 标题 + 云端源 + 会话 -->
    <header class="square-topbar">
      <button type="button" class="square-back" aria-label="返回首页" @click="goHome">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>返回</span>
      </button>

      <div class="square-title-block">
        <h1 class="square-title">线上提示词广场</h1>
        <span class="square-origin">plotpilot.xyz · 经本地内核代理拉取</span>
      </div>

      <div class="square-session">
        <template v-if="session?.logged_in">
          <span class="session-chip is-on" :title="session.username">
            <span class="session-dot" />
            {{ session.display_name || session.username }}
          </span>
          <button type="button" class="session-btn" @click="handleLogout">退出</button>
        </template>
        <template v-else>
          <button type="button" class="session-btn is-login" @click="showLogin = true">登录云端</button>
        </template>
        <button type="button" class="session-btn" :disabled="refreshing" @click="refreshAll">
          {{ refreshing ? '刷新中…' : '刷新' }}
        </button>
      </div>
    </header>

    <!-- Tab 切换 -->
    <nav class="square-tabs" role="tablist">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        role="tab"
        class="square-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        :aria-selected="activeTab === tab.key"
        @click="onTabChange(tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'official' && official.assets.length" class="tab-count">{{ official.assets.length }}</span>
        <span v-else-if="tab.key === 'community' && community.assets.length" class="tab-count">{{ community.assets.length }}</span>
      </button>
    </nav>

    <!-- 主内容区 -->
    <main class="square-body">
      <!-- 管理端斩断：整页静待态（优先于任何 tab） -->
      <StateBlock
        v-if="suspendedError"
        :error="suspendedError"
        @retry="refreshAll"
      />
      <!-- 官方书元 -->
      <section v-else-if="activeTab === 'official'" class="tab-panel">
        <div class="filter-row">
          <div class="genre-chips" role="list">
            <button
              type="button"
              class="genre-chip"
              :class="{ 'is-active': !official.genre }"
              @click="selectGenre('')"
            >全部</button>
            <button
              v-for="g in genres"
              :key="g.slug"
              type="button"
              class="genre-chip"
              :class="{ 'is-active': official.genre === g.slug }"
              :style="{ '--chip-accent': g.accent }"
              @click="selectGenre(g.slug)"
            >
              {{ g.label }}
              <span v-if="g.count" class="chip-count">{{ g.count }}</span>
            </button>
          </div>
          <div class="search-box">
            <svg viewBox="0 0 24 24" fill="none" class="search-icon">
              <circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8"/>
              <path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
            <input
              v-model="officialQuery"
              type="text"
              placeholder="搜索书元 / Hook…"
              @keydown.enter="loadOfficial(true)"
            />
          </div>
        </div>

        <StateBlock
          v-if="official.error"
          :error="official.error"
          @retry="loadOfficial(true)"
        />
        <div v-else-if="official.loading && !official.assets.length" class="cards-grid">
          <div v-for="n in 6" :key="n" class="card-skeleton" />
        </div>
        <div v-else-if="!official.assets.length" class="empty-block">
          <p>没有匹配的书元——换个题材或关键词试试。</p>
        </div>
        <template v-else>
          <div class="cards-grid">
            <button
              v-for="asset in official.assets"
              :key="asset.id"
              type="button"
              class="asset-card"
              @click="openOfficialDetail(asset)"
            >
              <div class="card-zone" :style="{ '--zone-accent': zoneAccent(asset) }">
                <span>{{ asset.zone_label || asset.zone || '书元' }}</span>
                <span v-if="asset.produces_document" class="zone-slot">{{ slotLabel(asset.produces_document) }}</span>
              </div>
              <h3 class="card-title">{{ asset.title }}</h3>
              <p class="card-summary">{{ asset.summary }}</p>
              <div v-if="asset.hook_tags?.length" class="card-tags">
                <span v-for="t in asset.hook_tags.slice(0, 3)" :key="t" class="card-tag">{{ t }}</span>
              </div>
              <div class="card-metrics">
                <span v-if="asset.metrics?.cold_start" class="metric cold" title="尚无真实使用数据">冷启中</span>
                <template v-else>
                  <span class="metric">应用 {{ asset.metrics?.apply_count ?? 0 }}</span>
                  <span class="metric">试用 {{ asset.metrics?.trial_count ?? 0 }}</span>
                  <span v-if="asset.metrics?.successful_run_rate" class="metric">
                    达成 {{ Math.round((asset.metrics.successful_run_rate ?? 0) * 100) }}%
                  </span>
                </template>
              </div>
            </button>
          </div>
          <button
            v-if="official.nextCursor"
            type="button"
            class="load-more"
            :disabled="official.loading"
            @click="loadOfficial(false)"
          >{{ official.loading ? '加载中…' : '加载更多' }}</button>
        </template>
      </section>

      <!-- 社区共享 -->
      <section v-else-if="activeTab === 'community'" class="tab-panel">
        <div class="filter-row">
          <div class="sort-switch" role="tablist" aria-label="排序">
            <button
              v-for="s in COMMUNITY_SORTS"
              :key="s.key"
              type="button"
              class="sort-btn"
              :class="{ 'is-active': community.sort === s.key }"
              @click="selectCommunitySort(s.key)"
            >{{ s.label }}</button>
          </div>
          <div class="search-box">
            <svg viewBox="0 0 24 24" fill="none" class="search-icon">
              <circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8"/>
              <path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
            <input
              v-model="communityQuery"
              type="text"
              placeholder="搜索社区分享…"
              @keydown.enter="loadCommunity(true)"
            />
          </div>
        </div>

        <StateBlock
          v-if="community.error"
          :error="community.error"
          @retry="loadCommunity(true)"
        />
        <div v-else-if="community.loading && !community.assets.length" class="cards-grid">
          <div v-for="n in 4" :key="n" class="card-skeleton" />
        </div>
        <div v-else-if="!community.assets.length" class="empty-block">
          <p>广场上还没有人分享模板。</p>
          <p class="empty-sub">登录 plotpilot.xyz 发布第一支，这里会实时同步。</p>
        </div>
        <div v-else class="cards-grid">
          <button
            v-for="item in community.assets"
            :key="item.id"
            type="button"
            class="asset-card community"
            @click="openCommunityDetail(item)"
          >
            <div class="community-head">
              <span class="author-avatar" :style="{ background: avatarColor(item) }">
                {{ authorInitial(item) }}
              </span>
              <span class="author-name">{{ item.author?.pen_name || item.author?.display_name || '匿名作者' }}</span>
              <span v-if="item.author?.grade_label" class="author-grade">{{ item.author.grade_label }}</span>
              <span v-if="visibilityLabel(item)" class="community-visibility">{{ visibilityLabel(item) }}</span>
            </div>
            <h3 class="card-title">{{ item.asset?.title || item.title || '未命名模板' }}</h3>
            <p class="card-summary">{{ item.asset?.summary || item.summary || item.safe_sample }}</p>
            <div class="card-metrics">
              <span class="metric">妙 {{ item.counters?.like ?? item.counters?.view ?? 0 }}</span>
              <span class="metric">批注 {{ item.counters?.comment ?? 0 }}</span>
              <span class="metric">试用 {{ item.counters?.trial ?? 0 }}</span>
              <span class="metric time">{{ publishTimeLabel(item) }}</span>
            </div>
          </button>
        </div>
      </section>

      <!-- 热榜小说 -->
      <section v-else class="tab-panel">
        <div class="filter-row">
          <div class="genre-chips">
            <button
              type="button"
              class="genre-chip"
              :class="{ 'is-active': !hot.source }"
              @click="selectHotSource('')"
            >全部来源</button>
            <button
              v-for="s in hotSources"
              :key="s"
              type="button"
              class="genre-chip"
              :class="{ 'is-active': hot.source === s }"
              @click="selectHotSource(s)"
            >{{ s }}</button>
          </div>
        </div>

        <StateBlock v-if="hot.error" :error="hot.error" :show-login="true" @retry="loadHot(true)" @login="showLogin = true" />
        <div v-else-if="hot.loading" class="rank-skeleton">
          <div v-for="n in 8" :key="n" class="rank-item rank-item--skeleton" />
        </div>
        <template v-else>
          <div v-if="hotTerms.length" class="hot-terms">
            <span class="terms-label">热词</span>
            <span v-for="t in hotTerms.slice(0, 12)" :key="t.term" class="hot-term">{{ t.term }}</span>
          </div>
          <ol class="rank-list">
            <li
              v-for="(item, idx) in hotItems"
              :key="`${item.source_key}-${item.rank}-${item.title}`"
              class="rank-item"
              :class="{ 'is-top': idx < 3 }"
            >
              <span class="rank-no" :class="`rank-no-${Math.min(idx + 1, 10)}`">{{ idx + 1 }}</span>
              <div class="rank-main">
                <div class="rank-title-row">
                  <span class="rank-title">{{ item.title }}</span>
                  <span v-if="item.author" class="rank-author">{{ item.author }}</span>
                </div>
                <p v-if="item.intro" class="rank-intro">{{ item.intro }}</p>
              </div>
              <div class="rank-side">
                <span class="rank-source">{{ item.source_label }}</span>
                <div v-if="item.tags?.length" class="rank-tags">
                  <span v-for="t in item.tags.slice(0, 2)" :key="t" class="rank-tag">{{ t }}</span>
                </div>
              </div>
            </li>
          </ol>
        </template>
      </section>
    </main>

    <!-- 官方书元详情抽屉 -->
    <n-drawer
      :show="detail.show && detail.kind === 'official'"
      :width="480"
      placement="right"
      :mask-closable="true"
      :close-on-esc="true"
      @update:show="(v: boolean) => detail.show = v"
    >
      <n-drawer-content closable :title="detail.asset?.title || '书元详情'">
        <div v-if="detail.asset" class="detail-body">
          <div class="detail-chips">
            <span v-if="detail.asset.zone_label" class="detail-chip zone">{{ detail.asset.zone_label }}</span>
            <span v-for="g in detail.asset.genre_tags ?? []" :key="g" class="detail-chip">{{ g }}</span>
          </div>
          <p class="detail-summary">{{ detail.asset.summary }}</p>

          <div v-if="detail.asset.variables?.length" class="detail-section">
            <h4>变量（{{ detail.asset.variables.length }}）</h4>
            <div v-for="v in detail.asset.variables" :key="v.key" class="var-row">
              <code class="var-key">{{ v.key }}</code>
              <span class="var-label">{{ v.label }}</span>
              <span v-if="v.required" class="var-required">必填</span>
            </div>
          </div>

          <div v-if="detail.asset.template_text" class="detail-section">
            <h4>模板</h4>
            <pre class="detail-pre">{{ detail.asset.template_text }}</pre>
          </div>
          <div v-else-if="detail.asset.sample_excerpt" class="detail-section">
            <h4>自证样章摘录</h4>
            <pre class="detail-pre">{{ detail.asset.sample_excerpt }}</pre>
          </div>

          <div class="detail-section">
            <h4>使用数据</h4>
            <div class="detail-metrics">
              <div class="dm"><b>{{ detail.asset.metrics?.apply_count ?? 0 }}</b><span>应用</span></div>
              <div class="dm"><b>{{ detail.asset.metrics?.trial_count ?? 0 }}</b><span>试用</span></div>
              <div class="dm"><b>{{ detail.asset.metrics?.remix_count ?? 0 }}</b><span>混搭</span></div>
              <div class="dm">
                <b>{{ detail.asset.metrics?.cold_start ? '—' : Math.round((detail.asset.metrics?.successful_run_rate ?? 0) * 100) + '%' }}</b>
                <span>达成率</span>
              </div>
            </div>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <!-- 社区模板详情抽屉 -->
    <n-drawer
      :show="detail.show && detail.kind === 'community'"
      :width="480"
      placement="right"
      :mask-closable="true"
      :close-on-esc="true"
      @update:show="(v: boolean) => detail.show = v"
    >
      <n-drawer-content closable :title="communityDetailTitle">
        <div v-if="detail.community" class="detail-body">
          <div class="community-head detail-author">
            <span class="author-avatar" :style="{ background: avatarColor(detail.community) }">
              {{ authorInitial(detail.community) }}
            </span>
            <span class="author-name">{{ detail.community.author?.pen_name || detail.community.author?.display_name || '匿名作者' }}</span>
            <span v-if="detail.community.author?.grade_label" class="author-grade">{{ detail.community.author.grade_label }}</span>
          </div>
          <p class="detail-summary">{{ detail.community.asset?.summary || detail.community.summary }}</p>
          <div v-if="detail.community.safe_sample" class="detail-section">
            <h4>安全样例</h4>
            <pre class="detail-pre">{{ detail.community.safe_sample }}</pre>
          </div>
          <div v-if="detail.community.ai_disclosure" class="detail-section">
            <h4>AI 披露</h4>
            <p class="detail-summary">{{ detail.community.ai_disclosure }}</p>
          </div>
          <div class="detail-section">
            <h4>互动数据</h4>
            <div class="detail-metrics">
              <div class="dm"><b>{{ detail.community.counters?.view ?? 0 }}</b><span>浏览</span></div>
              <div class="dm"><b>{{ detail.community.counters?.save ?? 0 }}</b><span>收藏</span></div>
              <div class="dm"><b>{{ detail.community.counters?.trial ?? 0 }}</b><span>试用</span></div>
              <div class="dm"><b>{{ detail.community.counters?.comment ?? 0 }}</b><span>批注</span></div>
            </div>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <!-- 登录弹层 -->
    <n-modal
      v-model:show="showLogin"
      preset="dialog"
      title="登录 plotpilot.xyz"
      positive-text="登录"
      negative-text="取消"
      :loading="loginLoading"
      @positive-click="handleLogin"
    >
      <div class="login-form">
        <p class="login-hint">
          登录后解锁热榜、妙/批注等互动；凭证只存本地内核（服务端 cookie 会话），浏览器零凭证。
        </p>
        <div class="login-field">
          <label>用户名</label>
          <input v-model="loginForm.username" type="text" autocomplete="username" placeholder="用户名" />
        </div>
        <div class="login-field">
          <label>密码</label>
          <input v-model="loginForm.password" type="password" autocomplete="current-password" placeholder="密码" @keydown.enter="handleLogin" />
        </div>
        <p v-if="loginError" class="login-error">{{ loginError }}</p>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NDrawer, NDrawerContent, NModal } from 'naive-ui'
import {
  CloudSquareError,
  fetchCloudSession,
  fetchHotNovels,
  fetchSquareAssets,
  fetchSquareCommunity,
  fetchSquareCommunityDetail,
  fetchSquareGenres,
  fetchSquareAssetDetail,
  loginCloudSession,
  logoutCloudSession,
  sendSquareEvent,
  type CloudSessionStatus,
  type HotNovelItem,
  type HotNovelTerm,
  type SquareAsset,
  type SquareCommunityAsset,
  type SquareGenre,
} from '@/api/cloudSquare'
import StateBlock from '@/components/square/SquareStateBlock.vue'

type TabKey = 'official' | 'community' | 'hot'
type SortKey = 'hot' | 'recent' | 'discussed'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'official', label: '官方书元' },
  { key: 'community', label: '社区共享' },
  { key: 'hot', label: '热榜小说' },
]
const COMMUNITY_SORTS: Array<{ key: SortKey; label: string }> = [
  { key: 'hot', label: '最热' },
  { key: 'recent', label: '最新' },
  { key: 'discussed', label: '最多讨论' },
]

const router = useRouter()

const activeTab = ref<TabKey>('official')
const refreshing = ref(false)
const loadedTabs = new Set<TabKey>(['official'])

// ── 会话 ──
const session = ref<CloudSessionStatus | null>(null)
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

async function handleLogin(): Promise<void> {
  if (!loginForm.username || !loginForm.password) {
    loginError.value = '请输入用户名和密码'
    return
  }
  loginLoading.value = true
  loginError.value = ''
  try {
    session.value = await loginCloudSession(loginForm.username, loginForm.password)
    showLogin.value = false
    loginForm.password = ''
    if (activeTab.value === 'hot') {
      void loadHot(true)
    }
  } catch (e) {
    loginError.value = e instanceof Error ? e.message : '登录失败'
  } finally {
    loginLoading.value = false
  }
}

async function handleLogout(): Promise<void> {
  try {
    await logoutCloudSession()
    session.value = { logged_in: false }
  } catch {
    // 忽略：下次进入会重查
  }
}

// ── 题材（官方书元筛选轴） ──
const genres = ref<SquareGenre[]>([])

async function loadGenres(): Promise<void> {
  try {
    genres.value = await fetchSquareGenres()
  } catch {
    genres.value = []
  }
}

// ── 官方书元 ──
const official = reactive<{
  assets: SquareAsset[]
  nextCursor: string
  loading: boolean
  error: CloudSquareError | null
  genre: string
}>({
  assets: [],
  nextCursor: '',
  loading: false,
  error: null,
  genre: '',
})
const officialQuery = ref('')

async function loadOfficial(reset: boolean): Promise<void> {
  official.loading = true
  official.error = null
  if (reset) {
    official.assets = []
    official.nextCursor = ''
  }
  try {
    const data = await fetchSquareAssets({
      q: officialQuery.value.trim() || undefined,
      genre: official.genre || undefined,
      cursor: reset ? undefined : official.nextCursor || undefined,
    })
    official.assets = reset ? data.assets : [...official.assets, ...data.assets]
    official.nextCursor = data.next_cursor ?? ''
  } catch (e) {
    official.error = e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
  } finally {
    official.loading = false
  }
}

function selectGenre(slug: string): void {
  official.genre = slug
  void loadOfficial(true)
}

// ── 社区共享 ──
const community = reactive<{
  assets: SquareCommunityAsset[]
  loading: boolean
  error: CloudSquareError | null
  sort: SortKey
}>({
  assets: [],
  loading: false,
  error: null,
  sort: 'hot',
})
const communityQuery = ref('')

async function loadCommunity(reset: boolean): Promise<void> {
  community.loading = true
  community.error = null
  if (reset) community.assets = []
  try {
    const data = await fetchSquareCommunity({
      q: communityQuery.value.trim() || undefined,
      sort: community.sort,
    })
    community.assets = data.assets ?? []
  } catch (e) {
    community.error = e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
  } finally {
    community.loading = false
  }
}

function selectCommunitySort(sort: SortKey): void {
  community.sort = sort
  void loadCommunity(true)
}

// ── 热榜 ──
const hot = reactive<{
  items: HotNovelItem[]
  terms: HotNovelTerm[]
  sources: string[]
  loading: boolean
  error: CloudSquareError | null
  source: string
}>({
  items: [],
  terms: [],
  sources: [],
  loading: false,
  error: null,
  source: '',
})

const hotItems = computed(() =>
  hot.source ? hot.items.filter(i => i.source_label === hot.source) : hot.items
)
const hotSources = computed(() => Array.from(new Set(hot.items.map(i => i.source_label))).slice(0, 10))
const hotTerms = computed(() => hot.terms)

async function loadHot(reset: boolean): Promise<void> {
  if (!reset && hot.items.length) return
  hot.loading = true
  hot.error = null
  try {
    const feed = await fetchHotNovels(30)
    // highlights 是全来源去重聚合榜；sources 里是各平台快照
    hot.items = feed.highlights ?? []
    hot.terms = feed.terms ?? []
    if (!hot.items.length) {
      const seen = new Set<string>()
      for (const s of feed.sources ?? []) {
        for (const item of s.items ?? []) {
          const key = `${item.source_key}-${item.title}`
          if (seen.has(key)) continue
          seen.add(key)
          hot.items.push(item)
        }
      }
    }
  } catch (e) {
    hot.error = e instanceof CloudSquareError ? e : new CloudSquareError('unknown', String(e))
    hot.items = []
    hot.terms = []
  } finally {
    hot.loading = false
  }
}

function selectHotSource(label: string): void {
  hot.source = label
}

// ── 详情抽屉 ──
const detail = reactive<{
  show: boolean
  kind: 'official' | 'community'
  asset: SquareAsset | null
  community: SquareCommunityAsset | null
}>({ show: false, kind: 'official', asset: null, community: null })

const communityDetailTitle = computed(() => detail.community?.asset?.title || '社区模板详情')

/** 管理端斩断门：任一激活数据面的错误是 suspended 时整页静待 */
const suspendedError = computed(() => {
  const pool = [official.error, community.error, hot.error]
  return pool.find(e => e?.kind === 'suspended') ?? null
})

async function openOfficialDetail(asset: SquareAsset): Promise<void> {
  detail.kind = 'official'
  detail.asset = asset
  detail.community = null
  detail.show = true
  // 详情有更多字段（变量/样章/模板文本），后台补拉一次替换
  try {
    detail.asset = (await fetchSquareAssetDetail(asset.id)) ?? asset
  } catch {
    // 列表数据够用，静默降级
  }
}

async function openCommunityDetail(item: SquareCommunityAsset): Promise<void> {
  detail.kind = 'community'
  detail.community = item
  detail.asset = null
  detail.show = true
  try {
    detail.community = await fetchSquareCommunityDetail(item.id)
    // 浏览即上报 view 事件（登录态下；匿名上游 401 静默忽略）
    void sendSquareEvent(item.id, 'view').catch(() => undefined)
  } catch {
    // 列表数据够用，静默降级
  }
}

// ── 杂项 ──

const ZONE_ACCENTS: Record<string, string> = {
  genre_hooks: '#10b981',
  creative_components: '#6366f1',
  opening_artifact: '#f59e0b',
  structure_pacing: '#06b6d4',
  packaging_benchmarking: '#ec4899',
}
function zoneAccent(asset: SquareAsset): string {
  return ZONE_ACCENTS[asset.zone ?? ''] ?? 'var(--color-brand, #4f46e5)'
}

function slotLabel(slot: string): string {
  if (slot === 'work') return '作品设定'
  if (slot === 'resource') return '资源设定'
  if (slot === 'stage') return '阶段设定'
  return ''
}

function visibilityLabel(item: SquareCommunityAsset): string {
  if (item.visibility === 'public') return '公开'
  if (item.visibility === 'link') return '链接可见'
  if (item.visibility === 'workspace') return '工作区'
  return ''
}

function publishTimeLabel(item: SquareCommunityAsset): string {
  const ts = item.published_at ?? item.updated_at ?? 0
  if (!ts) return ''
  const diffMs = Date.now() - ts * 1000
  if (!Number.isFinite(diffMs) || diffMs < 0) return ''
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 60) return `${Math.max(minutes, 1)} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}

const AVATAR_PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6']
function avatarColor(item: SquareCommunityAsset): string {
  const seed = item.creator_user_id || item.id || ''
  let h = 0
  for (const ch of seed) h = (h * 31 + ch.codePointAt(0)!) % 997
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length]
}

function authorInitial(item: SquareCommunityAsset): string {
  const name = item.author?.pen_name || item.author?.display_name || '匿'
  return name.slice(0, 1).toUpperCase()
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.all([loadSession(), loadGenres()])
    if (activeTab.value === 'official') await loadOfficial(true)
    else if (activeTab.value === 'community') await loadCommunity(true)
    else await loadHot(true)
  } finally {
    refreshing.value = false
  }
}

function goHome(): void {
  void router.push('/')
}

/** 切 tab 懒加载：社区/热榜首次进入才拉数据（官方书元挂载即拉） */
function onTabChange(tab: TabKey): void {
  activeTab.value = tab
  if (loadedTabs.has(tab)) return
  loadedTabs.add(tab)
  if (tab === 'community') void loadCommunity(true)
  else if (tab === 'hot') void loadHot(true)
}

onMounted(() => {
  void loadSession()
  void loadGenres()
  void loadOfficial(true)
})
</script>

<style scoped>
.square-view {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--app-surface-subtle);
}

/* ── 顶栏 ── */
.square-topbar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 14px 28px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.square-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  border-radius: 9px;
  padding: 7px 12px 7px 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.square-back svg {
  width: 15px;
  height: 15px;
}

.square-back:hover {
  color: var(--color-brand, #4f46e5);
  border-color: var(--color-brand, #4f46e5);
}

.square-title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.square-title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.01em;
}

.square-origin {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.square-session {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: 999px;
  padding: 5px 12px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-chip.is-on .session-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  flex: none;
}

.session-btn {
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  border-radius: 9px;
  padding: 7px 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
}

.session-btn:hover:not(:disabled) {
  border-color: var(--color-brand, #4f46e5);
  color: var(--color-brand, #4f46e5);
}

.session-btn.is-login {
  background: var(--color-brand, #4f46e5);
  border-color: var(--color-brand, #4f46e5);
  color: #fff;
}

.session-btn.is-login:hover {
  filter: brightness(1.08);
}

.session-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

/* ── Tabs ── */
.square-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 28px 0;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
}

.square-tab {
  position: relative;
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: color 0.16s ease;
}

.square-tab::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 2.5px;
  border-radius: 2px 2px 0 0;
  background: transparent;
  transition: background 0.16s ease;
}

.square-tab:hover {
  color: var(--app-text-secondary);
}

.square-tab.is-active {
  color: var(--color-brand, #4f46e5);
}

.square-tab.is-active::after {
  background: var(--color-brand, #4f46e5);
}

.tab-count {
  font-size: 10.5px;
  font-weight: 700;
  background: var(--app-surface-subtle);
  color: var(--app-text-muted);
  border-radius: 999px;
  padding: 1px 7px;
}

.square-tab.is-active .tab-count {
  background: color-mix(in srgb, var(--color-brand, #4f46e5) 12%, transparent);
  color: var(--color-brand, #4f46e5);
}

/* ── 主区 ── */
.square-body {
  flex: 1;
  padding: 20px 28px 40px;
  max-width: 1280px;
  width: 100%;
  box-sizing: border-box;
  margin: 0 auto;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.genre-chips {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.genre-chip {
  --chip-accent: var(--color-brand, #4f46e5);
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 12.5px;
  font-weight: 600;
  border-radius: 999px;
  padding: 5.5px 13px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.genre-chip:hover {
  border-color: var(--chip-accent);
  color: var(--chip-accent);
}

.genre-chip.is-active {
  background: var(--chip-accent);
  border-color: var(--chip-accent);
  color: #fff;
}

.chip-count {
  font-size: 10px;
  opacity: 0.75;
  font-weight: 700;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-radius: 10px;
  padding: 0 12px;
  width: 240px;
}

.search-icon {
  width: 15px;
  height: 15px;
  color: var(--app-text-muted);
  flex: none;
}

.search-box input {
  border: none;
  outline: none;
  background: transparent;
  color: var(--app-text-primary);
  font-size: 13px;
  height: 36px;
  width: 100%;
}

.search-box:focus-within {
  border-color: var(--color-brand, #4f46e5);
}

.sort-switch {
  display: inline-flex;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-radius: 10px;
  padding: 3px;
  gap: 2px;
}

.sort-btn {
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 12.5px;
  font-weight: 600;
  border-radius: 7px;
  padding: 5px 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.sort-btn.is-active {
  background: var(--color-brand, #4f46e5);
  color: #fff;
}

/* ── 卡片网格 ── */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}

.asset-card {
  text-align: left;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-radius: 14px;
  padding: 16px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 9px;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.asset-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--zone-accent, var(--color-brand, #4f46e5)) 55%, transparent);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.1);
}

.card-skeleton {
  height: 170px;
  border-radius: 14px;
  background: linear-gradient(100deg, var(--app-surface-subtle) 40%, var(--app-surface) 50%, var(--app-surface-subtle) 60%);
  background-size: 200% 100%;
  animation: skeleton-slide 1.4s ease infinite;
  border: 1px solid var(--app-border);
}

@keyframes skeleton-slide {
  from { background-position: 120% 0; }
  to { background-position: -80% 0; }
}

.card-zone {
  --zone-accent: var(--color-brand, #4f46e5);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-zone > span:first-child {
  font-size: 11px;
  font-weight: 700;
  color: var(--zone-accent);
  background: color-mix(in srgb, var(--zone-accent) 11%, transparent);
  padding: 3px 9px;
  border-radius: 6px;
}

.zone-slot {
  font-size: 10.5px;
  color: var(--app-text-muted);
  border: 1px dashed var(--app-border);
  padding: 2px 7px;
  border-radius: 6px;
}

.card-title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  color: var(--app-text-primary);
  line-height: 1.35;
}

.card-summary {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.card-tag {
  font-size: 10.5px;
  color: var(--app-text-muted);
  background: var(--app-surface-subtle);
  padding: 2px 8px;
  border-radius: 5px;
}

.card-metrics {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 4px;
  border-top: 1px dashed var(--app-border);
}

.metric {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.metric.cold {
  color: var(--color-gold, #f59e0b);
}

.metric.time {
  margin-left: auto;
  font-weight: 400;
}

.load-more {
  display: block;
  margin: 20px auto 0;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
  border-radius: 10px;
  padding: 9px 26px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.load-more:hover:not(:disabled) {
  border-color: var(--color-brand, #4f46e5);
  color: var(--color-brand, #4f46e5);
}

.load-more:disabled {
  opacity: 0.55;
  cursor: wait;
}

/* ── 社区卡 ── */
.community-head {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.author-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.author-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.author-grade {
  font-size: 10px;
  font-weight: 700;
  color: var(--color-gold, #f59e0b);
  background: color-mix(in srgb, var(--color-gold, #f59e0b) 12%, transparent);
  padding: 1px 7px;
  border-radius: 5px;
  flex: none;
}

.community-visibility {
  margin-left: auto;
  font-size: 10px;
  color: var(--app-text-muted);
  border: 1px solid var(--app-border);
  padding: 1px 7px;
  border-radius: 5px;
  flex: none;
}

.detail-author {
  margin-bottom: 4px;
}

/* ── 空态/错误态 ── */
.empty-block {
  text-align: center;
  padding: 60px 20px;
  color: var(--app-text-muted);
}

.empty-block p {
  margin: 0 0 6px;
  font-size: 14px;
}

.empty-sub {
  font-size: 12px !important;
  opacity: 0.75;
}

/* ── 热榜 ── */
.hot-terms {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
}

.terms-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-gold, #f59e0b);
  flex: none;
}

.hot-term {
  font-size: 12px;
  color: var(--app-text-secondary);
  background: var(--app-surface-subtle);
  padding: 3px 10px;
  border-radius: 999px;
}

.rank-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 14px;
  overflow: hidden;
}

.rank-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--app-border);
}

.rank-item:last-child {
  border-bottom: none;
}

.rank-item.is-top {
  background: color-mix(in srgb, var(--color-brand, #4f46e5) 4%, transparent);
}

.rank-item--skeleton {
  height: 58px;
  background: linear-gradient(100deg, var(--app-surface-subtle) 40%, var(--app-surface) 50%, var(--app-surface-subtle) 60%);
  background-size: 200% 100%;
  animation: skeleton-slide 1.4s ease infinite;
}

.rank-skeleton {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 14px;
  overflow: hidden;
}

.rank-no {
  width: 26px;
  height: 26px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12.5px;
  font-weight: 800;
  border-radius: 8px;
  color: var(--app-text-muted);
  background: var(--app-surface-subtle);
}

.rank-no-1 { background: #f59e0b; color: #fff; }
.rank-no-2 { background: #94a3b8; color: #fff; }
.rank-no-3 { background: #d97706; color: #fff; }

.rank-main {
  flex: 1;
  min-width: 0;
}

.rank-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.rank-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-author {
  font-size: 12px;
  color: var(--app-text-muted);
  flex: none;
}

.rank-intro {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-muted);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
}

.rank-side {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}

.rank-source {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.rank-tags {
  display: flex;
  gap: 4px;
}

.rank-tag {
  font-size: 10px;
  color: var(--color-brand, #4f46e5);
  background: color-mix(in srgb, var(--color-brand, #4f46e5) 9%, transparent);
  padding: 1px 7px;
  border-radius: 5px;
}

/* ── 详情抽屉内容 ── */
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-chip {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-secondary);
  background: var(--app-surface-subtle);
  padding: 3px 10px;
  border-radius: 6px;
}

.detail-chip.zone {
  color: var(--color-brand, #4f46e5);
  background: color-mix(in srgb, var(--color-brand, #4f46e5) 11%, transparent);
}

.detail-summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--app-text-secondary);
}

.detail-section h4 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--app-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.var-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--app-border);
}

.var-row:last-child {
  border-bottom: none;
}

.var-key {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  color: var(--color-brand, #4f46e5);
  background: color-mix(in srgb, var(--color-brand, #4f46e5) 9%, transparent);
  padding: 2px 7px;
  border-radius: 5px;
}

.var-label {
  font-size: 12.5px;
  color: var(--app-text-secondary);
}

.var-required {
  margin-left: auto;
  font-size: 10px;
  color: var(--color-gold, #f59e0b);
}

.detail-pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-secondary);
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.dm {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 12px 6px;
  background: var(--app-surface-subtle);
  border-radius: 10px;
}

.dm b {
  font-size: 17px;
  color: var(--app-text-primary);
}

.dm span {
  font-size: 11px;
  color: var(--app-text-muted);
}

/* ── 登录弹层 ── */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px;
}

.login-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-muted);
  background: var(--app-surface-subtle);
  border-radius: 8px;
  padding: 10px 12px;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.login-field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.login-field input {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  color: var(--app-text-primary);
  background: var(--app-surface);
  outline: none;
}

.login-field input:focus {
  border-color: var(--color-brand, #4f46e5);
}

.login-error {
  margin: 0;
  font-size: 12px;
  color: var(--color-danger, #dc2626);
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .square-topbar,
  .square-tabs,
  .square-body {
    padding-left: 16px;
    padding-right: 16px;
  }

  .search-box {
    width: 100%;
  }

  .rank-side {
    display: none;
  }
}
</style>
