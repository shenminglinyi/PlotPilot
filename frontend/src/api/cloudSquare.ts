/**
 * 云端广场（线上提示词广场）API：全部经本地内核 /cloud/* 代理。
 *
 * 数据流：前端 → 本地后端 /api/v1/cloud/proxy → https://plotpilot.xyz。
 * 好处：无 CORS、凭证仅存服务端、路径白名单收口（SSRF 免疫）。
 * 公开目录（genres/facets/assets/community）匿名可读；热榜/互动需登录。
 */
import { fetchJson, HttpError } from './http'

// ── 类型（只取 UI 渲染用到的字段子集） ──

export interface SquareGenre {
  slug: string
  label: string
  english_label?: string
  description?: string
  accent?: string
  count?: number
}

export interface SquareFacets {
  genres?: SquareGenre[]
  zones?: Array<{ key: string; label: string }>
  hooks?: Array<{ key: string; label: string }>
  stages?: Array<{ key: string; label: string }>
}

export interface SquareAssetMetrics {
  trial_count?: number
  apply_count?: number
  remix_count?: number
  successful_run_rate?: number
  cold_start?: boolean
}

export interface SquareVariableSpec {
  key: string
  label?: string
  required?: boolean
}

export interface SquareAsset {
  id: string
  version?: string
  title: string
  summary?: string
  asset_type?: string
  zone?: string
  zone_label?: string
  slot_key?: string
  produces_document?: string
  genre_tags?: string[]
  genre_slugs?: string[]
  hook_tags?: string[]
  stage_tags?: string[]
  variables?: SquareVariableSpec[]
  template_text?: string
  sample_excerpt?: string
  has_prompt_source?: boolean
  metrics?: SquareAssetMetrics
}

export interface SquareAssetList {
  assets: SquareAsset[]
  next_cursor?: string
  total_visible_hint?: number
  viewer_tier?: string
}

export interface SquareAuthorCard {
  pen_name?: string
  display_name?: string
  grade_label?: string
  grade?: string
  avatar_url?: string
}

export interface SquareCommunityAsset {
  id: string
  creator_user_id?: string
  visibility?: string
  review_status?: string
  safe_sample?: string
  ai_disclosure?: string
  counters?: Record<string, number>
  successful_run_rate?: number
  rank_score?: number
  published_at?: number
  updated_at?: number
  asset?: SquareAsset
  author?: SquareAuthorCard
  title?: string
  summary?: string
}

export interface SquareCommunityList {
  assets: SquareCommunityAsset[]
  next_cursor?: string
}

export interface HotNovelItem {
  source_key: string
  source_label: string
  rank: number
  title: string
  author?: string | null
  category?: string | null
  url?: string | null
  intro?: string | null
  hot_value?: string | null
  tags?: string[]
}

export interface HotNovelSourceSnapshot {
  source_key: string
  source_label: string
  platform?: string
  period?: string
  items: HotNovelItem[]
  error?: string | null
}

export interface HotNovelTerm {
  term: string
  kind?: string
  item_count?: number
  score?: number
}

export interface HotNovelFeed {
  generated_at?: string
  highlights?: HotNovelItem[]
  terms?: HotNovelTerm[]
  sources?: HotNovelSourceSnapshot[]
}

export interface CloudSessionStatus {
  logged_in: boolean
  username?: string
  display_name?: string
  user_id?: string
}

// ── 代理底层 ──

interface CloudProxyEnvelope {
  status_code: number
  body: { data?: unknown; detail?: string; message?: string } & Record<string, unknown>
}

/** 云端下发/服务端管控的机器码：管理端斩断开源端广场 */
export const KERNEL_SQUARE_SUSPENDED_DETAIL = 'kernel_square_suspended'

/** 云端不可达/会话失效等本地代理错误 */
export class CloudSquareError extends Error {
  /**
   * - 'suspended'：管理端斩断（上游 403 + kernel_square_suspended）
   * - 'unreachable'：本地内核/网络不可达
   * - 'auth'：需登录云端
   * - 'upstream'：云端 4xx/5xx
   * - 'unknown'：未知
   */
  kind: 'suspended' | 'unreachable' | 'auth' | 'upstream' | 'unknown'
  upstreamStatus?: number

  constructor(kind: CloudSquareError['kind'], message: string, upstreamStatus?: number) {
    super(message)
    this.name = 'CloudSquareError'
    this.kind = kind
    this.upstreamStatus = upstreamStatus
  }
}

async function cloudGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const cleaned: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== '') cleaned[k] = v
  }
  let envelope: CloudProxyEnvelope
  try {
    envelope = await fetchJson<CloudProxyEnvelope>('/api/v1/cloud/proxy', {
      method: 'POST',
      body: { method: 'GET', path, params: cleaned },
      timeoutMs: 30_000,
    })
  } catch (e) {
    if (e instanceof HttpError) {
      if (e.status === 401) throw new CloudSquareError('auth', '尚未登录云端', 401)
      throw new CloudSquareError('unreachable', '本地内核不可达', e.status)
    }
    throw new CloudSquareError('unknown', e instanceof Error ? e.message : String(e))
  }
  const upstream = envelope.status_code
  if (upstream >= 500) {
    throw new CloudSquareError('upstream', `云端服务异常（${upstream}）`, upstream)
  }
  if (upstream === 403 && envelope.body?.detail === KERNEL_SQUARE_SUSPENDED_DETAIL) {
    // 管理端斩断：整页显示「线上暂未提供服务，静待～」，不是登录问题
    throw new CloudSquareError(
      'suspended',
      envelope.body?.message || '线上暂未提供服务，静待～',
      upstream,
    )
  }
  if (upstream === 401 || upstream === 403) {
    throw new CloudSquareError('auth', envelope.body?.detail || '需要登录云端', upstream)
  }
  if (upstream === 404) {
    throw new CloudSquareError('upstream', '云端暂无此内容', 404)
  }
  return (envelope.body?.data ?? {}) as T
}

async function cloudPost(path: string, body: Record<string, unknown>): Promise<void> {
  try {
    await fetchJson<CloudProxyEnvelope>('/api/v1/cloud/proxy', {
      method: 'POST',
      body: { method: 'POST', path, body },
      timeoutMs: 20_000,
    })
  } catch (e) {
    if (e instanceof HttpError) {
      if (e.status === 401) throw new CloudSquareError('auth', '尚未登录云端', 401)
      throw new CloudSquareError('unreachable', '本地内核不可达', e.status)
    }
    throw new CloudSquareError('unknown', e instanceof Error ? e.message : String(e))
  }
}

// ── 会话 ──

export async function fetchCloudSession(): Promise<CloudSessionStatus> {
  const res = await fetchJson<{ data: CloudSessionStatus }>('/api/v1/cloud/session')
  return res.data
}

export async function loginCloudSession(username: string, password: string): Promise<CloudSessionStatus> {
  const res = await fetchJson<{ data: CloudSessionStatus }>('/api/v1/cloud/session', {
    method: 'POST',
    body: { username, password },
  })
  return res.data
}

export async function logoutCloudSession(): Promise<void> {
  await fetchJson('/api/v1/cloud/session', { method: 'DELETE' })
}

// ── 目录面（公开，匿名可读） ──

const genresCache: { at: number; data: SquareGenre[] } = { at: 0, data: [] }
const GENRES_TTL_MS = 5 * 60 * 1000

export async function fetchSquareGenres(force = false): Promise<SquareGenre[]> {
  if (!force && genresCache.data.length && Date.now() - genresCache.at < GENRES_TTL_MS) {
    return genresCache.data
  }
  const data = await cloudGet<{ genres: SquareGenre[] }>('/api/v1/prompt-square/genres')
  genresCache.data = data.genres ?? []
  genresCache.at = Date.now()
  return genresCache.data
}

export interface SquareAssetQuery {
  q?: string
  genre?: string
  zone?: string
  cursor?: string
  limit?: number
}

export async function fetchSquareAssets(query: SquareAssetQuery = {}): Promise<SquareAssetList> {
  return cloudGet<SquareAssetList>('/api/v1/prompt-square/assets', {
    q: query.q,
    genre: query.genre,
    zone: query.zone,
    cursor: query.cursor,
    limit: query.limit ?? 24,
  })
}

export async function fetchSquareAssetDetail(assetId: string): Promise<SquareAsset | null> {
  // 详情响应是 {asset: {...}, viewer_tier}——服务端把资产包了一层
  const data = await cloudGet<{ asset?: SquareAsset }>(
    `/api/v1/prompt-square/assets/${encodeURIComponent(assetId)}`,
  )
  return data.asset ?? null
}

export interface SquareCommunityQuery {
  q?: string
  zone?: string
  genre?: string
  sort?: 'hot' | 'recent' | 'discussed'
  cursor?: string
  limit?: number
}

export async function fetchSquareCommunity(query: SquareCommunityQuery = {}): Promise<SquareCommunityList> {
  return cloudGet<SquareCommunityList>('/api/v1/prompt-square/community/assets', {
    q: query.q,
    zone: query.zone,
    genre: query.genre,
    sort: query.sort ?? 'hot',
    cursor: query.cursor,
    limit: query.limit ?? 30,
  })
}

export async function fetchSquareCommunityDetail(id: string): Promise<SquareCommunityAsset> {
  return cloudGet<SquareCommunityAsset>(
    `/api/v1/prompt-square/community/assets/${encodeURIComponent(id)}`,
  )
}

// ── 热榜（云端需登录，匿名时上游 401 → CloudSquareError(auth)） ──

export async function fetchHotNovels(limit = 20): Promise<HotNovelFeed> {
  return cloudGet<HotNovelFeed>('/api/v1/prompt-square/hot-novels', { limit })
}

// ── 社区互动（需登录） ──

export type SquareEventType = 'view' | 'save' | 'trial' | 'apply' | 'remix' | 'urge'

export async function sendSquareEvent(communityAssetId: string, eventType: SquareEventType): Promise<void> {
  await cloudPost(
    `/api/v1/prompt-square/community/assets/${encodeURIComponent(communityAssetId)}/events`,
    { event_type: eventType, idempotency_key: `desktop-${Date.now()}` },
  )
}
