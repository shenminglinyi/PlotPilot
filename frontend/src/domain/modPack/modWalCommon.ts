import { promptPlazaApi, type PromptApiCallConfig, type PromptMutationPreconditions, type PromptNodeDetail } from '@/api/llmControl'
import { storageKeys } from '@/config/storageKeys'
import { hasForeignModMention, hasForeignReplacedBlock, hasMatchingCustomOriginToken } from '@/domain/modPack/modProtocol'
import type { InstalledModRecord, UnresolvedNodeMutation } from '@/domain/modPack/types'
export const AMBIGUOUS_MUTATION_GRACE_MS = 15_000
export const MOD_HUB_WEB_LOCK_NAME = 'plotpilot:mod_hub_tx_lock'
let memoryFallbackStore: Record<string, InstalledModRecord> = {}
function cloneRecordsMap(source: Record<string, InstalledModRecord>): Record<string, InstalledModRecord> { return JSON.parse(JSON.stringify(source)) as Record<string, InstalledModRecord> }
export function readStoredRecords(): Record<string, InstalledModRecord> { if (typeof window === 'undefined') return cloneRecordsMap(memoryFallbackStore)
 try { const raw = window.localStorage.getItem(storageKeys.modHubInstalled)
  if (!raw) return {}
  const parsed = JSON.parse(raw) as unknown
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, InstalledModRecord>) : {} } catch { return {} } }
export function readStoredRecordsStrict(): Record<string, InstalledModRecord> { if (typeof window === 'undefined') return cloneRecordsMap(memoryFallbackStore)
 let raw: string | null
 try { raw = window.localStorage.getItem(storageKeys.modHubInstalled) } catch (err) { throw new Error(`读取浏览器本地模组状态失败（${err instanceof Error ? err.message : String(err)}），已中止模组变更以保护现有恢复记录`) }
 if (raw === null || raw === '') return {}
 let parsed: unknown
 try { parsed = JSON.parse(raw) } catch (err) { throw new Error(`本地模组恢复存储数据格式损坏（${err instanceof Error ? err.message : String(err)}），已拒绝覆盖写入以保护现有快照`) }
 if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('本地模组恢复存储结构异常，已拒绝覆盖写入以保护现有快照')
 return parsed as Record<string, InstalledModRecord> }
export function writeStoredRecordsStrict(records: Record<string, InstalledModRecord>): void { const serialized = JSON.stringify(records)
 if (typeof window === 'undefined') { memoryFallbackStore = JSON.parse(serialized) as Record<string, InstalledModRecord>; return }
 try { window.localStorage.setItem(storageKeys.modHubInstalled, serialized) } catch (err) { throw new Error(`浏览器本地存储写入失败（${err instanceof Error ? err.message : String(err)}），已中止模组变更以防丢失回滚与所有权记录`)
 } }
export function writeStoredPackRecordStrict(packId: string, record: InstalledModRecord | undefined): Record<string, InstalledModRecord> { const authoritative = readStoredRecordsStrict()
 if (record !== undefined) authoritative[packId] = record; else delete authoritative[packId]
 writeStoredRecordsStrict(authoritative)
 return authoritative }
const nodeLockTails = new Map<string, Promise<void>>()
async function acquireSingleKeyLock(key: string): Promise<() => void> { const prev = nodeLockTails.get(key) ?? Promise.resolve()
 let releaseFn!: () => void
 const current = new Promise<void>(resolve => { releaseFn = resolve })
 const tail = prev.then(() => current)
 nodeLockTails.set(key, tail)
 await prev
 return () => { releaseFn()
  if (nodeLockTails.get(key) === tail) nodeLockTails.delete(key) } }
async function runWithInProcessKeyLocks<T>(keys: Iterable<string>, fn: () => Promise<T>): Promise<T> { const sortedUniqueKeys = Array.from(new Set(['__mod_hub_state__', ...keys])).sort()
 const releases: Array<() => void> = []
 try { for (const k of sortedUniqueKeys) releases.push(await acquireSingleKeyLock(k))
  return await fn() } finally { for (let i = releases.length - 1; i >= 0; i -= 1) releases[i]() } }
export async function withNodeLocks<T>(keys: Iterable<string>, fn: () => Promise<T>): Promise<T> { if (typeof window !== 'undefined') { const webLocks = typeof navigator !== 'undefined'
   ? (navigator as Navigator & { locks?: { request: <R>(name: string, options: { mode: 'exclusive' }, callback: () => Promise<R>) => Promise<R> } }).locks
   : undefined
  if (typeof webLocks?.request !== 'function') { throw new Error('当前运行环境不支持跨标签页互斥锁（Web Locks API），请通过 localhost / 127.0.0.1 或 HTTPS 安全上下文访问以保障模组事务安全') }
  return await webLocks.request(MOD_HUB_WEB_LOCK_NAME, { mode: 'exclusive' }, () => runWithInProcessKeyLocks(keys, fn)) }
 return await runWithInProcessKeyLocks(keys, fn) }
export function collectRecordLockKeys(rec?: InstalledModRecord): string[] { if (!rec) return []
 return [
  ...(rec.pack.overrides?.map(o => o.nodeKey) ?? []), ...(rec.patchedNodeKeys ?? []), ...Object.keys(rec.patchedNodeIds ?? {}), ...Object.keys(rec.replacedSystemBackups ?? {}),
  ...Object.keys(rec.pendingCreateTokens ?? {}), ...Object.keys(rec.pendingCreateTemplates ?? {}), ...Object.keys(rec.ownedCustomTokens ?? {}), ...Object.keys(rec.ownedCustomUserTemplates ?? {}),
  ...Object.keys(rec.unresolvedMutations ?? {}), ] }
interface HttpErrorShape { response?: { status?: number; data?: unknown }; message?: string }
export function getHttpStatus(err: unknown): number | undefined { if (!err || typeof err !== 'object') return undefined
 const status = (err as HttpErrorShape).response?.status
 return typeof status === 'number' ? status : undefined }
export function getHttpDetailMessage(err: unknown): string | undefined { if (!err || typeof err !== 'object') return undefined
 const data = (err as HttpErrorShape).response?.data
 if (data && typeof data === 'object' && 'detail' in data) { const detail = (data as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (detail != null) return JSON.stringify(detail) }
 return undefined }
export const isHttpNotFound = (err: unknown): boolean => getHttpStatus(err) === 404
export function isDefinitivePreCommitHttpError(err: unknown): boolean { const s = getHttpStatus(err)
 return s === 400 || s === 401 || s === 403 || s === 404 || s === 405 || s === 409 || s === 413 || s === 422 }
export function isWithinAmbiguityWindow(mutation: UnresolvedNodeMutation, nowMs = Date.now()): boolean {
 if (typeof mutation.startedAt !== 'number' || !Number.isFinite(mutation.startedAt) || mutation.startedAt <= 0) return false
 return nowMs - mutation.startedAt < AMBIGUOUS_MUTATION_GRACE_MS }
export function hasVersionFenceToken(detail: Pick<PromptNodeDetail, 'active_version_id' | 'version_count'>): boolean {
 return typeof detail.active_version_id === 'string' && detail.active_version_id.trim().length > 0 }
function assertHasVersionFenceToken(detail: PromptNodeDetail, actionLabel: string): void {
 if (!hasVersionFenceToken(detail)) throw new Error(`节点「${detail.node_key}」缺少全局唯一版本标识（active_version_id），已中止${actionLabel}以保障并发安全`) }
export function buildSystemUpdatePreconditions(detail: PromptNodeDetail): PromptMutationPreconditions { assertHasVersionFenceToken(detail, '更新')
 return { expected_active_version_id: detail.active_version_id!,
  ...(typeof detail.version_count === 'number' && Number.isFinite(detail.version_count) ? { expected_version_count: detail.version_count } : {}), expected_system: detail.system ?? '',
  ...(typeof detail.user_template === 'string' ? { expected_user_template: detail.user_template } : {}), } }
export function buildOwnedCustomUpdatePreconditions(detail: PromptNodeDetail): PromptMutationPreconditions { return { ...buildSystemUpdatePreconditions(detail),
  expected_user_template: detail.user_template ?? '', ...(typeof detail.name === 'string' ? { expected_name: detail.name } : {}),
  ...(typeof detail.description === 'string' ? { expected_description: detail.description } : {}), } }
export function buildDeleteNodePreconditionConfig(detail: PromptNodeDetail): PromptApiCallConfig & { data?: PromptMutationPreconditions } { assertHasVersionFenceToken(detail, '删除')
 const verId = detail.active_version_id!, params: Record<string, string | number> = { expected_version_id: verId }
 if (typeof detail.version_count === 'number' && Number.isFinite(detail.version_count)) params.expected_version_count = detail.version_count
 return { silentGlobalFeedback: true, params, data: { expected_active_version_id: verId,
   ...(typeof detail.version_count === 'number' && Number.isFinite(detail.version_count) ? { expected_version_count: detail.version_count } : {}), expected_system: detail.system ?? '',
   expected_user_template: detail.user_template ?? '', }, } }
export function hasPatchMutationCommitted(live: PromptNodeDetail, mutation: UnresolvedNodeMutation): boolean {
 if (mutation.writtenSystem !== undefined && (live.system ?? '') !== mutation.writtenSystem) return false
 if (mutation.writtenName !== undefined && live.name !== mutation.writtenName) return false
 if (mutation.writtenDescription !== undefined && (live.description || '') !== mutation.writtenDescription) return false
 if (mutation.writtenUserTemplate !== undefined && (live.user_template ?? '') !== mutation.writtenUserTemplate) return false
 const hasAnyWritten = mutation.writtenSystem !== undefined || mutation.writtenName !== undefined || mutation.writtenDescription !== undefined || mutation.writtenUserTemplate !== undefined
 if (!hasAnyWritten) return false
 const hasAnyPrior = mutation.priorSystem !== undefined || mutation.priorName !== undefined || mutation.priorDescription !== undefined || mutation.priorUserTemplate !== undefined
 if (!hasAnyPrior) return true
 return (mutation.writtenSystem !== undefined && mutation.priorSystem !== undefined && mutation.writtenSystem !== mutation.priorSystem) ||
  (mutation.writtenName !== undefined && mutation.priorName !== undefined && mutation.writtenName !== mutation.priorName) ||
  (mutation.writtenDescription !== undefined && mutation.priorDescription !== undefined && mutation.writtenDescription !== mutation.priorDescription) ||
  (mutation.writtenUserTemplate !== undefined && mutation.priorUserTemplate !== undefined && mutation.writtenUserTemplate !== mutation.priorUserTemplate) }
export function isMissingLegacyRemoteEndpoint(err: unknown): boolean { const status = getHttpStatus(err)
 const detail = getHttpDetailMessage(err)
 return (status === 404 && detail === 'Not Found') || (status === 405 && detail === 'Method Not Allowed') }
export function formatBackendError(err: unknown, fallbackPrefix: string): Error { const detail = getHttpDetailMessage(err)
 if (detail) return new Error(`${fallbackPrefix}：${detail}`)
 if (err instanceof Error) return err
 return new Error(`${fallbackPrefix}：${String(err)}`) }
export async function fetchExistingNodeOrNull(nodeKeyOrId: string): Promise<PromptNodeDetail | null> { try {
  return (await promptPlazaApi.getNodeDetail(nodeKeyOrId, { silentGlobalFeedback: true })) as unknown as PromptNodeDetail } catch (err) { if (isHttpNotFound(err)) return null
  throw formatBackendError(err, `读取节点「${nodeKeyOrId}」失败`) } }
export async function fetchNodeByVerifiedId(targetId: string): Promise<PromptNodeDetail | null> { const detail = await fetchExistingNodeOrNull(targetId)
 if (!detail) return null
 if (detail.id !== targetId) throw new Error(`节点 ID「${targetId}」查询被同名键「${detail.node_key}」遮蔽，已保留恢复记录`)
 return detail }
export async function fenceNodeVersion(detail: PromptNodeDetail, changeSummary: string): Promise<PromptNodeDetail> { assertHasVersionFenceToken(detail, '版本围栏收敛')
 await promptPlazaApi.updateNode(detail.node_key, { ...buildOwnedCustomUpdatePreconditions(detail), system: detail.system ?? '', change_summary: changeSummary }, { silentGlobalFeedback: true }, )
 const refreshed = await fetchNodeByVerifiedId(detail.id)
 if (!refreshed) throw new Error(`节点「${detail.node_key}」在建立版本围栏后已不存在，请重试对账`)
 const hadVerCnt = typeof detail.version_count === 'number' && Number.isFinite(detail.version_count)
 const idAdvanced = typeof refreshed.active_version_id === 'string' && refreshed.active_version_id.trim().length > 0 && refreshed.active_version_id !== detail.active_version_id
 const cntAdvanced = !hadVerCnt || (typeof refreshed.version_count === 'number' && refreshed.version_count > detail.version_count)
 if (!idAdvanced || !cntAdvanced) throw new Error(`节点「${detail.node_key}」版本世代未推进，无法拦截超时未决请求，已保留恢复记录`)
 return refreshed }
export function getDuplicateTokenMatches(err: unknown): PromptNodeDetail[] {
 const m = err && typeof err === 'object' ? (err as { duplicateMatches?: unknown }).duplicateMatches : undefined
 return Array.isArray(m) ? (m as PromptNodeDetail[]) : [] }
export async function discoverCustomNodeByOriginToken(packId: string, originToken: string | undefined): Promise<PromptNodeDetail | null> {
 if (!originToken) throw new Error('缺少自定义节点 128 位归属令牌，无法核验已重命名节点去向，已保留恢复记录')
 if (typeof promptPlazaApi.listNodes !== 'function') throw new Error('当前环境缺少权威节点枚举接口（listNodes），已保留未决创建恢复记录')
 let allNodes: Awaited<ReturnType<typeof promptPlazaApi.listNodes>>
 try { allNodes = await promptPlazaApi.listNodes() } catch (err) { throw formatBackendError(err, '枚举节点核验未决创建归属失败') }
 if (!Array.isArray(allNodes)) throw new Error('节点枚举返回格式异常，已保留未决创建恢复记录')
 const matches: PromptNodeDetail[] = []
 for (const item of allNodes) { if (!item || item.is_builtin || typeof item.id !== 'string' || !item.id) continue
  const detail = await fetchNodeByVerifiedId(item.id)
  if (detail && !detail.is_builtin && hasMatchingCustomOriginToken(detail.system ?? '', packId, originToken)) matches.push(detail) }
 if (matches.length > 1) { const dupErr = new Error('检测到多个自定义节点携带同一归属令牌，已保留恢复记录以防误认') as Error & { duplicateMatches?: PromptNodeDetail[] }
  dupErr.duplicateMatches = matches; throw dupErr }
 return matches[0] ?? null }
export function findForeignDependentPackNames(installedRecords: Record<string, InstalledModRecord>, targetNodeKey: string, excludePackId: string, targetNodeId?: string, ): string[] {
 const names: string[] = []
 for (const [otherId, otherRec] of Object.entries(installedRecords)) { if (otherId === excludePackId) continue
  const matchesByKey = otherRec.patchedNodeKeys.includes(targetNodeKey) || Boolean(otherRec.patchedNodeIds?.[targetNodeKey]) ||
   Boolean(otherRec.replacedSystemBackups?.[targetNodeKey]) || Boolean(otherRec.unresolvedMutations?.[targetNodeKey])
  const matchesById = Boolean(targetNodeId) && (Object.values(otherRec.patchedNodeIds ?? {}).includes(targetNodeId!) ||
   Object.values(otherRec.replacedSystemBackups ?? {}).some(b => b.targetNodeId === targetNodeId) || Object.values(otherRec.unresolvedMutations ?? {}).some(u => u.targetNodeId === targetNodeId)
  )
  if (matchesByKey || matchesById) names.push(otherRec.pack.name) }
 return names }
export function hasForeignContentLayers(systemText: string, excludePackId: string): boolean {
 return hasForeignModMention(systemText, excludePackId) || hasForeignReplacedBlock(systemText, excludePackId) }
