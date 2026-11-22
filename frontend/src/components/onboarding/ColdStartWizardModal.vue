<template>
  <teleport to="body">
    <div v-if="show" ref="maskRef" class="cold-mask" @click.self="close">
      <section ref="dialogRef" class="cold-dialog" role="dialog" aria-modal="true" aria-label="三分钟极速开书" tabindex="-1" :aria-busy="submitting || abandoning">
        <header class="cold-head"><h2>三分钟极速开书</h2><button ref="closeRef" type="button" :disabled="submitting || abandoning" @click="close">收起</button></header>
        <nav class="step-ledger" aria-label="开书步骤">
          <button v-for="(label, i) in stepLabels" :key="label" type="button" :class="{ 'is-current': step === i }" :aria-current="step === i ? 'step' : undefined" :disabled="i > furthestStep || submitting || busy || abandoning || recoveryLocked" @click="goStep(i)">{{ label }}</button>
        </nav>
        <div ref="bodyRef" class="cold-body" tabindex="-1">
          <section v-if="step === 0" class="step-sheet">
            <h3>接通创作模型与省额编组</h3>
            <div class="connection-block">
              <h4>本机订阅网关</h4><p>Magpie · 127.0.0.1:3425/v1</p>
              <button type="button" :disabled="busy || panelLoading" @click="probe">{{ busy ? '正在读取网关…' : '嗅探本机订阅网关' }}</button>
              <p v-if="probed && !reachableGateways.length" role="status">尚未发现可用网关，请确认本机网关已启动，或打开完整设置。</p>
              <div v-for="gateway in reachableGateways" :key="gateway.id" class="gateway-row">
                <strong>{{ gateway.name }} · {{ gateway.models.length }} 个模型</strong><p>{{ gateway.base_url }}</p>
                <dl class="role-ledger"><div><dt>主写 main</dt><dd>{{ gateway.recommended_roles.main || '未推荐' }}</dd></div><div><dt>省额 cheap</dt><dd>{{ gateway.recommended_roles.cheap || '沿用主写' }}</dd></div><div><dt>记忆 kg</dt><dd>{{ gateway.recommended_roles.kg || '沿用主写' }}</dd></div></dl>
                <button type="button" :disabled="busy || !(gateway.recommended_roles.main || gateway.models[0])" @click="connect(gateway)">一键接通省额黄金编组</button>
              </div>
            </div>
            <div class="connection-block"><h4>免密授权与完整模型设置</h4><div class="action-row"><button type="button" :disabled="busy" @click="authorize">OpenRouter 免密授权</button><button type="button" :disabled="busy" @click="openEngine">打开完整模型引擎设置</button><button type="button" :disabled="panelLoading || busy" @click="refreshPanel">刷新连接状态</button></div><p v-if="oauthNotice" role="status">{{ oauthNotice }}</p><a v-if="oauthUrl" :href="oauthUrl" target="_blank" rel="noopener noreferrer">打开授权页</a></div>
            <div class="runtime-strip" :class="{ 'is-ready': runtimeReady }">
              <p v-if="panelLoading">正在核对当前模型配置…</p>
              <p v-else-if="runtimeReady">已就绪主力模型：{{ panel?.runtime.active_profile_name || panel?.runtime.model }}</p>
              <p v-else>当前处于演示回退态，建议先嗅探本机网关或配置接口；亦可先立卷再配置模型。</p>
              <p v-if="runtimeReady">{{ panel?.config.endpoint_mode === 'independent' ? '独立角色编组' : '同源角色编组' }} · {{ currentRoleModels.join(' · ') }}</p>
              <p>记忆检索向量已自动启用同源轻量或本地词频检索兜底，无需单独配置向量密钥，人物状态与前文伏笔自动归档。</p>
            </div>
          </section>
          <section v-else-if="step === 1" class="step-sheet">
            <h3>择定题材流派与叙事模组</h3>
            <label class="field"><span>暂定书名</span><input v-model="title" maxlength="120" :disabled="submitting || recoveryLocked" placeholder="例如：夜雨寄北录（立卷后可随时易名）" /></label>
            <div class="taxonomy-choices" aria-label="题材大类"><button v-for="root in roots" :key="root.id" type="button" :disabled="submitting || recoveryLocked" :aria-pressed="selectedRoot?.id === root.id" :class="{ 'is-selected': selectedRoot?.id === root.id }" @click="selectRoot(root)">{{ pickLocaleLabel(root) }}</button></div>
            <div class="taxonomy-choices" aria-label="细分主题"><button v-for="leaf in selectedRoot?.children || []" :key="leaf.id" type="button" :disabled="submitting || recoveryLocked" :aria-pressed="selectedLeaf?.id === leaf.id" :class="{ 'is-selected': selectedLeaf?.id === leaf.id }" @click="leafId = leaf.id">{{ pickLocaleLabel(leaf) }}</button></div>
            <h4>叙事模组</h4>
            <div class="pack-ledger"><button v-for="pack in CURATED_MOD_PACKS" :key="pack.id" type="button" class="pack-row" :disabled="submitting || recoveryLocked" :class="{ 'is-selected': selectedIds.includes(pack.id) }" :aria-pressed="selectedIds.includes(pack.id)" @click="togglePack(pack.id)"><span class="pack-glyph" aria-hidden="true">{{ pack.glyph }}</span><span class="pack-copy"><strong>{{ pack.name }}</strong><span v-if="pack.recommendedModelTier" class="tier-badge">{{ MOD_RECOMMENDED_MODEL_TIER_META[pack.recommendedModelTier].shortBadge }}</span><span class="pack-summary">{{ pack.summary }}</span><span v-if="modHub.isInstalled(pack.id)" class="installed-note">已安装</span></span><span class="pack-status">{{ selectedIds.includes(pack.id) ? '已选' : '挂载' }}</span></button></div>
            <p v-if="tierMismatch" class="quiet-note">所选模组建议旗舰主写档，当前模型偏轻量；可先试写，再按叙事复杂度调整主力模型。</p>
          </section>
          <section v-else class="step-sheet">
            <h3>落定开篇节拍，直入首章试写</h3>
            <label class="field"><span>首章节拍与梗概</span><textarea v-model="premise" rows="9" maxlength="2000" class="premise-sheet" :disabled="submitting || recoveryLocked" @input="premiseEdited = true" /></label>
            <div class="action-row"><span class="quiet-note">已就绪首章引子 · {{ premise.trim().length }} 字</span><button v-if="premise !== sourceScaffold && !recoveryLocked" type="button" :disabled="submitting || abandoning" @click="restoreScaffold">恢复模组原支架</button><button v-if="recoveryLocked" type="button" :disabled="submitting || busy || abandoning" @click="abandonRecovery">{{ novelConfirmed ? '放弃未完书卷并重开' : '放弃待确认草稿并重开' }}</button></div>
            <p v-if="scaffoldTruncated" class="quiet-note">模组支架较长，已带入前 2000 字，可在本步精简。</p>
            <p v-if="recoveryLocked && novelConfirmed" class="quiet-note">书卷《{{ title || '未命名新卷' }}》已建立且首章节拍快照已锁定；请点击下方按钮继续完成首章起笔初始化，或放弃此卷重新立卷。</p>
            <p v-else-if="recoveryLocked" class="quiet-note">上次立卷《{{ title || '未命名新卷' }}》响应未确认，已保留同一书目编号与首章节拍快照；继续操作将先核对服务端状态再安全续接，不会重复建书。</p>
            <div class="runtime-strip"><p>审稿红线 {{ redlineCount }} 条 · 净词巡检 {{ wordCount }} 词</p><p>进入工作台后按 Alt + Z 可开启禅意卷边批注</p></div>
          </section>
          <p v-if="errorText" class="error-note" role="alert">{{ errorText }}</p>
        </div>
        <footer class="cold-foot">
          <template v-if="step === 0"><button type="button" :disabled="busy || panelLoading || submitting || abandoning" @click="goStep(1)">沿用现有配置</button><button type="button" class="primary" :disabled="busy || panelLoading || submitting || abandoning" @click="goStep(1)">确认编组，选流派</button></template>
          <template v-else-if="step === 1"><button type="button" :disabled="submitting || abandoning || recoveryLocked" @click="goStep(0)">上一步</button><button type="button" :disabled="submitting || abandoning || recoveryLocked" @click="skipPacks">暂不挂模组</button><button type="button" class="primary" :disabled="submitting || abandoning" @click="goStep(2)">带入支架，下一步</button></template>
          <template v-else><button type="button" :disabled="submitting || abandoning || recoveryLocked" @click="goStep(1)">上一步</button><button type="button" :disabled="submitting || busy || abandoning || (!recoveryLocked && !premise.trim())" @click="submit(false)">{{ !recoveryLocked ? '仅立卷，稍后写' : novelConfirmed ? '完成初始化回书架' : '核对并立卷回书架' }}</button><button type="button" class="primary" :disabled="submitting || busy || abandoning || (!recoveryLocked && !premise.trim())" @click="submit(true)">{{ submitting ? '正在处理…' : !recoveryLocked ? '立卷并试写第一章' : novelConfirmed ? '重试初始化并试写' : '核对并试写第一章' }}</button></template>
        </footer>
      </section>
    </div>
  </teleport>
</template>

<script lang="ts">
import type { AxiosRequestConfig } from 'axios'
import { apiClient } from '@/api/config'
import { apiRoutes } from '@/api/endpoints'
import type { NovelDTO, novelApi as NovelApiType } from '@/api/novel'
import { readStorageJson, removeStorageItem, writeStorageJson } from '@/utils/storage'
import { isWizardCompleted, markWizardCompleted } from '@/utils/wizardStageCache'

export const COLD_START_RECOVERY_STORAGE_KEY = 'plotpilot:cold-start-recovery:v1'
export const COLD_START_ABANDONED_OPS_STORAGE_KEY = 'plotpilot:cold-start-abandoned-ops:v1'

export type ColdStartCreatePayload = Parameters<typeof NovelApiType.createNovel>[0]

export interface ColdStartRecoveryRecord {
  v: 1
  rev: number
  opId: string
  novelId: string
  novelConfirmed: boolean
  payload: ColdStartCreatePayload
  title: string
  premise: string
  chapterHint: string
  chapter1Ensured: boolean
  chapter1HintSaved: boolean
  savedAt: number
}

export type NovelReconcileProbeResult =
  | { status: 'missing' }
  | { status: 'matched'; novel: NovelDTO }
  | { status: 'conflict'; novel?: NovelDTO }
  | { status: 'unverifiable' }

const V1_LENGTH_TIER_META: Record<
  'short' | 'standard' | 'epic',
  { approxTotalWords: number; defaultChapterWords: number }
> = {
  short: { approxTotalWords: 300_000, defaultChapterWords: 2000 },
  standard: { approxTotalWords: 1_000_000, defaultChapterWords: 2000 },
  epic: { approxTotalWords: 3_000_000, defaultChapterWords: 2000 },
}

function clampExpectedChapterWords(words: number): number {
  return Math.max(500, Math.min(20_000, Math.trunc(words)))
}

function resolveExpectedLengthParams(payload: ColdStartCreatePayload): {
  targetChapters: number
  targetWordsPerChapter: number
} {
  const rawTier =
    typeof payload.length_tier === 'string' ? payload.length_tier.trim().toLowerCase() : ''
  if (rawTier === 'short' || rawTier === 'standard' || rawTier === 'epic') {
    const meta = V1_LENGTH_TIER_META[rawTier]
    const requestedWpc =
      typeof payload.target_words_per_chapter === 'number' &&
      Number.isFinite(payload.target_words_per_chapter) &&
      payload.target_words_per_chapter > 0
        ? payload.target_words_per_chapter
        : meta.defaultChapterWords
    const wpc = clampExpectedChapterWords(requestedWpc)
    return {
      targetChapters: Math.max(1, Math.ceil(meta.approxTotalWords / wpc)),
      targetWordsPerChapter: wpc,
    }
  }
  const tc =
    typeof payload.target_chapters === 'number' &&
    Number.isFinite(payload.target_chapters) &&
    payload.target_chapters > 0
      ? Math.trunc(payload.target_chapters)
      : 100
  const requestedTw =
    typeof payload.target_words_per_chapter === 'number' &&
    Number.isFinite(payload.target_words_per_chapter) &&
    payload.target_words_per_chapter > 0
      ? payload.target_words_per_chapter
      : 2500
  return {
    targetChapters: tc,
    targetWordsPerChapter: clampExpectedChapterWords(requestedTw),
  }
}

export function hasVerifiableNovelIdentityShape(raw: unknown): raw is NovelDTO {
  if (!raw || typeof raw !== 'object') return false
  const candidate = raw as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    candidate.id.length > 0 &&
    candidate.id === candidate.id.trim() &&
    typeof candidate.title === 'string' &&
    typeof candidate.author === 'string' &&
    typeof candidate.premise === 'string' &&
    typeof candidate.target_chapters === 'number' &&
    Number.isFinite(candidate.target_chapters) &&
    typeof candidate.target_words_per_chapter === 'number' &&
    Number.isFinite(candidate.target_words_per_chapter) &&
    typeof candidate.locked_genre === 'string' &&
    typeof candidate.locked_world_preset === 'string' &&
    typeof candidate.locked_story_structure === 'string' &&
    typeof candidate.locked_pacing_control === 'string' &&
    typeof candidate.locked_writing_style === 'string' &&
    typeof candidate.locked_special_requirements === 'string'
  )
}

export function matchesSeedNovelIdentity(
  dto: NovelDTO,
  seed: ColdStartRecoveryRecord,
): boolean {
  if (!hasVerifiableNovelIdentityShape(dto)) return false
  if (dto.id !== seed.novelId) return false
  const { targetChapters, targetWordsPerChapter } = resolveExpectedLengthParams(seed.payload)
  return (
    dto.title.trim() === (seed.payload.title || '').trim() &&
    dto.author.trim() === (seed.payload.author || '').trim() &&
    (dto.premise ?? '').trim() === (seed.payload.premise ?? '').trim() &&
    dto.target_chapters === targetChapters &&
    dto.target_words_per_chapter === targetWordsPerChapter &&
    (dto.locked_genre ?? '').trim() === (seed.payload.genre ?? '').trim() &&
    (dto.locked_world_preset ?? '').trim() === (seed.payload.world_preset ?? '').trim() &&
    (dto.locked_story_structure ?? '').trim() === (seed.payload.story_structure ?? '').trim() &&
    (dto.locked_pacing_control ?? '').trim() === (seed.payload.pacing_control ?? '').trim() &&
    (dto.locked_writing_style ?? '').trim() === (seed.payload.writing_style ?? '').trim() &&
    (dto.locked_special_requirements ?? '').trim() ===
      (seed.payload.special_requirements ?? '').trim()
  )
}

export async function probeNovelReconciliation(
  seed: ColdStartRecoveryRecord,
  signal?: AbortSignal,
): Promise<NovelReconcileProbeResult> {
  if (signal?.aborted) {
    throw new Error('立卷状态核对已取消')
  }
  let onAbort: (() => void) | null = null
  try {
    const requestPromise = apiClient.get<NovelDTO>(apiRoutes.novels.detail(seed.novelId), {
      silentGlobalFeedback: true,
      signal,
    } as AxiosRequestConfig & { silentGlobalFeedback?: boolean })
    const rawDto = signal
      ? await Promise.race([
          requestPromise,
          new Promise<never>((_, reject) => {
            onAbort = () => reject(new Error('立卷状态核对已取消'))
            signal.addEventListener('abort', onAbort, { once: true })
          }),
        ])
      : await requestPromise
    if (!rawDto || typeof rawDto !== 'object') {
      return { status: 'unverifiable' }
    }
    const rawId = (rawDto as { id?: unknown }).id
    if (typeof rawId === 'string' && rawId.length > 0 && rawId !== seed.novelId) {
      return { status: 'conflict', novel: rawDto as NovelDTO }
    }
    if (!hasVerifiableNovelIdentityShape(rawDto)) {
      return { status: 'unverifiable' }
    }
    if (!matchesSeedNovelIdentity(rawDto, seed)) {
      return { status: 'conflict', novel: rawDto }
    }
    return { status: 'matched', novel: rawDto }
  } catch (error) {
    const status = (error as { response?: { status?: number } } | null)?.response?.status
    if (status === 404) {
      return { status: 'missing' }
    }
    throw error
  } finally {
    if (signal && onAbort) {
      signal.removeEventListener('abort', onAbort)
    }
  }
}

function readAbandonedColdStartOps(): string[] {
  const raw = readStorageJson<unknown>(COLD_START_ABANDONED_OPS_STORAGE_KEY, [])
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())).slice(-24)
}

function recordAbandonedColdStartOp(opId: string | undefined): void {
  if (!opId || !opId.trim()) return
  const existing = readAbandonedColdStartOps().filter(item => item !== opId)
  existing.push(opId)
  writeStorageJson(COLD_START_ABANDONED_OPS_STORAGE_KEY, existing.slice(-24))
}

export function isColdStartOpAbandoned(opId: string): boolean {
  if (!opId) return true
  return readAbandonedColdStartOps().includes(opId)
}

function createUniqueSuffix(): string {
  const randomUuid =
    typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`
  return randomUuid
}

function createColdStartOpId(): string {
  return `csop-${createUniqueSuffix()}`
}

function createColdStartNovelId(): string {
  return `novel-${createUniqueSuffix()}`
}

export function readColdStartRecovery(): ColdStartRecoveryRecord | null {
  const raw = readStorageJson<Partial<ColdStartRecoveryRecord> | null>(COLD_START_RECOVERY_STORAGE_KEY, null)
  if (
    !raw ||
    raw.v !== 1 ||
    typeof raw.novelId !== 'string' ||
    !raw.novelId ||
    raw.novelId !== raw.novelId.trim()
  ) {
    return null
  }
  const novelId = raw.novelId
  if (isWizardCompleted(novelId)) {
    return null
  }
  const opId = typeof raw.opId === 'string' && raw.opId.trim() ? raw.opId.trim() : `legacy-${novelId}`
  if (isColdStartOpAbandoned(opId)) {
    return null
  }
  const novelConfirmed = typeof raw.novelConfirmed === 'boolean' ? raw.novelConfirmed : false
  const title = typeof raw.title === 'string' && raw.title.trim() ? raw.title : '未命名新卷'
  const chapterHint = typeof raw.chapterHint === 'string' ? raw.chapterHint : ''
  const premise = typeof raw.premise === 'string' && raw.premise.trim() ? raw.premise : chapterHint
  const hasValidPayload =
    raw.payload !== null &&
    typeof raw.payload === 'object' &&
    typeof raw.payload.title === 'string' &&
    Boolean(raw.payload.title.trim()) &&
    typeof raw.payload.author === 'string' &&
    Boolean(raw.payload.author.trim()) &&
    typeof raw.payload.target_chapters === 'number' &&
    Number.isFinite(raw.payload.target_chapters)
  if (!hasValidPayload) {
    return null
  }
  const payload: ColdStartCreatePayload = { ...(raw.payload as ColdStartCreatePayload), novel_id: novelId }
  const rev =
    typeof raw.rev === 'number' && Number.isSafeInteger(raw.rev) && raw.rev >= 1 ? raw.rev : 1
  return {
    v: 1,
    rev,
    opId,
    novelId,
    novelConfirmed,
    payload,
    title,
    premise,
    chapterHint,
    chapter1Ensured: Boolean(raw.chapter1Ensured),
    chapter1HintSaved: Boolean(raw.chapter1HintSaved),
    savedAt: typeof raw.savedAt === 'number' && Number.isFinite(raw.savedAt) ? raw.savedAt : 0,
  }
}

export type ColdStartSlotClaimResult =
  | { acquired: true; record: ColdStartRecoveryRecord }
  | {
      acquired: false
      reason: 'conflict' | 'storage_failed' | 'abandoned'
      existing: ColdStartRecoveryRecord | null
    }

export type ColdStartCompletionResult =
  | { state: 'completed' }
  | { state: 'checkpoint_persisted_completion_failed'; record: ColdStartRecoveryRecord }
  | { state: 'checkpoint_write_failed' }
  | { state: 'lost_ownership' }

export async function withColdStartOperationLock<T>(
  opId: string,
  fn: (acquired: boolean) => T | Promise<T>,
  options?: { ifAvailable?: boolean },
): Promise<T> {
  const normalizedOpId = typeof opId === 'string' ? opId.trim() : ''
  if (!normalizedOpId) {
    throw new Error('立卷操作标识缺失，已中止执行')
  }
  const locks =
    typeof navigator !== 'undefined'
      ? (navigator as Navigator & {
          locks?: {
            request: <R>(
              name: string,
              optsOrCb:
                | { mode?: 'exclusive'; ifAvailable?: boolean }
                | ((lock: unknown) => R | Promise<R>),
              maybeCb?: (lock: unknown) => R | Promise<R>,
            ) => Promise<R>
          }
        }).locks
      : undefined
  if (!locks || typeof locks.request !== 'function') {
    throw new Error('当前环境不支持跨窗口操作互斥锁（Web Locks），为避免多窗口并发重复建书已中止')
  }
  const lockName = `plotpilot:cold-start-op-exec:${normalizedOpId}`
  let callbackEntered = false
  try {
    if (options?.ifAvailable) {
      return await locks.request(
        lockName,
        { mode: 'exclusive', ifAvailable: true },
        lock => {
          callbackEntered = true
          return fn(lock !== null && lock !== undefined)
        },
      )
    }
    return await locks.request(lockName, () => {
      callbackEntered = true
      return fn(true)
    })
  } catch (error) {
    if (callbackEntered) throw error
    throw new Error('无法获取跨窗口操作互斥锁（Web Locks），为避免多窗口并发重复建书已中止')
  }
}

export async function withColdStartStorageLock<T>(fn: () => T | Promise<T>): Promise<T> {
  const locks =
    typeof navigator !== 'undefined'
      ? (navigator as Navigator & {
          locks?: { request: <R>(name: string, cb: () => R | Promise<R>) => Promise<R> }
        }).locks
      : undefined
  if (!locks || typeof locks.request !== 'function') {
    throw new Error('当前环境不支持跨窗口存储互斥锁（Web Locks），为避免多窗口并发重复建书已中止')
  }
  let callbackEntered = false
  try {
    return await locks.request('plotpilot:cold-start-recovery:mutex', () => {
      callbackEntered = true
      return fn()
    })
  } catch (error) {
    if (callbackEntered) throw error
    throw new Error('无法获取跨窗口存储互斥锁（Web Locks），为避免多窗口并发重复建书已中止')
  }
}

function matchesExpectedRecordState(
  actual: ColdStartRecoveryRecord | null,
  expected: ColdStartRecoveryRecord,
): boolean {
  return Boolean(
    actual &&
      actual.rev === expected.rev &&
      actual.opId === expected.opId &&
      actual.novelId === expected.novelId &&
      actual.novelConfirmed === expected.novelConfirmed &&
      actual.title === expected.title &&
      actual.premise === expected.premise &&
      actual.chapterHint === expected.chapterHint &&
      actual.chapter1Ensured === expected.chapter1Ensured &&
      actual.chapter1HintSaved === expected.chapter1HintSaved &&
      actual.savedAt === expected.savedAt,
  )
}

export function claimColdStartRecoverySlot(
  record: ColdStartRecoveryRecord,
): ColdStartSlotClaimResult {
  if (!record.opId || isColdStartOpAbandoned(record.opId)) {
    return { acquired: false, reason: 'abandoned', existing: null }
  }
  const existing = readColdStartRecovery()
  if (existing && existing.opId !== record.opId) {
    return { acquired: false, reason: 'conflict', existing }
  }
  const initialRecord: ColdStartRecoveryRecord = {
    ...record,
    rev: Math.max(1, record.rev || 1),
  }
  writeStorageJson(COLD_START_RECOVERY_STORAGE_KEY, initialRecord)
  const verified = readColdStartRecovery()
  if (!verified) {
    return { acquired: false, reason: 'storage_failed', existing: null }
  }
  if (verified.opId !== initialRecord.opId) {
    return { acquired: false, reason: 'conflict', existing: verified }
  }
  if (!matchesExpectedRecordState(verified, initialRecord)) {
    return { acquired: false, reason: 'storage_failed', existing: verified }
  }
  return { acquired: true, record: verified }
}

export function advanceColdStartRecovery(
  expectedOpId: string,
  updater: (current: ColdStartRecoveryRecord) => ColdStartRecoveryRecord,
): ColdStartRecoveryRecord | null {
  if (!expectedOpId || isColdStartOpAbandoned(expectedOpId)) return null
  const current = readColdStartRecovery()
  if (!current || current.opId !== expectedOpId) {
    return null
  }
  const candidate = updater(current)
  if (!candidate || candidate.opId !== expectedOpId || isColdStartOpAbandoned(expectedOpId)) {
    return null
  }
  if (matchesExpectedRecordState(current, candidate)) {
    return current
  }
  const next: ColdStartRecoveryRecord = {
    ...candidate,
    rev: Math.max(current.rev + 1, candidate.rev),
    savedAt: Math.max(Date.now(), current.savedAt + 1, candidate.savedAt),
  }
  writeStorageJson(COLD_START_RECOVERY_STORAGE_KEY, next)
  const verified = readColdStartRecovery()
  if (!matchesExpectedRecordState(verified, next)) {
    return null
  }
  return verified
}

export function completeColdStartRecovery(
  expectedOpId: string,
  novelId: string,
): ColdStartCompletionResult {
  if (!expectedOpId || isColdStartOpAbandoned(expectedOpId)) {
    return { state: 'lost_ownership' }
  }
  const current = readColdStartRecovery()
  if (!current || current.opId !== expectedOpId || current.novelId !== novelId) {
    return { state: 'lost_ownership' }
  }
  const withHintSaved: ColdStartRecoveryRecord = {
    ...current,
    rev: current.rev + 1,
    novelConfirmed: true,
    chapter1Ensured: true,
    chapter1HintSaved: true,
    savedAt: Math.max(Date.now(), current.savedAt + 1),
  }
  writeStorageJson(COLD_START_RECOVERY_STORAGE_KEY, withHintSaved)
  const checkpointVerified = readColdStartRecovery()
  if (!checkpointVerified) {
    if (isWizardCompleted(novelId)) {
      removeStorageItem(COLD_START_RECOVERY_STORAGE_KEY)
      return { state: 'completed' }
    }
    return {
      state: isColdStartOpAbandoned(expectedOpId) ? 'lost_ownership' : 'checkpoint_write_failed',
    }
  }
  if (checkpointVerified.opId !== expectedOpId || checkpointVerified.novelId !== novelId) {
    return { state: 'lost_ownership' }
  }
  if (!matchesExpectedRecordState(checkpointVerified, withHintSaved)) {
    return { state: 'checkpoint_write_failed' }
  }
  markWizardCompleted(novelId)
  if (isWizardCompleted(novelId)) {
    removeStorageItem(COLD_START_RECOVERY_STORAGE_KEY)
    return { state: 'completed' }
  }
  const postMarkerVerified = readColdStartRecovery()
  if (postMarkerVerified && matchesExpectedRecordState(postMarkerVerified, withHintSaved)) {
    return { state: 'checkpoint_persisted_completion_failed', record: postMarkerVerified }
  }
  if (postMarkerVerified && postMarkerVerified.opId === expectedOpId) {
    return { state: 'checkpoint_write_failed' }
  }
  return { state: 'lost_ownership' }
}

export async function confirmColdStartNovelFromList(
  existingNovelIds: ReadonlySet<string>,
): Promise<void> {
  const peek = readColdStartRecovery()
  if (!peek || peek.novelConfirmed || !existingNovelIds.has(peek.novelId)) return
  const targetOpId = peek.opId
  try {
    await withColdStartOperationLock(
      targetOpId,
      async acquired => {
        if (!acquired) return
        const seedToVerify = await withColdStartStorageLock(() => {
          const current = readColdStartRecovery()
          if (!current || current.opId !== targetOpId || current.novelConfirmed) return null
          if (isColdStartOpAbandoned(targetOpId) || !existingNovelIds.has(current.novelId)) {
            return null
          }
          return current
        })
        if (!seedToVerify || isColdStartOpAbandoned(targetOpId)) return
        const probe = await probeNovelReconciliation(seedToVerify)
        if (probe.status !== 'matched' || isColdStartOpAbandoned(targetOpId)) return
        await withColdStartStorageLock(() => {
          const current = readColdStartRecovery()
          if (!current || current.opId !== targetOpId || current.novelConfirmed) return
          if (isColdStartOpAbandoned(targetOpId) || current.novelId !== seedToVerify.novelId) {
            return
          }
          advanceColdStartRecovery(current.opId, cur => ({
            ...cur,
            rev: cur.rev + 1,
            novelConfirmed: true,
            savedAt: Math.max(Date.now(), cur.savedAt + 1),
          }))
        })
      },
      { ifAvailable: true },
    )
  } catch {
    /* Leave unresolved creation intent intact if cross-tab Web Locks or identity verification fails. */
  }
}

export function clearColdStartRecovery(expectedNovelId?: string, expectedOpId?: string): boolean {
  const current = readStorageJson<Partial<ColdStartRecoveryRecord> | null>(
    COLD_START_RECOVERY_STORAGE_KEY,
    null,
  )
  if (expectedOpId) {
    recordAbandonedColdStartOp(expectedOpId)
  }
  if (!current) {
    return !expectedOpId || readAbandonedColdStartOps().includes(expectedOpId)
  }
  const currentNovelId = typeof current.novelId === 'string' ? current.novelId.trim() : ''
  const currentOpId =
    typeof current.opId === 'string' && current.opId.trim()
      ? current.opId.trim()
      : currentNovelId
        ? `legacy-${currentNovelId}`
        : ''
  if (expectedOpId && currentOpId && currentOpId !== expectedOpId) {
    return readAbandonedColdStartOps().includes(expectedOpId)
  }
  if (expectedNovelId && currentNovelId && currentNovelId !== expectedNovelId) {
    return !expectedOpId || readAbandonedColdStartOps().includes(expectedOpId)
  }
  const resolvedOpId = currentOpId || expectedOpId
  if (resolvedOpId) {
    recordAbandonedColdStartOp(resolvedOpId)
  }
  removeStorageItem(COLD_START_RECOVERY_STORAGE_KEY)
  const postRaw = readStorageJson<Partial<ColdStartRecoveryRecord> | null>(
    COLD_START_RECOVERY_STORAGE_KEY,
    null,
  )
  const postNovelId = typeof postRaw?.novelId === 'string' ? postRaw.novelId.trim() : ''
  const postOpId =
    typeof postRaw?.opId === 'string' && postRaw.opId.trim()
      ? postRaw.opId.trim()
      : postNovelId
        ? `legacy-${postNovelId}`
        : ''
  const removedFromSlot =
    !postRaw ||
    (expectedOpId ? postOpId !== expectedOpId : false) ||
    (expectedNovelId ? postNovelId !== expectedNovelId : false)
  const durableTombstone = Boolean(resolvedOpId && readAbandonedColdStartOps().includes(resolvedOpId))
  return removedFromSlot || durableTombstone
}
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { llmControlApi, promptPlazaApi, type LLMControlPanelData, type LocalGatewayItem } from '@/api/llmControl'
import { chapterApi } from '@/api/chapter'
import { novelApi } from '@/api/novel'
import { BUILTIN_CN_MARKET_V1, marketMajorThemeGenre, worldToneForSelection, writingProfileForSelection } from '@/domain/taxonomy/cnMarket'
import { pickLocaleLabel, type TaxonomyNode } from '@/domain/taxonomy/types'
import { CURATED_MOD_PACKS } from '@/domain/modPack/curatedPacks'
import { MOD_RECOMMENDED_MODEL_TIER_META, type NarrativeModPack } from '@/domain/modPack/types'
import { useAppSettingsShellStore } from '@/stores/appSettingsShellStore'
import { useModHubStore } from '@/stores/modHubStore'
import { formatApiError } from '@/utils/apiError'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'created', novelId: string): void
  (e: 'initialized', novelId: string): void
  (e: 'restore-focus'): void
}>()
const router = useRouter()
const settings = useAppSettingsShellStore()
const modHub = useModHubStore()
const stepLabels = ['第一步 · 模型与向量编组', '第二步 · 流派与叙事模组', '第三步 · 首章节拍与试写']
const defaultScaffold = '【起笔意象】以一处具象时辰、气候或器物细节切入，点出主角眼下的处境：\n【骤然失衡】一桩无法推脱的来客、旧账或异变逼近，迫使主角当场做出应对：\n【首章留钩】表面风波暂歇，却在末句动作或物件上翻出更深一层的悬念：'
const roots = BUILTIN_CN_MARKET_V1.roots
const rootId = ref(roots[0]?.id ?? '')
const leafId = ref(roots[0]?.children?.[0]?.id ?? '')
const selectedRoot = computed(() => roots.find(root => root.id === rootId.value) ?? roots[0])
const selectedLeaf = computed(() => selectedRoot.value?.children?.find(leaf => leaf.id === leafId.value) ?? selectedRoot.value?.children?.[0] ?? selectedRoot.value)
const step = ref(0)
const furthestStep = ref(0)
const title = ref('')
const premise = ref(defaultScaffold)
const premiseEdited = ref(false)
const selectedIds = ref<string[]>([])
const selectedPacks = computed(() => selectedIds.value.flatMap(id => { const pack = CURATED_MOD_PACKS.find(item => item.id === id); return pack ? [pack] : [] }))
const fullScaffold = computed(() => selectedPacks.value.find(pack => pack.openingBeatTemplate?.trim())?.openingBeatTemplate?.trim() || defaultScaffold)
const sourceScaffold = computed(() => fullScaffold.value.slice(0, 2000))
const scaffoldTruncated = computed(() => fullScaffold.value.length > 2000)
const effectivePacks = computed(() => {
  const packs = new Map<string, NarrativeModPack>(modHub.installedList.map(record => {
    const curated = CURATED_MOD_PACKS.find(pack => pack.id === record.pack.id)
    return [record.pack.id, { ...curated, ...record.pack, reviewRedlines: record.pack.reviewRedlines ?? curated?.reviewRedlines, antiAiWordlist: record.pack.antiAiWordlist ?? curated?.antiAiWordlist }]
  }))
  for (const pack of selectedPacks.value) packs.set(pack.id, pack)
  return [...packs.values()]
})
const redlineCount = computed(() => effectivePacks.value.reduce((n, pack) => n + (pack.reviewRedlines?.length ?? 0), 0))
const wordCount = computed(() => effectivePacks.value.reduce((n, pack) => n + (pack.antiAiWordlist?.length ?? 0), 0))
const panel = ref<LLMControlPanelData | null>(null)
const runtimeReady = computed(() => Boolean(panel.value && !panel.value.runtime.using_mock && panel.value.runtime.model))
const currentRoleModels = computed(() => {
  if (!panel.value) return []
  const config = panel.value.config
  return (['main', 'cheap', 'kg'] as const).map(role => {
    const id = config.endpoint_mode === 'independent' ? config.role_bindings?.[role] || config.active_profile_id : config.active_profile_id
    const profile = config.profiles.find(item => item.id === id)
    return `${role}：${profile?.model || panel.value?.runtime.model || '待配置'}`
  })
})
const tierMismatch = computed(() => selectedPacks.value.some(pack => pack.recommendedModelTier === 'flagship') && /flash|mini|haiku|lite/i.test(panel.value?.runtime.model ?? ''))
const gateways = ref<LocalGatewayItem[]>([])
const reachableGateways = computed(() => gateways.value.filter(gateway => gateway.reachable))
const busy = ref(false)
const panelLoading = ref(false)
const probed = ref(false)
const submitting = ref(false)
const abandoning = ref(false)
const errorText = ref('')
const oauthNotice = ref('')
const oauthUrl = ref('')
const maskRef = ref<HTMLElement | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
const closeRef = ref<HTMLButtonElement | null>(null)
const bodyRef = ref<HTMLElement | null>(null)
const activeOpId = ref('')
const createdNovelId = ref('')
const novelConfirmed = ref(false)
const recoveryLocked = computed(() => Boolean(activeOpId.value && createdNovelId.value))
let epoch = 0
let panelEpoch = 0
let busyEpoch = 0
let submitEpoch = 0
let abandonEpoch = 0
let controller: AbortController | null = null
let openReconcileController: AbortController | null = null
let openReconcilePromise: Promise<void> | null = null
let opener: HTMLElement | null = null
let inertNodes: Array<{ el: HTMLElement; inert: boolean }> = []
const emittedCreatedOps = new Set<string>()
let chapter1Ensured = false
let chapter1HintSaved = false
let unmounted = false
let committedSeed: ColdStartRecoveryRecord | null = null
const valid = (requestEpoch: number) => !unmounted && props.show && requestEpoch === epoch
const panelValid = (requestPanelEpoch: number) =>
  !unmounted && props.show && requestPanelEpoch === panelEpoch
const submissionValid = (
  requestEpoch: number,
  requestSubmitEpoch: number,
  expectedOpId?: string,
) =>
  valid(requestEpoch) &&
  requestSubmitEpoch === submitEpoch &&
  (!expectedOpId || (activeOpId.value === expectedOpId && !isColdStartOpAbandoned(expectedOpId)))

function emitCreatedOnce(
  opId: string,
  novelId: string,
  requestEpoch: number,
  requestSubmitEpoch: number,
  canEmit?: () => boolean,
): boolean {
  if (!opId || !novelId || !submissionValid(requestEpoch, requestSubmitEpoch, opId)) return false
  if (canEmit && !canEmit()) return false
  if (!emittedCreatedOps.has(opId)) {
    emittedCreatedOps.add(opId)
    emit('created', novelId)
  }
  return submissionValid(requestEpoch, requestSubmitEpoch, opId) && (!canEmit || canEmit())
}

function emitInitializedIfValid(
  opId: string,
  novelId: string,
  requestEpoch: number,
  requestSubmitEpoch: number,
): boolean {
  if (!novelId || !submissionValid(requestEpoch, requestSubmitEpoch, opId || undefined)) return false
  emit('initialized', novelId)
  return submissionValid(requestEpoch, requestSubmitEpoch, opId || undefined)
}

function resetDraftScaffold(): void {
  premiseEdited.value = false
  premise.value = sourceScaffold.value
}

function cancelOpenReconcile(): void {
  openReconcileController?.abort()
  openReconcileController = null
}

function adoptRecoveryRecord(recovery: ColdStartRecoveryRecord, requestEpoch: number): void {
  cancelOpenReconcile()
  activeOpId.value = recovery.opId
  createdNovelId.value = recovery.novelId
  novelConfirmed.value = recovery.novelConfirmed
  if (recovery.novelConfirmed) {
    emittedCreatedOps.add(recovery.opId)
  }
  chapter1Ensured = recovery.chapter1Ensured
  chapter1HintSaved = recovery.chapter1HintSaved
  title.value = recovery.title
  premise.value = recovery.premise || recovery.chapterHint
  premiseEdited.value = true
  committedSeed = recovery
  step.value = 2
  furthestStep.value = 2
  if (!recovery.novelConfirmed) {
    const requestSubmitEpoch = submitEpoch
    const runPromise = reconcilePendingRecoveryOnOpen(recovery, requestEpoch, requestSubmitEpoch)
    openReconcilePromise = runPromise.finally(() => {
      if (openReconcilePromise === runPromise) {
        openReconcilePromise = null
      }
    })
  }
}

async function reconcilePendingRecoveryOnOpen(
  seedSnapshot: ColdStartRecoveryRecord,
  requestEpoch: number,
  requestSubmitEpoch: number,
): Promise<void> {
  const opId = seedSnapshot.opId
  const reconcileController = new AbortController()
  openReconcileController = reconcileController
  const canContinueReconcile = () =>
    !reconcileController.signal.aborted &&
    submissionValid(requestEpoch, requestSubmitEpoch, opId) &&
    !submitting.value &&
    !abandoning.value
  if (!canContinueReconcile()) return
  try {
    await withColdStartOperationLock(
      opId,
      async acquired => {
        if (!acquired || !canContinueReconcile()) return
        const authoritative = await withColdStartStorageLock(() => {
          if (!canContinueReconcile()) return null
          const current = readColdStartRecovery()
          if (!current || current.opId !== opId || isColdStartOpAbandoned(opId)) return null
          return current
        })
        if (!authoritative || !canContinueReconcile()) return
        if (authoritative.novelConfirmed) {
          if (
            !emitCreatedOnce(
              opId,
              authoritative.novelId,
              requestEpoch,
              requestSubmitEpoch,
              canContinueReconcile,
            )
          ) {
            return
          }
          novelConfirmed.value = true
          createdNovelId.value = authoritative.novelId
          chapter1Ensured = authoritative.chapter1Ensured
          chapter1HintSaved = authoritative.chapter1HintSaved
          committedSeed = authoritative
          return
        }
        const probe = await probeNovelReconciliation(authoritative, reconcileController.signal)
        if (probe.status !== 'matched' || !canContinueReconcile()) return
        const advanced = await withColdStartStorageLock(() =>
          advanceColdStartRecovery(opId, cur =>
            cur.novelConfirmed
              ? cur
              : {
                  ...cur,
                  rev: cur.rev + 1,
                  novelConfirmed: true,
                  savedAt: Math.max(Date.now(), cur.savedAt + 1),
                },
          ),
        )
        if (
          !advanced ||
          !emitCreatedOnce(
            opId,
            advanced.novelId,
            requestEpoch,
            requestSubmitEpoch,
            canContinueReconcile,
          )
        ) {
          return
        }
        novelConfirmed.value = true
        createdNovelId.value = advanced.novelId
        chapter1Ensured = advanced.chapter1Ensured
        chapter1HintSaved = advanced.chapter1HintSaved
        committedSeed = advanced
      },
      { ifAvailable: true },
    )
  } catch {
    /* Leave unresolved creation intent intact for explicit retry reconciliation. */
  } finally {
    if (openReconcileController === reconcileController) {
      openReconcileController = null
    }
  }
}

function selectRoot(root: TaxonomyNode) { if (submitting.value || abandoning.value || recoveryLocked.value) return; rootId.value = root.id; leafId.value = root.children?.[0]?.id ?? root.id }
function togglePack(id: string) { if (submitting.value || abandoning.value || recoveryLocked.value) return; selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id] }
function restoreScaffold() { if (submitting.value || abandoning.value || recoveryLocked.value) return; resetDraftScaffold() }
async function abandonRecovery() {
  if (submitting.value || busy.value || abandoning.value || !recoveryLocked.value) return
  cancelOpenReconcile()
  const targetNovelId = createdNovelId.value
  const targetOpId = activeOpId.value
  let expectedSessionEpoch = epoch
  const requestAbandonEpoch = ++abandonEpoch
  abandoning.value = true
  errorText.value = ''
  try {
    const outcome = await withColdStartStorageLock(() => {
      const cleared = clearColdStartRecovery(targetNovelId, targetOpId)
      const remaining = readColdStartRecovery()
      return { cleared, remaining }
    })
    if (!valid(expectedSessionEpoch) || requestAbandonEpoch !== abandonEpoch || activeOpId.value !== targetOpId) return
    if (!outcome.cleared) {
      errorText.value = '无法清除本地恢复记录，请检查浏览器存储权限后重试'
      return
    }
    epoch += 1
    expectedSessionEpoch = epoch
    submitEpoch += 1
    abandoning.value = false
    if (outcome.remaining && outcome.remaining.opId !== targetOpId) {
      adoptRecoveryRecord(outcome.remaining, expectedSessionEpoch)
      errorText.value = `另一窗口已切换至未完立卷《${outcome.remaining.title}》，已同步最新状态`
      void nextTick(() => bodyRef.value?.focus())
      return
    }
    activeOpId.value = ''
    createdNovelId.value = ''
    novelConfirmed.value = false
    committedSeed = null
    chapter1Ensured = false
    chapter1HintSaved = false
    title.value = ''
    step.value = 1
    furthestStep.value = 1
    resetDraftScaffold()
    void nextTick(() => bodyRef.value?.focus())
  } catch (error) {
    if (valid(expectedSessionEpoch) && requestAbandonEpoch === abandonEpoch) {
      errorText.value = formatApiError(error, '无法清除本地恢复记录，请检查浏览器权限后重试')
    }
  } finally {
    if (valid(expectedSessionEpoch) && requestAbandonEpoch === abandonEpoch) {
      abandoning.value = false
    }
  }
}
watch(sourceScaffold, scaffold => { if (!premiseEdited.value && !submitting.value && !abandoning.value && !recoveryLocked.value) premise.value = scaffold })
function goStep(value: number) { if (submitting.value || busy.value || abandoning.value || (recoveryLocked.value && value !== 2)) return; step.value = value; furthestStep.value = Math.max(furthestStep.value, value); void nextTick(() => bodyRef.value?.focus()) }
function skipPacks() { if (submitting.value || abandoning.value || recoveryLocked.value) return; selectedIds.value = selectedIds.value.filter(id => modHub.isInstalled(id)); goStep(2) }
function close() { if (!submitting.value && !abandoning.value) emit('update:show', false) }
async function openEngine() { close(); await nextTick(); settings.open('engine') }
async function refreshPanel() {
  const requestPanelEpoch = ++panelEpoch
  controller?.abort()
  controller = new AbortController()
  panelLoading.value = true
  try {
    const result = await llmControlApi.getPanel(controller.signal)
    if (panelValid(requestPanelEpoch)) panel.value = result
  } catch (error) {
    if (panelValid(requestPanelEpoch)) errorText.value = formatApiError(error, '暂未读取到模型配置，可先立卷后再配置')
  } finally { if (panelValid(requestPanelEpoch)) panelLoading.value = false }
}
async function operation(action: (requestEpoch: number) => Promise<void>) {
  if (busy.value || submitting.value || abandoning.value) return
  const requestEpoch = epoch
  const requestBusyEpoch = ++busyEpoch
  busy.value = true
  errorText.value = ''
  try { await action(requestEpoch) }
  catch (error) { if (valid(requestEpoch) && requestBusyEpoch === busyEpoch) errorText.value = formatApiError(error, '连接未完成，请重试或打开完整模型设置') }
  finally { if (!unmounted && props.show && requestBusyEpoch === busyEpoch) busy.value = false }
}
async function probe() {
  await operation(async requestEpoch => {
    const result = await llmControlApi.probeLocalGateways()
    if (!valid(requestEpoch)) return
    gateways.value = result.gateways
    probed.value = true
  })
}
async function connect(gateway: LocalGatewayItem) {
  await operation(async requestEpoch => {
    const roles = gateway.recommended_roles
    const mainModel = roles.main || gateway.models[0] || ''
    if (!mainModel) throw new Error('该网关尚未返回可用模型')
    await llmControlApi.connectLocalGateway({ base_url: gateway.base_url, name: gateway.name, main_model: mainModel, cheap_model: roles.cheap || mainModel, kg_model: roles.kg || roles.cheap || mainModel, enable_golden_roles: true })
    if (valid(requestEpoch)) await refreshPanel()
  })
}
async function authorize() {
  await operation(async requestEpoch => {
    const result = await llmControlApi.startOpenRouterOAuth()
    if (!valid(requestEpoch)) return
    let safeAuthorizeUrl = ''
    try {
      const parsed = new URL(result.authorize_url)
      if (parsed.protocol === 'https:') safeAuthorizeUrl = parsed.toString()
    } catch {
      safeAuthorizeUrl = ''
    }
    if (!safeAuthorizeUrl) throw new Error('授权地址校验未通过，请打开完整模型设置连接')
    oauthUrl.value = safeAuthorizeUrl
    window.open(safeAuthorizeUrl, '_blank', 'noopener,noreferrer')
    oauthNotice.value = '请在授权页完成连接，返回后刷新连接状态；未弹出新页时可使用下方链接。'
  })
}
function transitionOnConflictAdoption(
  other: ColdStartRecoveryRecord,
  message: string,
  requestEpoch: number,
  requestSubmitEpoch: number,
): void {
  if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch) return
  cancelOpenReconcile()
  submitEpoch += 1
  submitting.value = false
  adoptRecoveryRecord(other, requestEpoch)
  errorText.value = message
  void nextTick(() => bodyRef.value?.focus())
}
function transitionOnOperationAbandoned(
  targetOpId: string,
  requestEpoch: number,
  requestSubmitEpoch: number,
): void {
  if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch) return
  if (activeOpId.value && activeOpId.value !== targetOpId) return
  cancelOpenReconcile()
  epoch += 1
  const nextEpoch = epoch
  submitEpoch += 1
  submitting.value = false
  errorText.value = ''
  const remaining = readColdStartRecovery()
  if (remaining && remaining.opId !== targetOpId) {
    adoptRecoveryRecord(remaining, nextEpoch)
    errorText.value = `另一窗口已切换至未完立卷《${remaining.title}》，已同步最新状态`
    void nextTick(() => bodyRef.value?.focus())
    return
  }
  activeOpId.value = ''
  createdNovelId.value = ''
  novelConfirmed.value = false
  committedSeed = null
  chapter1Ensured = false
  chapter1HintSaved = false
  title.value = ''
  step.value = 1
  furthestStep.value = 1
  resetDraftScaffold()
  void nextTick(() => bodyRef.value?.focus())
}
async function finishExternallyCompletedNovel(
  opId: string,
  novelId: string,
  enterWorkbench: boolean,
  requestEpoch: number,
  requestSubmitEpoch: number,
): Promise<void> {
  if (!emitInitializedIfValid(opId, novelId, requestEpoch, requestSubmitEpoch)) {
    if (opId && isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    }
    return
  }
  const shouldEnterWorkbench =
    enterWorkbench && submissionValid(requestEpoch, requestSubmitEpoch, opId || undefined)
  submitEpoch += 1
  submitting.value = false
  emit('update:show', false)
  if (shouldEnterWorkbench && !unmounted && (!opId || !isColdStartOpAbandoned(opId))) {
    try {
      await router.push({
        path: `/book/${novelId}/workbench`,
        query: { chapter: '1', mode: 'assisted' },
      })
    } catch {
      /* The initialized book remains available on Home. */
    }
  }
}
async function handleLostOrFailedAdvancement(
  opId: string,
  novelId: string,
  enterWorkbench: boolean,
  requestEpoch: number,
  requestSubmitEpoch: number,
  storageFailureMessage: string,
): Promise<void> {
  if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch || activeOpId.value !== opId) return
  if (isColdStartOpAbandoned(opId)) {
    transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    return
  }
  const current = await withColdStartStorageLock(() => readColdStartRecovery())
  if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch || activeOpId.value !== opId) return
  if (isColdStartOpAbandoned(opId)) {
    transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    return
  }
  if (current && current.opId !== opId) {
    transitionOnConflictAdoption(
      current,
      `检测到另一窗口已切换至《${current.title}》，已载入最新记录；请核对后再继续`,
      requestEpoch,
      requestSubmitEpoch,
    )
    return
  }
  if (!current && novelId && isWizardCompleted(novelId)) {
    await finishExternallyCompletedNovel(
      opId,
      novelId,
      enterWorkbench,
      requestEpoch,
      requestSubmitEpoch,
    )
    return
  }
  if (!current) {
    transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    return
  }
  throw new Error(storageFailureMessage)
}
async function ensureActiveSlotOwnership(
  opId: string,
  novelId: string,
  enterWorkbench: boolean,
  requestEpoch: number,
  requestSubmitEpoch: number,
): Promise<boolean> {
  if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) {
    if (isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    }
    return false
  }
  const current = await withColdStartStorageLock(() => readColdStartRecovery())
  if (current && current.opId === opId && !isColdStartOpAbandoned(opId)) {
    return submissionValid(requestEpoch, requestSubmitEpoch, opId)
  }
  await handleLostOrFailedAdvancement(
    opId,
    novelId,
    enterWorkbench,
    requestEpoch,
    requestSubmitEpoch,
    '本地恢复记录状态异常，请刷新后重试',
  )
  return false
}
async function dispatchCreateWithReconcile(
  opId: string,
  seed: ColdStartRecoveryRecord,
  enterWorkbench: boolean,
  requestEpoch: number,
  requestSubmitEpoch: number,
): Promise<ColdStartRecoveryRecord | null> {
  if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) {
    if (isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    }
    return null
  }
  let created: unknown
  try {
    created = await novelApi.createNovel(seed.payload)
  } catch (createError) {
    if (isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
      return null
    }
    if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) {
      return null
    }
    const createStatus = (createError as { response?: { status?: number } } | null)?.response?.status
    if (createStatus === 409) {
      throw new Error(
        '服务端已存在同编号但属性冲突的书目记录（HTTP 409），为避免覆盖已中止；请回书架核对或放弃草稿重开',
      )
    }
    let probe: NovelReconcileProbeResult = { status: 'missing' }
    try {
      probe = await probeNovelReconciliation(seed)
    } catch {
      probe = { status: 'missing' }
    }
    if (isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
      return null
    }
    if (probe.status === 'matched') {
      const advanced = await withColdStartStorageLock(() =>
        advanceColdStartRecovery(opId, cur => ({
          ...cur,
          rev: cur.rev + 1,
          novelConfirmed: true,
          savedAt: Math.max(Date.now(), cur.savedAt + 1),
        })),
      )
      if (!advanced) {
        await handleLostOrFailedAdvancement(
          opId,
          seed.novelId,
          enterWorkbench,
          requestEpoch,
          requestSubmitEpoch,
          '服务端已建立书目，但本地恢复记录未能更新；请检查浏览器存储权限后重试',
        )
        return null
      }
      if (!emitCreatedOnce(opId, seed.novelId, requestEpoch, requestSubmitEpoch)) {
        if (isColdStartOpAbandoned(opId)) {
          transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
        }
        return null
      }
      novelConfirmed.value = true
      committedSeed = advanced
      return advanced
    }
    if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) {
      return null
    }
    if (probe.status === 'conflict') {
      throw new Error(
        '服务端已存在同编号但内容或预设不同的书目记录，为避免覆盖已暂停；请回书架核对或放弃草稿重开',
      )
    }
    if (probe.status === 'unverifiable') {
      throw new Error(
        '立卷响应未获确认，且服务端返回详情字段不完整无法核验身份；请稍后重试或回书架核对',
      )
    }
    throw new Error(
      `立卷响应未获确认：${formatApiError(createError, '可点击下方按钮核对服务端状态并续接，或放弃草稿重开')}`,
    )
  }

  if (isColdStartOpAbandoned(opId)) {
    transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    return null
  }
  const returnedId =
    created && typeof created === 'object' ? (created as { id?: unknown }).id : undefined
  if (typeof returnedId === 'string' && returnedId.length > 0 && returnedId !== seed.novelId) {
    if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) return null
    throw new Error(
      '服务端返回的书目编号与当前立卷草稿不一致，为避免误写既有书目已中止；请回书架核对或放弃草稿重开',
    )
  }
  if (!hasVerifiableNovelIdentityShape(created)) {
    if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) return null
    throw new Error(
      '立卷响应缺少必要身份校验字段，为避免误写未确认书目已暂停；请点击重试核对服务端状态',
    )
  }
  if (!matchesSeedNovelIdentity(created, seed)) {
    if (!submissionValid(requestEpoch, requestSubmitEpoch, opId)) return null
    throw new Error(
      '服务端返回的书目预设属性与当前立卷草稿不一致，为避免误写既有书目已中止；请回书架核对或放弃草稿重开',
    )
  }
  const resolvedId = created.id
  const advanced = await withColdStartStorageLock(() =>
    advanceColdStartRecovery(opId, cur => ({
      ...cur,
      rev: cur.rev + 1,
      novelId: resolvedId,
      payload: { ...cur.payload, novel_id: resolvedId },
      novelConfirmed: true,
      savedAt: Math.max(Date.now(), cur.savedAt + 1),
    })),
  )
  if (!advanced) {
    await handleLostOrFailedAdvancement(
      opId,
      resolvedId,
      enterWorkbench,
      requestEpoch,
      requestSubmitEpoch,
      '立卷已返回，但本地恢复记录未能更新；请检查浏览器存储权限或刷新书架核对',
    )
    return null
  }
  if (!emitCreatedOnce(opId, resolvedId, requestEpoch, requestSubmitEpoch)) {
    if (isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    }
    return null
  }
  novelConfirmed.value = true
  createdNovelId.value = resolvedId
  committedSeed = advanced
  return advanced
}
async function executeLockedOperationPipeline(
  targetOpId: string,
  initialSeed: ColdStartRecoveryRecord,
  isFreshClaim: boolean,
  enterWorkbench: boolean,
  requestEpoch: number,
  requestSubmitEpoch: number,
): Promise<void> {
  let seed: ColdStartRecoveryRecord = initialSeed
  if (isFreshClaim) {
    const confirmed = await dispatchCreateWithReconcile(
      targetOpId,
      seed,
      enterWorkbench,
      requestEpoch,
      requestSubmitEpoch,
    )
    if (!confirmed) return
    seed = confirmed
  } else if (!seed.novelConfirmed) {
    if (
      !(await ensureActiveSlotOwnership(
        targetOpId,
        seed.novelId,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
      ))
    ) {
      return
    }
    let probe: NovelReconcileProbeResult
    try {
      probe = await probeNovelReconciliation(seed)
    } catch (probeError) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
        return
      }
      throw new Error(
        `未能核对书目是否已在服务端落盘，为避免重复建书已暂停：${formatApiError(probeError, '请待连接恢复后重试')}`,
      )
    }
    if (isColdStartOpAbandoned(targetOpId)) {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      return
    }
    if (probe.status === 'matched') {
      const advanced = await withColdStartStorageLock(() =>
        advanceColdStartRecovery(targetOpId, cur => ({
          ...cur,
          rev: cur.rev + 1,
          novelConfirmed: true,
          savedAt: Math.max(Date.now(), cur.savedAt + 1),
        })),
      )
      if (!advanced) {
        await handleLostOrFailedAdvancement(
          targetOpId,
          seed.novelId,
          enterWorkbench,
          requestEpoch,
          requestSubmitEpoch,
          '未能更新本地立卷确认状态，请检查浏览器存储权限后重试',
        )
        return
      }
      if (!emitCreatedOnce(targetOpId, seed.novelId, requestEpoch, requestSubmitEpoch)) {
        if (isColdStartOpAbandoned(targetOpId)) {
          transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
        }
        return
      }
      seed = advanced
      novelConfirmed.value = true
      createdNovelId.value = advanced.novelId
      committedSeed = seed
    } else {
      if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) return
      if (probe.status === 'conflict') {
        throw new Error(
          '服务端已存在同编号但内容或预设不同的书目记录，为避免覆盖已暂停；请回书架核对或放弃草稿重开',
        )
      }
      if (probe.status === 'unverifiable') {
        throw new Error(
          '服务端返回书目详情字段不完整，无法核验立卷身份，为避免误写已暂停；请刷新后重试',
        )
      }
      if (
        !(await ensureActiveSlotOwnership(
          targetOpId,
          seed.novelId,
          enterWorkbench,
          requestEpoch,
          requestSubmitEpoch,
        ))
      ) {
        return
      }
      const confirmed = await dispatchCreateWithReconcile(
        targetOpId,
        seed,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
      )
      if (!confirmed) return
      seed = confirmed
    }
  } else if (!chapter1Ensured || !chapter1HintSaved) {
    if (
      !(await ensureActiveSlotOwnership(
        targetOpId,
        seed.novelId,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
      ))
    ) {
      return
    }
    let confirmedProbe: NovelReconcileProbeResult
    try {
      confirmedProbe = await probeNovelReconciliation(seed)
    } catch (probeError) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
        return
      }
      throw new Error(
        `未能核验服务端书目立卷身份，为避免误写已暂停：${formatApiError(probeError, '请待连接恢复后重试')}`,
      )
    }
    if (isColdStartOpAbandoned(targetOpId)) {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      return
    }
    if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) return
    if (confirmedProbe.status === 'conflict') {
      throw new Error(
        '服务端已存在同编号但内容或预设不同的书目记录，为避免覆盖已暂停；请回书架核对或放弃草稿重开',
      )
    }
    if (confirmedProbe.status !== 'matched') {
      throw new Error(
        '未能确认服务端书目与当前待恢复草稿一致，为避免误写已暂停；请回书架核对或放弃草稿重开',
      )
    }
  }
  if (!chapter1Ensured) {
    if (
      !(await ensureActiveSlotOwnership(
        targetOpId,
        seed.novelId,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
      ))
    ) {
      return
    }
    try {
      await chapterApi.ensureChapter(seed.novelId, 1, '第一章 起笔')
    } catch (error) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
        return
      }
      throw new Error(`书目已建立，但首章创建未完成：${formatApiError(error, '请点击重试完成首章初始化')}`)
    }
    if (isColdStartOpAbandoned(targetOpId)) {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      return
    }
    const advanced = await withColdStartStorageLock(() =>
      advanceColdStartRecovery(targetOpId, cur => ({
        ...cur,
        rev: cur.rev + 1,
        novelConfirmed: true,
        chapter1Ensured: true,
        savedAt: Math.max(Date.now(), cur.savedAt + 1),
      })),
    )
    if (!advanced) {
      await handleLostOrFailedAdvancement(
        targetOpId,
        seed.novelId,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
        '首章已创建，但本地恢复进度未能写入；请检查存储空间后点击重试继续',
      )
      return
    }
    if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      }
      return
    }
    chapter1Ensured = true
    seed = advanced
    committedSeed = seed
  }
  if (!chapter1HintSaved) {
    if (
      !(await ensureActiveSlotOwnership(
        targetOpId,
        seed.novelId,
        enterWorkbench,
        requestEpoch,
        requestSubmitEpoch,
      ))
    ) {
      return
    }
    try {
      await chapterApi.updateGenerationHint(seed.novelId, 1, seed.chapterHint)
    } catch (error) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
        return
      }
      throw new Error(`首章已建立，但开篇节拍尚未写入：${formatApiError(error, '请点击重试保存首章引子')}`)
    }
    if (isColdStartOpAbandoned(targetOpId)) {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      return
    }
  }
  const finalNovelId = seed.novelId
  const completionResult = await withColdStartStorageLock(() =>
    completeColdStartRecovery(targetOpId, finalNovelId),
  )
  if (completionResult.state === 'lost_ownership') {
    await handleLostOrFailedAdvancement(
      targetOpId,
      finalNovelId,
      enterWorkbench,
      requestEpoch,
      requestSubmitEpoch,
      '本地恢复记录已变更，请核对后再操作',
    )
    return
  }
  if (completionResult.state === 'checkpoint_write_failed') {
    if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      }
      return
    }
    throw new Error('首章引子已发送，但本地恢复检查点未能写入；请检查浏览器存储空间或权限后重试')
  }
  if (completionResult.state === 'checkpoint_persisted_completion_failed') {
    if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) {
      if (isColdStartOpAbandoned(targetOpId)) {
        transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      }
      return
    }
    chapter1HintSaved = true
    committedSeed = completionResult.record
    throw new Error(
      '首章引子检查点已保存，但完成标记未能写入；请释放浏览器存储空间后点击重试完成确认',
    )
  }
  if (!emitInitializedIfValid(targetOpId, finalNovelId, requestEpoch, requestSubmitEpoch)) {
    if (isColdStartOpAbandoned(targetOpId)) {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
    }
    return
  }
  chapter1HintSaved = true
  const shouldEnterWorkbench =
    enterWorkbench && submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)
  submitEpoch += 1
  submitting.value = false
  emit('update:show', false)
  if (shouldEnterWorkbench && !unmounted && !isColdStartOpAbandoned(targetOpId)) {
    try {
      await router.push({
        path: `/book/${finalNovelId}/workbench`,
        query: { chapter: '1', mode: 'assisted' },
      })
    } catch {
      /* The initialized book remains available on Home. */
    }
  }
}
async function submit(enterWorkbench: boolean) {
  if (submitting.value || busy.value || abandoning.value) return
  const requestEpoch = epoch
  const requestSubmitEpoch = ++submitEpoch
  let opId = activeOpId.value
  let freshSnapshot: {
    opId: string
    packsToSelect: NarrativeModPack[]
    initialRecord: ColdStartRecoveryRecord
  } | null = null
  if (!recoveryLocked.value) {
    const trimmedPremise = premise.value.trim()
    if (!trimmedPremise) { errorText.value = '请先填写首章节拍与梗概'; return }
    const root = selectedRoot.value, leaf = selectedLeaf.value
    if (!root || !leaf) { errorText.value = '请先选择题材大类与主题'; return }
    const genre = marketMajorThemeGenre(root, leaf) || pickLocaleLabel(root) || '原创故事'
    const profile = writingProfileForSelection(root, leaf)
    const resolvedTitle = title.value.trim() || `${pickLocaleLabel(leaf)}新卷`
    const nextOpId = createColdStartOpId()
    const nextNovelId = createColdStartNovelId()
    const chapterHint = trimmedPremise.slice(0, 1200)
    const payload: ColdStartCreatePayload = {
      novel_id: nextNovelId,
      title: resolvedTitle,
      author: '作者',
      premise: trimmedPremise,
      genre,
      world_preset: worldToneForSelection(root, leaf) || genre,
      story_structure: profile.story_structure?.trim() || '围绕主角目标，以选择推动冲突与结果，逐章兑现伏笔。',
      pacing_control: profile.pacing_control?.trim() || '舒展场景与冲突交替，每章推进一项实质变化。',
      writing_style: profile.writing_style?.trim() || '具体、克制，以可见动作和自然对话呈现人物。',
      special_requirements: profile.special_requirements?.trim() || '保持人物动机、知情范围与前文事实一致。',
      length_tier: 'standard',
      target_chapters: 0,
    }
    freshSnapshot = {
      opId: nextOpId,
      packsToSelect: [...selectedPacks.value],
      initialRecord: {
        v: 1,
        rev: 1,
        opId: nextOpId,
        novelId: nextNovelId,
        novelConfirmed: false,
        payload,
        title: resolvedTitle,
        premise: trimmedPremise,
        chapterHint,
        chapter1Ensured: false,
        chapter1HintSaved: false,
        savedAt: Date.now(),
      },
    }
  }
  submitting.value = true
  errorText.value = ''
  const pendingOpenReconcile = openReconcilePromise
  cancelOpenReconcile()
  try {
    if (pendingOpenReconcile) {
      await pendingOpenReconcile.catch(() => {})
      if (!submissionValid(requestEpoch, requestSubmitEpoch)) return
    }
    if (!recoveryLocked.value && freshSnapshot) {
      const preExisting = await withColdStartStorageLock(() => readColdStartRecovery())
      if (!submissionValid(requestEpoch, requestSubmitEpoch)) return
      if (preExisting) {
        transitionOnConflictAdoption(
          preExisting,
          `检测到另一窗口已有未完立卷《${preExisting.title}》，已载入该记录；请先核对完成或放弃后再新建`,
          requestEpoch,
          requestSubmitEpoch,
        )
        return
      }
      const missing = freshSnapshot.packsToSelect.filter(pack => !modHub.isInstalled(pack.id))
      if (missing.length) {
        const nodes = await promptPlazaApi.listNodes()
        if (!submissionValid(requestEpoch, requestSubmitEpoch)) return
        for (const pack of missing) {
          if (!modHub.isInstalled(pack.id)) {
            try { await modHub.installModPack(pack, nodes) }
            catch (error) { throw new Error(`模组「${pack.name}」未能安装，尚未创建书目。${formatApiError(error, '请重试')}`) }
          }
          if (!submissionValid(requestEpoch, requestSubmitEpoch)) return
        }
      }
      if (!submissionValid(requestEpoch, requestSubmitEpoch)) return
      const snapshotRecord = freshSnapshot.initialRecord
      const freshOutcome = await withColdStartOperationLock(
        freshSnapshot.opId,
        async (acquired): Promise<{ conflict: ColdStartRecoveryRecord | null }> => {
          if (!acquired) {
            throw new Error('当前立卷操作正在其他上下文执行，请勿重复提交')
          }
          const claimResult = await withColdStartStorageLock((): ColdStartSlotClaimResult | null => {
            if (!submissionValid(requestEpoch, requestSubmitEpoch)) return null
            return claimColdStartRecoverySlot(snapshotRecord)
          })
          if (!claimResult) return { conflict: null }
          if (!claimResult.acquired) {
            if (!submissionValid(requestEpoch, requestSubmitEpoch)) return { conflict: null }
            if (claimResult.reason === 'conflict' && claimResult.existing) {
              return { conflict: claimResult.existing }
            }
            if (claimResult.reason === 'storage_failed') {
              throw new Error(
                '无法持久化立卷恢复记录，为避免断线重复建书已中止；请检查浏览器本地存储空间或权限后重试',
              )
            }
            return { conflict: null }
          }
          if (!submissionValid(requestEpoch, requestSubmitEpoch)) {
            try {
              await withColdStartStorageLock(() =>
                clearColdStartRecovery(claimResult.record.novelId, claimResult.record.opId),
              )
            } catch {
              /* Best-effort cleanup of undispatched slot if closed during lock release. */
            }
            return { conflict: null }
          }
          opId = claimResult.record.opId
          activeOpId.value = opId
          createdNovelId.value = claimResult.record.novelId
          novelConfirmed.value = false
          chapter1Ensured = false
          chapter1HintSaved = false
          committedSeed = claimResult.record
          await executeLockedOperationPipeline(
            opId,
            claimResult.record,
            true,
            enterWorkbench,
            requestEpoch,
            requestSubmitEpoch,
          )
          return { conflict: null }
        },
        { ifAvailable: true },
      )
      if (freshOutcome.conflict) {
        transitionOnConflictAdoption(
          freshOutcome.conflict,
          `检测到另一窗口已有未完立卷《${freshOutcome.conflict.title}》，已切换至该记录；请先核对完成或放弃后再新建`,
          requestEpoch,
          requestSubmitEpoch,
        )
      }
      return
    }
    const targetOpId = opId
    if (!targetOpId) throw new Error('书目快照缺失，请关闭后重新打开')
    const recoveryOutcome = await withColdStartOperationLock(
      targetOpId,
      async (
        acquired,
      ): Promise<
        | { kind: 'done' }
        | { kind: 'abandoned' }
        | { kind: 'conflict'; existing: ColdStartRecoveryRecord }
      > => {
        if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch || activeOpId.value !== targetOpId) {
          return { kind: 'done' }
        }
        if (isColdStartOpAbandoned(targetOpId)) {
          return { kind: 'abandoned' }
        }
        if (!acquired) {
          throw new Error('另一窗口正在执行该书卷的立卷初始化，请稍候完成后再核对')
        }
        const authState = await withColdStartStorageLock(() => ({
          abandoned: isColdStartOpAbandoned(targetOpId),
          stored: readColdStartRecovery(),
          completed: Boolean(createdNovelId.value && isWizardCompleted(createdNovelId.value)),
        }))
        if (!valid(requestEpoch) || requestSubmitEpoch !== submitEpoch || activeOpId.value !== targetOpId) {
          return { kind: 'done' }
        }
        if (authState.abandoned) {
          return { kind: 'abandoned' }
        }
        if (!authState.stored) {
          if (authState.completed && createdNovelId.value) {
            await finishExternallyCompletedNovel(
              targetOpId,
              createdNovelId.value,
              enterWorkbench,
              requestEpoch,
              requestSubmitEpoch,
            )
            return { kind: 'done' }
          }
          return { kind: 'abandoned' }
        }
        if (authState.stored.opId !== targetOpId) {
          return { kind: 'conflict', existing: authState.stored }
        }
        if (!submissionValid(requestEpoch, requestSubmitEpoch, targetOpId)) {
          return isColdStartOpAbandoned(targetOpId) ? { kind: 'abandoned' } : { kind: 'done' }
        }
        createdNovelId.value = authState.stored.novelId
        novelConfirmed.value = authState.stored.novelConfirmed
        chapter1Ensured = authState.stored.chapter1Ensured
        chapter1HintSaved = authState.stored.chapter1HintSaved
        committedSeed = authState.stored
        await executeLockedOperationPipeline(
          targetOpId,
          authState.stored,
          false,
          enterWorkbench,
          requestEpoch,
          requestSubmitEpoch,
        )
        return { kind: 'done' }
      },
      { ifAvailable: true },
    )
    if (recoveryOutcome.kind === 'abandoned') {
      transitionOnOperationAbandoned(targetOpId, requestEpoch, requestSubmitEpoch)
      return
    }
    if (recoveryOutcome.kind === 'conflict') {
      transitionOnConflictAdoption(
        recoveryOutcome.existing,
        `检测到另一窗口已切换至《${recoveryOutcome.existing.title}》，已载入最新记录；请核对后再继续`,
        requestEpoch,
        requestSubmitEpoch,
      )
      return
    }
  } catch (error) {
    if (opId && isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
      return
    }
    if (
      valid(requestEpoch) &&
      requestSubmitEpoch === submitEpoch &&
      (!opId || (activeOpId.value === opId && !isColdStartOpAbandoned(opId)))
    ) {
      errorText.value = formatApiError(error, '立卷未完成，请重试')
    }
  } finally {
    if (opId && isColdStartOpAbandoned(opId)) {
      transitionOnOperationAbandoned(opId, requestEpoch, requestSubmitEpoch)
    } else if (
      valid(requestEpoch) &&
      requestSubmitEpoch === submitEpoch &&
      (!opId || (activeOpId.value === opId && !isColdStartOpAbandoned(opId)))
    ) {
      submitting.value = false
    } else if (valid(requestEpoch) && requestSubmitEpoch === submitEpoch && submitting.value) {
      submitEpoch += 1
      submitting.value = false
    }
  }
}
function handleKeys(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return }
  if (event.key !== 'Tab') return
  const items = Array.from(dialogRef.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]') ?? []).filter(el => el.getClientRects().length > 0 && window.getComputedStyle(el).visibility !== 'hidden')
  const first = items[0], last = items[items.length - 1]
  if (!first || !last) { event.preventDefault(); dialogRef.value?.focus(); return }
  const active = document.activeElement
  const outside = !dialogRef.value?.contains(active)
  const onContainer = active === dialogRef.value || active === bodyRef.value
  if (event.shiftKey && (active === first || outside || onContainer)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && (active === last || outside)) { event.preventDefault(); first.focus() }
}
function cleanup(restoreFocus = true) {
  epoch += 1
  panelEpoch += 1
  busyEpoch += 1
  submitEpoch += 1
  abandonEpoch += 1
  cancelOpenReconcile()
  controller?.abort()
  controller = null
  submitting.value = false
  busy.value = false
  abandoning.value = false
  panelLoading.value = false
  activeOpId.value = ''
  createdNovelId.value = ''
  novelConfirmed.value = false
  chapter1Ensured = false
  chapter1HintSaved = false
  committedSeed = null
  document.removeEventListener('keydown', handleKeys, true)
  for (const node of inertNodes) node.el.inert = node.inert
  inertNodes = []
  const savedOpener = opener
  opener = null
  if (restoreFocus && !unmounted) {
    if (savedOpener?.isConnected && savedOpener.getClientRects().length > 0) {
      savedOpener.focus()
    } else {
      emit('restore-focus')
    }
  }
}
watch(() => props.show, async open => {
  if (!open) { cleanup(true); return }
  epoch += 1
  const requestEpoch = epoch
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  errorText.value = ''; oauthNotice.value = ''; oauthUrl.value = ''
  busy.value = false; submitting.value = false; abandoning.value = false; panelLoading.value = false; panel.value = null; gateways.value = []; probed.value = false
  rootId.value = roots[0]?.id ?? ''; leafId.value = roots[0]?.children?.[0]?.id ?? ''
  selectedIds.value = CURATED_MOD_PACKS.filter(pack => modHub.isInstalled(pack.id)).map(pack => pack.id)
  const recovery = readColdStartRecovery()
  if (recovery) {
    adoptRecoveryRecord(recovery, requestEpoch)
  } else {
    step.value = 0
    furthestStep.value = 0
    title.value = ''
    activeOpId.value = ''
    createdNovelId.value = ''
    novelConfirmed.value = false
    chapter1Ensured = false
    chapter1HintSaved = false
    committedSeed = null
    resetDraftScaffold()
  }
  document.addEventListener('keydown', handleKeys, true)
  void refreshPanel()
  await nextTick()
  if (!valid(requestEpoch)) return
  for (const child of Array.from(document.body.children)) {
    if (child instanceof HTMLElement && child !== maskRef.value && !child.contains(maskRef.value)) { inertNodes.push({ el: child, inert: child.inert }); child.inert = true }
  }
  closeRef.value?.focus()
}, { immediate: true })
onBeforeUnmount(() => {
  unmounted = true
  cleanup(false)
})
</script>

<style scoped>
.cold-mask { position: fixed; inset: 0; z-index: 3200; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(22,22,21,0.48); }
.cold-dialog { width: 100%; max-width: 880px; max-height: 92dvh; display: flex; flex-direction: column; overflow: hidden; background: var(--app-page-bg, #f4f4f2); color: var(--app-text-primary, #161615); border: none; border-radius: 3px; font-family: 'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px; font-variant-numeric: tabular-nums; }
.cold-dialog * { box-sizing: border-box; }
.cold-dialog :focus-visible { outline: 1.5px solid var(--color-brand, #1f5e5b); outline-offset: 2px; }
.cold-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 20px 24px 12px; }
.cold-head h2 { margin: 0; font-size: 24px; white-space: nowrap; font-weight: 600; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }
.cold-dialog button { min-height: 44px; border: none; border-radius: 3px; padding: 8px 12px; background: var(--app-surface-subtle, #ecece8); color: var(--app-text-secondary, #4a4a46); font: inherit; cursor: pointer; }
.cold-dialog button:disabled { opacity: 0.56; cursor: default; }
.cold-head button { min-width: 44px; flex-shrink: 0; background: transparent; }
.step-ledger { display: flex; gap: 8px; padding: 0 24px 16px; }
.step-ledger button { flex: 1; text-align: left; background: transparent; border-bottom: 2px solid transparent; border-radius: 0; font-size: 14px; }
.step-ledger button.is-current { border-bottom-color: var(--color-brand, #1f5e5b); color: var(--app-text-primary, #161615); }
.cold-body { flex: 1; min-height: 0; overflow-y: auto; padding: 0 24px 24px; }
.step-sheet { display: flex; flex-direction: column; gap: 20px; background: var(--app-surface, #ffffff); padding: 24px; }
.step-sheet h3 { margin: 0; font-size: 18px; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }
.step-sheet h4 { margin: 0; font-size: 16px; font-weight: 500; }
.connection-block { padding: 16px; background: var(--app-page-bg, #f4f4f2); }
.connection-block p, .runtime-strip p { margin: 8px 0; font-size: 14px; color: var(--app-text-secondary, #4a4a46); line-height: 1.7; max-width: 58ch; overflow-wrap: anywhere; }
.gateway-row { margin-top: 16px; padding: 16px; background: var(--app-surface, #ffffff); }
.gateway-row strong { font-size: 15px; }
.role-ledger { font-size: 14px; color: var(--app-text-secondary, #4a4a46); margin: 12px 0; }
.role-ledger > div { display: flex; flex-wrap: wrap; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--app-divider, rgba(22,22,21,0.08)); }
.role-ledger > div:last-child { border-bottom: none; }
.role-ledger dt { flex: 0 0 88px; }
.role-ledger dd { margin: 0; overflow-wrap: anywhere; min-width: 0; }
.runtime-strip { border-left: 2px solid var(--app-text-muted, #595953); padding: 0 16px; }
.runtime-strip.is-ready { border-left-color: var(--color-brand, #1f5e5b); }
.action-row, .taxonomy-choices { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.taxonomy-choices button { background: var(--app-page-bg, #f4f4f2); border-bottom: 2px solid transparent; border-radius: 0; }
.taxonomy-choices button.is-selected { background: var(--app-surface-subtle, #ecece8); border-bottom-color: var(--color-brand, #1f5e5b); color: var(--app-text-primary, #161615); }
.field { display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--app-text-secondary, #4a4a46); }
.field input, .field textarea { width: 100%; min-width: 0; padding: 14px 16px; background: var(--app-page-bg, #f4f4f2); border: none; border-radius: 3px; color: var(--app-text-primary, #161615); font: inherit; font-size: 15px; }
.field .premise-sheet { max-width: 58ch; font-size: 16px; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; line-height: 1.75; resize: vertical; }
.pack-ledger { display: flex; flex-direction: column; gap: 8px; }
.cold-dialog .pack-row { display: flex; align-items: flex-start; gap: 12px; padding: 16px; text-align: left; background: var(--app-page-bg, #f4f4f2); border-left: 2px solid transparent; }
.cold-dialog .pack-row.is-selected { background: var(--app-surface-subtle, #ecece8); border-left-color: var(--color-brand, #1f5e5b); }
.pack-glyph { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: var(--app-surface, #ffffff); flex-shrink: 0; color: var(--app-text-primary, #161615); }
.pack-copy { flex: 1; min-width: 0; }
.pack-copy strong { font-size: 15px; color: var(--app-text-primary, #161615); }
.tier-badge, .installed-note { display: inline-block; font-size: 14px; color: var(--app-text-muted, #595953); margin-left: 8px; }
.pack-summary { display: block; font-size: 14px; line-height: 1.7; margin-top: 8px; max-width: 58ch; }
.pack-status { flex-shrink: 0; font-size: 14px; }
.quiet-note, .error-note { margin: 0; font-size: 14px; line-height: 1.7; color: var(--app-text-muted, #595953); max-width: 58ch; }
.error-note { margin-top: 16px; color: var(--app-text-primary, #161615); border-left: 2px solid var(--app-border-strong, rgba(22,22,21,0.28)); padding-left: 12px; }
.cold-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; padding: 16px 24px; }
.cold-dialog .primary { background: var(--color-brand, #1f5e5b); color: var(--app-text-inverse, #ffffff); max-width: 144px; }
.connection-block a { color: var(--app-text-secondary, #4a4a46); font-size: 14px; text-underline-offset: 4px; }
@media (max-width: 640px) { .cold-mask { padding: 12px; } .cold-dialog { max-height: calc(100dvh - 24px); } .cold-head { padding: 16px 12px 12px; } .step-ledger { gap: 4px; padding: 0 12px 12px; } .step-ledger button { padding: 8px 4px; } .cold-body { padding: 0 12px 12px; } .step-sheet { padding: 16px 12px; gap: 16px; } .connection-block, .gateway-row { padding: 12px; } .cold-foot { padding: 12px; gap: 8px; } .cold-foot button { padding: 8px; } .cold-dialog .pack-row { padding: 12px 8px; gap: 8px; } .tier-badge { display: block; margin: 4px 0 0; } }
</style>
