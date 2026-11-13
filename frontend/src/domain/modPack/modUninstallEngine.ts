import { promptPlazaApi, type PromptNodeDetail as NDet } from '@/api/llmControl'
import { assertValidModId, extractCustomOriginToken as origTok, hasAnyModBlock, hasMatchingCustomOriginToken as hasCTok, hasPackModMention, hasReplacedModBlock as hasRepBlk, restoreReplacedModBlock, stripModProtocolBlock,
 stripOwnedCustomBlock, } from '@/domain/modPack/modProtocol'
import { buildDeleteNodePreconditionConfig as delPre, buildSystemUpdatePreconditions as sysPre, discoverCustomNodeByOriginToken as discTok,
 fenceNodeVersion as fenceVer, fetchExistingNodeOrNull as fetchByKey, fetchNodeByVerifiedId as fetchById, findForeignDependentPackNames, formatBackendError as fmtErr, getDuplicateTokenMatches as dupDets,
 hasForeignContentLayers, hasPatchMutationCommitted as isPatchDone, isDefinitivePreCommitHttpError as isPreErr, isHttpNotFound as is404, isWithinAmbiguityWindow as inGraceWin, withNodeLocks, } from '@/domain/modPack/modWalCommon'
import type { InstalledModRecord, ReplacedNodeBackup, UnresolvedNodeMutation as WalMut } from '@/domain/modPack/types'
export interface UninstallStoreBridge { reloadAuthoritativeMap: () => Record<string, InstalledModRecord>
 commitPackRecord: (packId: string, record: InstalledModRecord | undefined) => Record<string, InstalledModRecord> }
export async function executeModPackUninstall(packId: string, bridge: UninstallStoreBridge): Promise<void> { const safeId = assertValidModId(packId)
 await withNodeLocks([safeId], () => runUninstallLocked(safeId, bridge)) }
async function runUninstallLocked(safeId: string, bridge: UninstallStoreBridge): Promise<void> { let instMap = bridge.reloadAuthoritativeMap()
 const record = instMap[safeId]
 if (!record) return
 const kCustIds = new Set<string>(record.createdNodeIds), actCIds = new Set<string>(record.createdNodeIds), enrIds = new Set<string>(record.createdNodeIds)
 const oToks: Record<string, string> = { ...(record.ownedCustomTokens ?? {}) }
 const remOTpls: Record<string, string> = { ...(record.ownedCustomUserTemplates ?? {}) }
 const pToks: Record<string, string> = { ...(record.pendingCreateTokens ?? {}) }
 const remPTpls: Record<string, string> = { ...(record.pendingCreateTemplates ?? {}) }
 const actPKeys = new Set<string>(record.patchedNodeKeys)
 const pIds: Record<string, string> = { ...(record.patchedNodeIds ?? {}) }
 const bkps: Record<string, ReplacedNodeBackup> = { ...(record.replacedSystemBackups ?? {}) }
 const wals: Record<string, WalMut> = { ...(record.unresolvedMutations ?? {}) }
 const getWalTok = (wal: WalMut | undefined): string | undefined =>
  wal ? (wal.originToken ?? origTok(wal.priorSystem ?? '', safeId) ?? origTok(wal.writtenSystem ?? '', safeId) ?? undefined) : undefined
 const basePendKey = (k: string): string => { const i = k.indexOf('#pending:'); return i >= 0 ? k.slice(0, i) : k }
 const isCust = (id: string | null | undefined, detail?: NDet | null, wal?: WalMut): boolean =>
  Boolean((id && (kCustIds.has(id) || actCIds.has(id))) || getWalTok(wal) !== undefined || wal?.kind === 'create' || wal?.kind === 'delete' || (detail && !detail.is_builtin && origTok(detail.system ?? '', safeId) !== null))
 const isProvenPatch = (detail: NDet | null | undefined, wal: WalMut | undefined, needsReplaced: boolean): boolean => {
  if (!detail || !wal || wal.kind !== 'patch' || wal.targetNodeId !== detail.id || isCust(detail.id, detail, wal)) return false
  const checkSys = (s: string) => s.length > 0 && origTok(s, safeId) === null && (needsReplaced ? hasRepBlk(s, safeId) : hasAnyModBlock(s, safeId))
  return checkSys(detail.system ?? '') || (isPatchDone(detail, wal) && checkSys(wal.priorSystem ?? '')) }
 for (const [bk, bv] of Object.entries(bkps)) if (bv.targetNodeId && !isCust(bv.targetNodeId) && !pIds[bk]) pIds[bk] = bv.targetNodeId
 for (const [pk, pid] of Object.entries(pIds)) if (!isCust(pid) && bkps[pk] && !bkps[pk].targetNodeId) bkps[pk] = { ...bkps[pk], targetNodeId: pid }
 const handledWalKeys = new Set<string>(), cleanIds = new Set<string>(), failIds = new Set<string>()
 const failKeys = new Set<string>(), pinToks = new Set<string>(), errs: string[] = []
 const pinTokens = (...toks: Array<string | null | undefined>): void => { for (const t of toks) if (t) pinToks.add(t) }
 const failNode = (nodeIds: Array<string | null | undefined>, keys: Array<string | null | undefined>, ...toksToPin: Array<string | null | undefined>): void => {
  for (const id of nodeIds) if (id) failIds.add(id)
  for (const k of keys) if (k) { failKeys.add(k); handledWalKeys.add(k) }
  pinTokens(...toksToPin) }
 const markClean = (nodeIds: Array<string | null | undefined>): void => { for (const id of nodeIds) if (id) cleanIds.add(id) }
 const hasTrace = (sys: string): boolean => hasAnyModBlock(sys, safeId) || hasPackModMention(sys, safeId)
 const restoreWal = (key: string, prior: WalMut | undefined): void => { if (prior) wals[key] = prior; else delete wals[key] }
 const isSlotVacant = (key: string): boolean => wals[key] === undefined && bkps[key] === undefined && pIds[key] === undefined &&
  !actPKeys.has(key) && oToks[key] === undefined && pToks[key] === undefined
 const retToks = (key: string | null | undefined, tok: string | undefined, includePending = true): void => { if (!key) return
  const oTok = oToks[key]
  if ((!oTok || oTok === tok) && (!oTok || !pinToks.has(oTok))) { delete oToks[key]; delete remOTpls[key] }
  if (includePending) { const pTok = pToks[key]
   if ((!pTok || pTok === tok) && (!pTok || !pinToks.has(pTok))) { delete pToks[key]; delete remPTpls[key] } } }
 const isBlkWin = (detail: NDet | null, entry: WalMut | undefined): boolean => { if (!entry || !inGraceWin(entry)) return false
  if (!detail) return entry.kind === 'create' || entry.kind === 'patch'
  return (entry.kind === 'patch' && !isPatchDone(detail, entry)) || entry.kind === 'delete' || entry.kind === 'create' }
 const idsGone = async (ids: Array<string | null | undefined>): Promise<boolean> => {
  const uniqueIds = Array.from(new Set(ids.filter((id): id is string => typeof id === 'string' && id.length > 0)))
  if (uniqueIds.length === 0) return false
  for (const id of uniqueIds) { try { if ((await fetchById(id)) !== null) return false } catch { return false } }
  return true }
 const nonEmpty = <T>(m: Record<string, T>): Record<string, T> | undefined => Object.keys(m).length ? { ...m } : undefined
 const saveCkpt = () => { instMap = bridge.commitPackRecord(safeId, { ...record, createdNodeIds: Array.from(actCIds),
   ownedCustomTokens: nonEmpty(oToks), ownedCustomUserTemplates: nonEmpty(remOTpls), pendingCreateTokens: nonEmpty(pToks), pendingCreateTemplates: nonEmpty(remPTpls),
   patchedNodeKeys: Array.from(actPKeys), patchedNodeIds: nonEmpty(pIds),
   replacedSystemBackups: nonEmpty(bkps), unresolvedMutations: nonEmpty(wals), walReservationPad: undefined, }) }
 saveCkpt()
 const matchesOrigWal = (wal: WalMut, sKey: string, expTok: string | undefined): boolean => { if (!expTok) return false
  const walTok = getWalTok(wal)
  if (walTok !== undefined) return walTok === expTok
  if (actPKeys.has(sKey) || pIds[sKey] !== undefined || bkps[sKey] !== undefined) return false
  if ((oToks[sKey] && oToks[sKey] !== expTok) || (pToks[sKey] && pToks[sKey] !== expTok)) return false
  return (wal.kind === 'patch' && oToks[sKey] === expTok && pToks[sKey] === undefined) ||
   (wal.kind === 'create' && pToks[sKey] === expTok && oToks[sKey] === undefined) ||
   (wal.kind === 'delete' && (oToks[sKey] === expTok || pToks[sKey] === expTok)) }
 const assertSlotSafe = (detail: NDet, expTok: string | undefined): void => { const liveKey = detail.node_key, exWal = wals[liveKey]
  if (exWal) { const exWTok = getWalTok(exWal)
   const ownByNode = exWal.targetNodeId !== undefined ? exWal.targetNodeId === detail.id : exWTok !== undefined ? Boolean(expTok) && exWTok === expTok : matchesOrigWal(exWal, liveKey, expTok)
   if (!ownByNode) throw new Error(`独立节点「${liveKey}」所在键位仍存有其他节点的未决恢复记录，已延后清理以保护原基线快照`) }
  if (bkps[liveKey] !== undefined) throw new Error(`独立节点「${liveKey}」所在键位仍存有系统替换基线快照，已延后清理以防丢失恢复线索`)
  if (pIds[liveKey] !== undefined && pIds[liveKey] !== detail.id) throw new Error(`独立节点「${liveKey}」所在键位仍存有其他挂载目标 ID 记录，已延后清理以防覆盖`)
  if (oToks[liveKey] !== undefined && oToks[liveKey] !== expTok) throw new Error(`独立节点「${liveKey}」所在键位仍存有其他自建节点的归属令牌，已延后清理以防覆盖`)
  if (pToks[liveKey] !== undefined && pToks[liveKey] !== expTok) throw new Error(`独立节点「${liveKey}」所在键位仍存有其他待确认节点的归属令牌，已延后清理以防覆盖`) }
 const hasForeignPatch = (key: string, nodeId: string): boolean => { const exWal = wals[key], bkp = bkps[key]
  if (exWal && (isCust(exWal.targetNodeId, null, exWal) || (exWal.targetNodeId && exWal.targetNodeId !== nodeId))) return true
  return Boolean((pIds[key] && pIds[key] !== nodeId) || (bkp?.targetNodeId && bkp.targetNodeId !== nodeId) || oToks[key] !== undefined || pToks[key] !== undefined) }
 const ownsWal = (sKey: string, nodeId: string, expTok?: string): boolean => { const entry = wals[sKey]
  if (!entry) return false
  const entryTok = getWalTok(entry)
  if (failIds.has(nodeId) || failKeys.has(sKey) || (entryTok && pinToks.has(entryTok)) || (expTok && pinToks.has(expTok))) return false
  if (entry.targetNodeId !== undefined) return entry.targetNodeId === nodeId
  if (entryTok !== undefined) return Boolean(expTok) && entryTok === expTok
  if (expTok !== undefined) return matchesOrigWal(entry, sKey, expTok)
  return entry.kind === 'patch' && (!pIds[sKey] || pIds[sKey] === nodeId) && (!bkps[sKey]?.targetNodeId || bkps[sKey]?.targetNodeId === nodeId) && oToks[sKey] === undefined && pToks[sKey] === undefined
 }
 const resolveCustomTpl = (detail: NDet, key: string, preferPending = false, expTok?: string): string | undefined => {
  const detailLiveTok = !detail.is_builtin ? origTok(detail.system ?? '', safeId) : null
  if (failIds.has(detail.id) || failKeys.has(detail.node_key) || (key !== detail.node_key && failKeys.has(key)) || (expTok && pinToks.has(expTok)) || (detailLiveTok && pinToks.has(detailLiveTok))) return undefined
  const matchesDetail = (item: WalMut | undefined, itemKey: string): item is WalMut => { if (!item) return false
   const wTok = getWalTok(item)
   if (failKeys.has(itemKey) || (wTok && pinToks.has(wTok))) return false
   if (item.targetNodeId !== undefined) return item.targetNodeId === detail.id
   return wTok !== undefined ? Boolean(expTok) && wTok === expTok : !expTok || oToks[key] === expTok || pToks[key] === expTok || oToks[detail.node_key] === expTok || pToks[detail.node_key] === expTok
  }
  const candKeys = Array.from(new Set([detail.node_key, key]))
  const cmtPatch = candKeys.map(k => (matchesDetail(wals[k], k) ? wals[k] : undefined)).find((item): item is WalMut => Boolean(item && item.kind === 'patch' && isPatchDone(detail, item)))
  if (cmtPatch) { if (cmtPatch.targetOwnedUserTemplate === null) return undefined
   if (cmtPatch.targetOwnedUserTemplate !== undefined) return cmtPatch.targetOwnedUserTemplate
   if (cmtPatch.writtenUserTemplate !== undefined) return cmtPatch.writtenUserTemplate }
  const uMut = (matchesDetail(wals[key], key) ? wals[key] : undefined) ?? (matchesDetail(wals[detail.node_key], detail.node_key) ? wals[detail.node_key] : undefined)
  const pickTpl = (toks: Record<string, string>, tpls: Record<string, string>, k: string) =>
   ((k !== detail.node_key && failKeys.has(k)) || (expTok && pinToks.has(expTok)) ? undefined : ((expTok ? toks[k] === expTok : !toks[k]) ? tpls[k] : undefined))
  const ownedTpl = pickTpl(oToks, remOTpls, key) ?? pickTpl(oToks, remOTpls, detail.node_key)
  const pendingTpl = pickTpl(pToks, remPTpls, key) ?? pickTpl(pToks, remPTpls, detail.node_key)
  return preferPending ? (pendingTpl ?? ownedTpl ?? uMut?.initialUserTemplate) : (ownedTpl ?? pendingTpl ?? uMut?.initialUserTemplate) }
 const hasBlkWal = (detail: NDet, ...candidateKeys: Array<string | null | undefined>): boolean => {
  const chkList: WalMut[] = [], seenKeys = new Set<string>()
  for (const k of [detail.node_key, ...candidateKeys]) { if (!k || seenKeys.has(k)) continue
   seenKeys.add(k)
   const entry = wals[k]
   if (entry && (k === detail.node_key || !entry.targetNodeId || entry.targetNodeId === detail.id)) chkList.push(entry) }
  for (const [uk, um] of Object.entries(wals)) if (!seenKeys.has(uk) && um.targetNodeId && um.targetNodeId === detail.id) chkList.push(um)
  return chkList.some((entry) => isBlkWin(detail, entry)) }
 const findTokSlot = (tokenMap: Record<string, string>, detail: NDet): [string, string] | undefined =>
  Object.entries(tokenMap).find(([k, tok]) => k !== detail.node_key && !failKeys.has(k) && Boolean(tok) && !pinToks.has(tok) && hasCTok(detail.system ?? '', safeId, tok))
 const findSrcKey = (detail: NDet): string | undefined => {
  for (const [k, um] of Object.entries(wals)) if (k !== detail.node_key && !failKeys.has(k) && um.targetNodeId === detail.id) return k
  for (const [k, um] of Object.entries(wals)) { const wTok = getWalTok(um)
   if (k !== detail.node_key && !failKeys.has(k) && (!um.targetNodeId || um.targetNodeId === detail.id) && wTok && !pinToks.has(wTok) && hasCTok(detail.system ?? '', safeId, wTok)) return k }
  const matched = findTokSlot(oToks, detail) ?? findTokSlot(pToks, detail)
  if (matched) return matched[0]
  const liveWal = wals[detail.node_key]
  return oToks[detail.node_key] !== undefined || pToks[detail.node_key] !== undefined || (liveWal !== undefined && (!liveWal.targetNodeId || liveWal.targetNodeId === detail.id)) ? detail.node_key : undefined
 }
 const enrollCustom = (detail: NDet, expTok: string, effTpl: string | undefined): void => { assertSlotSafe(detail, expTok)
  enrIds.add(detail.id); kCustIds.add(detail.id); actCIds.add(detail.id); oToks[detail.node_key] = expTok
  if (effTpl !== undefined) remOTpls[detail.node_key] = effTpl; else delete remOTpls[detail.node_key]
  saveCkpt() }
 const retireAbsent = (sKey: string, targetId: string, originTok?: string): void => { const customTarget = isCust(targetId) || Boolean(originTok)
  markClean([targetId]); actCIds.delete(targetId)
  const priorPatchedId = pIds[sKey], slotBkp = bkps[sKey]
  const hadProvenPatch = !customTarget && (priorPatchedId === targetId || slotBkp?.targetNodeId === targetId)
  if (priorPatchedId === targetId && (!slotBkp || !customTarget)) delete pIds[sKey]
  if (slotBkp && !customTarget && (slotBkp.targetNodeId === targetId || (!slotBkp.targetNodeId && priorPatchedId === targetId))) delete bkps[sKey]
  if (ownsWal(sKey, targetId, originTok)) delete wals[sKey]
  if (originTok) retToks(sKey, originTok)
  if (hadProvenPatch && oToks[sKey] === undefined && pToks[sKey] === undefined && bkps[sKey] === undefined && pIds[sKey] === undefined) actPKeys.delete(sKey)
 }
 const fin404 = (ids: Array<string | null | undefined>, primaryKey: string | null | undefined, liveKeys: Array<string | null | undefined>, tok: string | undefined): void => {
  markClean(ids); const validIds = ids.filter((id): id is string => Boolean(id))
  for (const id of validIds) actCIds.delete(id)
  if (primaryKey) { for (const id of validIds) if (ownsWal(primaryKey, id, tok)) delete wals[primaryKey]
   retToks(primaryKey, tok, true) }
  for (const lk of liveKeys) if (lk) { for (const id of validIds) if (ownsWal(lk, id, tok)) delete wals[lk]; retToks(lk, tok, false) } }
 const infSlotTok = (sKey: string, um: WalMut | undefined): string | undefined => { if (!um) return undefined
  const wTok = getWalTok(um)
  if (wTok) return wTok
  const slotTok = oToks[sKey] ?? pToks[sKey]
  return slotTok && matchesOrigWal(um, sKey, slotTok) ? slotTok : undefined }
 const walBinds = (wk: string, wu: WalMut | undefined, tok: string | undefined): boolean => {
  if (!wu?.targetNodeId || !tok) return false
  const wt = getWalTok(wu)
  if (wt !== undefined) return wt === tok
  if (wu.kind === 'create') return pToks[wk] === tok || (!pToks[wk] && oToks[wk] === tok)
  if (wu.kind === 'delete') return oToks[wk] === tok || pToks[wk] === tok
  return matchesOrigWal(wu, wk, tok) }
 const effWTok = (wk: string, wu: WalMut | undefined): string | undefined => {
  if (!wu) return undefined
  const wt = getWalTok(wu)
  if (wt) return wt
  if (wu.targetNodeId) { for (const t of [pToks[wk], oToks[wk]]) if (t && walBinds(wk, wu, t)) return t; return undefined }
  return infSlotTok(wk, wu) }
 const walConf = (tok: string, candId?: string | null): { ids: string[]; keys: string[] } | null => {
  const bIds = new Set<string>(), bKeys = new Set<string>()
  for (const [wk, wu] of Object.entries(wals)) if (wu.targetNodeId && walBinds(wk, wu, tok)) { bIds.add(wu.targetNodeId); bKeys.add(wk) }
  return bIds.size > 1 || (Boolean(candId) && bIds.size > 0 && !bIds.has(candId!)) ? { ids: Array.from(bIds), keys: Array.from(bKeys) } : null }
 const keepEnr = (id: string) => { if (enrIds.has(id)) actCIds.add(id); else { actCIds.delete(id); kCustIds.delete(id) } }
 const obsById = new Map<string, NDet>(), ownByTok = new Map<string, NDet>()
 const recOwner = (tok: string, d: NDet | null | undefined): NDet | null => {
  if (!d) return null
  obsById.set(d.id, d)
  const prev = ownByTok.get(tok)
  if (prev && prev.id !== d.id) return prev
  ownByTok.set(tok, d); return null }
 const failCls = (tok: string | undefined, exDets: NDet[] = [], exKeys: Array<string | null | undefined> = [], exIds: Array<string | null | undefined> = []): void => {
  if (!tok) { failNode(exIds, exKeys); return }
  const prev = ownByTok.get(tok); ownByTok.delete(tok)
  const ids = new Set<string>(), keys = new Set<string>()
  for (const id of exIds) if (id) ids.add(id)
  for (const k of exKeys) if (k) keys.add(k)
  for (const [k, u] of Object.entries(wals)) if (walBinds(k, u, tok) || effWTok(k, u) === tok) { keys.add(k); if (u.targetNodeId) ids.add(u.targetNodeId) }
  for (const [k, v] of Object.entries(pToks)) if (v === tok) keys.add(k)
  for (const [k, v] of Object.entries(oToks)) if (v === tok) keys.add(k)
  for (const d of [...(prev ? [prev] : []), ...exDets, ...Array.from(obsById.values())]) {
   if (ids.has(d.id) || (!d.is_builtin && hasCTok(d.system ?? '', safeId, tok))) { ids.add(d.id); keys.add(d.node_key) } }
  for (const [k, u] of Object.entries(wals)) if (u.targetNodeId && ids.has(u.targetNodeId)) keys.add(k)
  failNode(Array.from(ids), Array.from(keys), tok) }
 const chkUniq = async (tok: string | null | undefined, exDets: NDet[] = [], exKeys: Array<string | null | undefined> = [], exIds: Array<string | null | undefined> = [], expId?: string | null, absOnly = false): Promise<boolean> => {
  if (!tok) return true
  if (pinToks.has(tok)) { failCls(tok, exDets, exKeys, exIds); return false }
  for (const d of exDets) if (!d.is_builtin && hasCTok(d.system ?? '', safeId, tok)) {
   const c1 = recOwner(tok, d)
   if (c1) { failCls(tok, [c1, d, ...exDets], [c1.node_key, d.node_key, ...exKeys], [c1.id, d.id, ...exIds])
    errs.push('检测到多个自定义节点携带同一归属令牌，已保留恢复记录以防误认'); return false } }
  try { const found = await discTok(safeId, tok)
   const c2 = recOwner(tok, found)
   if (c2 && found) { failCls(tok, [c2, found, ...exDets], [c2.node_key, found.node_key, ...exKeys], [c2.id, found.id, ...exIds])
    errs.push('检测到多个自定义节点携带同一归属令牌，已保留恢复记录以防误认'); return false }
   const owner = found ?? ownByTok.get(tok), wc = walConf(tok, expId) ?? walConf(tok, owner?.id)
   if (wc) { failCls(tok, [...(owner ? [owner] : []), ...exDets], [...wc.keys, owner?.node_key, ...exKeys], [...wc.ids, owner?.id, expId, ...exIds])
    errs.push('检测到归属令牌与未决目标节点不一致，已保留恢复记录以防误删'); return false }
   if (absOnly) { if (found) { failCls(tok, [found, ...exDets], [found.node_key, ...exKeys], [found.id, expId, ...exIds])
     errs.push('检测到待退役归属令牌仍存在于活动节点，已保留恢复记录'); return false }
    const prev = ownByTok.get(tok)
    if (prev && ((expId && prev.id !== expId) || failIds.has(prev.id))) { failCls(tok, [prev, ...exDets], [prev.node_key, ...exKeys], [prev.id, expId, ...exIds])
     errs.push('检测到待退役归属令牌关联未完成节点，已保留恢复记录'); return false }
    return true }
   if (owner && expId && owner.id !== expId) {
    failCls(tok, [owner, ...exDets], [owner.node_key, ...exKeys], [owner.id, expId, ...exIds])
    errs.push('检测到归属令牌指向其他自建节点，已保留恢复记录以防误认'); return false }
   return true } catch (discErr) {
   failCls(tok, [...exDets, ...dupDets(discErr)], exKeys, exIds)
   errs.push(fmtErr(discErr, '核验自建节点归属令牌唯一性失败').message); return false } }
 const assertTokUniq = async (tok: string | null | undefined, curDetail?: NDet): Promise<void> => {
  if (!tok) return
  if (pinToks.has(tok)) throw new Error('检测到重复自建节点归属令牌，已中止清理')
  const throwDup = (matches: NDet[], msg = '检测到多个自定义节点携带同一归属令牌，已保留恢复记录以防误认') => {
   const e = new Error(msg) as Error & { duplicateMatches?: NDet[] }; e.duplicateMatches = matches; throw e }
  if (curDetail && !curDetail.is_builtin && hasCTok(curDetail.system ?? '', safeId, tok)) {
   const c1 = recOwner(tok, curDetail); if (c1) throwDup([c1, curDetail]) }
  const found = await discTok(safeId, tok)
  const c2 = recOwner(tok, found); if (c2 && found) throwDup([c2, found, ...(curDetail ? [curDetail] : [])])
  const owner = found ?? ownByTok.get(tok)
  if (walConf(tok, curDetail?.id) ?? walConf(tok, owner?.id)) {
   throwDup([...(owner ? [owner] : []), ...(curDetail ? [curDetail] : [])], '检测到归属令牌与未决目标节点不一致，已保留恢复记录以防误删') }
  if (owner && curDetail && owner.id !== curDetail.id) throwDup([owner, curDetail]) }
 const enrollClean = async (detail: NDet, tok: string | undefined, sKey: string, preferPending: boolean, prechecked = false): Promise<'cleaned' | 'skipped'> => {
  const sys = detail.system ?? '', matchesTok = !detail.is_builtin && Boolean(tok) && hasCTok(sys, safeId, tok!)
  if (!prechecked) for (const t of new Set([tok, !detail.is_builtin ? origTok(sys, safeId) : null])) await assertTokUniq(t, detail)
  const effTpl = resolveCustomTpl(detail, sKey, preferPending, tok)
  if (matchesTok && tok) { kCustIds.add(detail.id); actCIds.add(detail.id)
   assertSlotSafe(detail, tok); enrollCustom(detail, tok, effTpl)
   await cleanCustom(detail, tok, effTpl, sKey, true)
   markClean([detail.id]); actCIds.delete(detail.id)
   if (ownsWal(detail.node_key, detail.id, tok)) delete wals[detail.node_key]
   retToks(detail.node_key, tok, false); return 'cleaned' }
  if (!detail.is_builtin && tok && hasTrace(sys)) { assertSlotSafe(detail, tok); enrollCustom(detail, tok, effTpl)
   throw new Error(`独立节点「${detail.node_key}」的模组归属边界标记不完整，已保留记录以防误删您的自定义内容`) }
  return 'skipped' }
 const migrateSlot = (fromKey: string, targetId: string, liveKey: string, hasTokFlag: boolean, keepFromPatched = false): boolean => {
  if (!isSlotVacant(liveKey)) { failNode([targetId], [fromKey, liveKey]); errs.push(`节点「${liveKey}」目标槽位非空，已保留原基线快照供下一轮统一对齐`); return false }
  const otherPId = pIds[fromKey] !== undefined && pIds[fromKey] !== targetId
  actPKeys.add(liveKey); pIds[liveKey] = targetId
  if (pIds[fromKey] === targetId) delete pIds[fromKey]
  const srcBkp = bkps[fromKey], srcWal = wals[fromKey]
  if (!hasTokFlag && srcBkp && (srcBkp.targetNodeId === targetId || (!srcBkp.targetNodeId && !otherPId))) {
   bkps[liveKey] = { ...srcBkp, targetNodeId: targetId }; if (!keepFromPatched) delete bkps[fromKey] }
  if (srcWal && (srcWal.targetNodeId === targetId || (!srcWal.targetNodeId && !otherPId))) { wals[liveKey] = srcWal; delete wals[fromKey] }
  if (!keepFromPatched && pIds[fromKey] === undefined && bkps[fromKey] === undefined) actPKeys.delete(fromKey)
  saveCkpt(); return true }
 const cleanCustom = async (detail: NDet, expTok: string | undefined, recTpl: string | undefined, srcK?: string | null, prechecked = false): Promise<void> => {
  const nKey = detail.node_key, dLiveTok = !detail.is_builtin ? origTok(detail.system ?? '', safeId) : null
  if (!prechecked) for (const t of new Set([expTok, dLiveTok])) await assertTokUniq(t, detail)
  if (failIds.has(detail.id) || failKeys.has(nKey) || (srcK && failKeys.has(srcK)) || (expTok && pinToks.has(expTok)) || (dLiveTok && pinToks.has(dLiveTok))) {
   throw new Error(`独立节点「${nKey}」关联未决冲突或重复归属令牌，已中止清理`) }
  assertSlotSafe(detail, expTok)
  if (hasBlkWal(detail, nKey, srcK)) throw new Error(`独立节点「${nKey}」仍有未确认完成的后台变更，已保留恢复记录供稍候重试`)
  const deps = findForeignDependentPackNames(instMap, nKey, safeId, detail.id)
  if (deps.length > 0 || hasForeignContentLayers(detail.system ?? '', safeId)) throw new Error(`独立节点「${nKey}」仍存在其他模组依赖（${deps.join('、') || '外层挂载块'}），请先停用依赖模组`)
  const hasUncustWal = (): boolean => [
   wals[nKey], ...(srcK && srcK !== nKey ? [wals[srcK]] : []),
   ...Object.values(wals).filter(u => u.targetNodeId === detail.id || (Boolean(expTok) && getWalTok(u) === expTok)),
  ].some(u => Boolean(u) && (u!.kind === 'delete' || (u!.kind === 'patch' && !isPatchDone(detail, u!))))
  const { strippedSystem, hadValidBlock } = stripOwnedCustomBlock(detail.system ?? '', safeId, expTok)
  if (!hadValidBlock) { if (hasTrace(detail.system ?? '')) throw new Error(`独立节点「${nKey}」的模组归属边界标记不完整，已保留记录以防误删您的自定义内容`)
   if (hasUncustWal()) await fenceVer(detail, `卸载模组「${record.pack.name}」收敛未决变更围栏`)
   return }
  if (hasTrace(strippedSystem)) throw new Error(`独立节点「${nKey}」仍残留模组标记，已保留记录以防破坏自定义内容`)
  const prvLWal = wals[nKey], diffSrc = Boolean(srcK && srcK !== nKey)
  const priorSrcWal = diffSrc ? wals[srcK!] : undefined
  const onCustErr = (wErr: unknown): never => { if (isPreErr(wErr) && !is404(wErr)) {
    restoreWal(nKey, prvLWal); if (diffSrc) restoreWal(srcK!, priorSrcWal)
    saveCkpt() } else if (is404(wErr)) { wals[nKey] = { ...wals[nKey], targetNodeId: detail.id, startedAt: prvLWal?.startedAt }; saveCkpt() }
   throw wErr }
  const canDelWhole = Boolean(expTok) && hasCTok(detail.system ?? '', safeId, expTok!) && strippedSystem === '' && recTpl !== undefined && (detail.user_template ?? '') === recTpl
  if (canDelWhole) { wals[nKey] = { kind: 'delete', targetNodeId: detail.id, originToken: expTok, initialUserTemplate: recTpl, startedAt: Date.now() }
   saveCkpt()
   try { await promptPlazaApi.deleteNode(detail.id, delPre(detail)) } catch (wErr) { onCustErr(wErr) } } else if (strippedSystem !== (detail.system ?? '')) {
   wals[nKey] = { kind: 'patch', targetNodeId: detail.id, priorSystem: detail.system ?? '', writtenSystem: strippedSystem,
    originToken: expTok ?? getWalTok(prvLWal), initialUserTemplate: recTpl ?? prvLWal?.initialUserTemplate,
    targetOwnedUserTemplate: prvLWal?.targetOwnedUserTemplate, startedAt: Date.now(), }
   saveCkpt()
   try { await promptPlazaApi.updateNode(nKey, { ...sysPre(detail), system: strippedSystem, change_summary: `卸载模组「${record.pack.name}」并保留用户自定义内容` }, { silentGlobalFeedback: true }) } catch (wErr) { onCustErr(wErr) }
  } else if (hasUncustWal()) { await fenceVer(detail, `卸载模组「${record.pack.name}」收敛未决变更围栏`) } }
 const reconcilePatch = async (detail: NDet, sKey: string): Promise<void> => { const nodeId = detail.id, liveKey = detail.node_key
  if (failIds.has(nodeId) || failKeys.has(sKey) || failKeys.has(liveKey)) { failNode([nodeId], [sKey, liveKey]); actPKeys.add(sKey); return }
  const detCTok = !detail.is_builtin ? origTok(detail.system ?? '', safeId) : null
  if (hasForeignPatch(sKey, nodeId) || hasForeignPatch(liveKey, nodeId) || isCust(nodeId, detail)) {
   failNode([nodeId], [sKey, liveKey], detCTok); actPKeys.add(sKey)
   errs.push(`节点「${liveKey}」所在键位存在其他归属记录或自建节点占用，已延后还原以防覆盖`); return }
  const curS = detail.system ?? ''
  const preSlotBackup = bkps[sKey] ?? (liveKey !== sKey && bkps[liveKey]?.targetNodeId === nodeId ? bkps[liveKey] : undefined)
  const preSlotWal = wals[sKey], preLiveWal = liveKey !== sKey ? wals[liveKey] : undefined, needsRep = Boolean(preSlotBackup)
  const preVerTgtId = (!isCust(preSlotBackup?.targetNodeId) ? preSlotBackup?.targetNodeId : undefined) ??
   (!isCust(pIds[sKey]) ? pIds[sKey] : undefined) ?? (liveKey !== sKey && pIds[liveKey] === nodeId && !isCust(nodeId) ? nodeId : undefined) ??
   (isProvenPatch(detail, preSlotWal, needsRep) ? nodeId : undefined) ?? (isProvenPatch(detail, preLiveWal, needsRep) ? nodeId : undefined)
  if (hasBlkWal(detail, sKey, liveKey)) {
   failNode([preVerTgtId ? nodeId : null], [sKey, preVerTgtId ? liveKey : null]); actPKeys.add(sKey)
   errs.push(`节点「${liveKey}」仍有未确认完成的超时写入，为防止延迟落盘丢失原稿已保留恢复基线快照`); return }
  const idBoundElsewhere = cleanIds.has(nodeId) || Object.entries(pIds).some(([k, id]) => k !== sKey && k !== liveKey && id === nodeId) ||
   Object.entries(bkps).some(([k, b]) => k !== sKey && k !== liveKey && b.targetNodeId === nodeId)
  if (!preVerTgtId && (liveKey !== sKey || idBoundElsewhere || (preSlotBackup && !hasRepBlk(curS, safeId)) || (!preSlotBackup && (!hasAnyModBlock(curS, safeId) || hasRepBlk(curS, safeId) || origTok(curS, safeId) !== null)))) {
   failNode([], [sKey]); actPKeys.add(sKey)
   errs.push(preSlotBackup ? `节点「${sKey}」旧版记录缺少稳定目标 ID 且当前节点不含本模组替换标记，已保留恢复基线快照` : `节点「${sKey}」旧版记录缺少稳定目标 ID 且当前节点不含本模组标记，已保留恢复记录`); return }
  let effKey = sKey
  if (liveKey !== sKey) { if (bkps[liveKey]?.targetNodeId === nodeId || pIds[liveKey] === nodeId || wals[liveKey]?.targetNodeId === nodeId) effKey = liveKey
   else if (migrateSlot(sKey, nodeId, liveKey, false)) effKey = liveKey; else { actPKeys.add(sKey); return } }
  const finPatchSlots = () => { markClean([nodeId]); actPKeys.delete(sKey); actPKeys.delete(effKey); actPKeys.delete(liveKey)
   delete pIds[effKey]; delete pIds[liveKey]
   if (sKey === effKey || pIds[sKey] === nodeId) delete pIds[sKey]
   delete bkps[effKey]; delete bkps[liveKey]; if (sKey === effKey) delete bkps[sKey]
   if (ownsWal(effKey, nodeId)) delete wals[effKey]
   if (ownsWal(liveKey, nodeId)) delete wals[liveKey]
   saveCkpt() }
  const backup = bkps[effKey] ?? bkps[liveKey]
  if (cleanIds.has(nodeId) && !backup && !hasTrace(curS)) { finPatchSlots(); return }
  try { const restoredSys = backup ? restoreReplacedModBlock(curS, safeId, backup.baselineSystem) : stripModProtocolBlock(curS, safeId)
   if (hasTrace(restoredSys)) throw new Error(`节点「${liveKey}」仍残留替换块但缺少基线快照，已保留记录以防丢失恢复线索`)
   if (restoredSys !== curS) { const prvSWal = wals[effKey]
    const prvLWal = liveKey !== effKey ? wals[liveKey] : undefined
    pIds[effKey] = nodeId
    if (backup) bkps[effKey] = { ...backup, targetNodeId: nodeId }
    wals[effKey] = { kind: 'patch', targetNodeId: nodeId, priorSystem: curS, writtenSystem: restoredSys,
     originToken: prvSWal?.originToken, initialUserTemplate: prvSWal?.initialUserTemplate,
     targetOwnedUserTemplate: prvSWal?.targetOwnedUserTemplate, startedAt: Date.now(), }
    actPKeys.add(effKey); saveCkpt()
    try {
     await promptPlazaApi.updateNode(liveKey, { ...sysPre(detail), system: restoredSys, change_summary: `卸载模组「${record.pack.name}」并恢复原指令` }, { silentGlobalFeedback: true })
    } catch (wErr) { if (isPreErr(wErr) && !is404(wErr)) {
      restoreWal(effKey, prvSWal ? { ...prvSWal, targetNodeId: prvSWal.targetNodeId ?? nodeId } : { kind: 'patch', targetNodeId: nodeId })
      if (liveKey !== effKey) restoreWal(liveKey, prvLWal)
      saveCkpt() } else if (is404(wErr)) { wals[effKey] = { ...wals[effKey], targetNodeId: nodeId, startedAt: prvSWal?.startedAt }
      saveCkpt() }
     throw wErr } } else { const hasUnpatchWal = [
     wals[effKey], wals[sKey], wals[liveKey], ...Object.values(wals).filter(u => u.targetNodeId === nodeId),
    ].some(u => Boolean(u) && !isCust(u!.targetNodeId, null, u) && (u!.kind === 'delete' || (u!.kind === 'patch' && !isPatchDone(detail, u!))))
    if (hasUnpatchWal) await fenceVer(detail, `卸载模组「${record.pack.name}」收敛未决更新围栏`) }
   finPatchSlots() } catch (err) { if (is404(err) && (await idsGone([nodeId]))) { actCIds.delete(nodeId); finPatchSlots(); return }
   failNode([nodeId], [effKey, liveKey]); actPKeys.add(effKey)
   errs.push(fmtErr(err, `还原节点「${liveKey}」失败`).message) } }
 { interface SlotMove { oldKey: string; liveKey: string; targetId: string; clearsOldWal: boolean; um?: WalMut; effectiveTok?: string
   movesBackup: boolean; backup?: ReplacedNodeBackup; movesPatchedId: boolean; wasPatched: boolean
   ownedTok?: string; ownedTpl?: string; pendingTok?: string; pendingTpl?: string }
  const candMap = new Map<string, SlotMove>(), bootMap = new Map<string, NDet>()
  let didAlign = false
  const preByTok = new Map<string, NDet[]>()
  for (const nodeId of Array.from(new Set([...record.createdNodeIds, ...actCIds]))) { if (failIds.has(nodeId) || cleanIds.has(nodeId)) continue
   try { const preDetail = await fetchById(nodeId)
    if (preDetail) { obsById.set(nodeId, preDetail)
     const cTok = !preDetail.is_builtin ? origTok(preDetail.system ?? '', safeId) : null
     if (cTok) { const arr = preByTok.get(cTok) ?? []; arr.push(preDetail); preByTok.set(cTok, arr) } } } catch (cAlignErr) { failNode([nodeId], []); keepEnr(nodeId)
    errs.push(fmtErr(cAlignErr, `对齐自建节点「${nodeId}」失败`).message) } }
  for (const [cTok, list] of preByTok) {
   if (list.length > 1) { for (const d of list) keepEnr(d.id)
    bootMap.delete(cTok); let extraDup: NDet[] = []
    try { await discTok(safeId, cTok) } catch (e) { extraDup = dupDets(e) }
    failCls(cTok, [...list, ...extraDup]); errs.push('检测到多个自建节点携带同一归属令牌，已保留恢复记录') } else if (list.length === 1) {
    const wc = walConf(cTok, list[0].id)
    if (wc) { bootMap.delete(cTok); failCls(cTok, list, [list[0].node_key, ...wc.keys], [list[0].id, ...wc.ids])
     errs.push('检测到归属令牌与未决目标节点不一致，已保留恢复记录以防误删')
    } else { bootMap.set(cTok, list[0]); recOwner(cTok, list[0]) } } }
  const tokSlots = new Map<string, Set<string>>()
  const regTokSlot = (tok: string | undefined, k: string, forceVerify = false) => { if (!tok) return
   if (pinToks.has(tok)) { bootMap.delete(tok); failCls(tok, [], [k]); return }
   if (!forceVerify && preByTok.has(tok)) return
   let s = tokSlots.get(tok); if (!s) { s = new Set<string>(); tokSlots.set(tok, s) } s.add(k) }
  for (const [cTok, list] of preByTok) if (list.length === 1) regTokSlot(cTok, list[0].node_key, true)
  for (const [k, um] of Object.entries(wals)) regTokSlot(effWTok(k, um), k, true)
  for (const [k, tok] of Object.entries(pToks)) regTokSlot(tok, k, true)
  for (const [k, tok] of Object.entries(oToks)) regTokSlot(tok, k, true)
  for (const [tok, slotKeys] of tokSlots) { let found: NDet | null = null
   try { found = await discTok(safeId, tok) } catch (discErr) {
    for (const d of preByTok.get(tok) ?? []) keepEnr(d.id)
    bootMap.delete(tok); failCls(tok, [...(preByTok.get(tok) ?? []), ...dupDets(discErr)], Array.from(slotKeys))
    errs.push(fmtErr(discErr, '预对齐自建节点归属令牌失败').message); continue }
   const c0 = recOwner(tok, found)
   if (c0 && found) { bootMap.delete(tok); failCls(tok, [c0, found, ...(preByTok.get(tok) ?? [])], Array.from(slotKeys), [c0.id, found.id])
    errs.push('检测到多个自定义节点携带同一归属令牌，已保留恢复记录以防误认'); continue }
   const wc0 = walConf(tok, found?.id ?? ownByTok.get(tok)?.id ?? null)
   if (wc0) { bootMap.delete(tok)
    failCls(tok, [...(found ? [found] : []), ...(preByTok.get(tok) ?? [])], [...Array.from(slotKeys), ...wc0.keys, ...(found ? [found.node_key] : [])], [...wc0.ids, ...(found ? [found.id] : [])])
    errs.push('检测到归属令牌与未决目标节点不一致，已保留恢复记录以防误删'); continue }
   const occ = found && !enrIds.has(found.id) && !Object.values(pToks).includes(tok) && !Object.entries(wals).some(([wk, wu]) => effWTok(wk, wu) === tok)
    ? Array.from(obsById.values()).find(d => enrIds.has(d.id) && d.id !== found!.id && !d.is_builtin && origTok(d.system ?? '', safeId) === null && oToks[d.node_key] === tok)
    : undefined
   if (occ && found) { bootMap.delete(tok); failCls(tok, [found, occ], [...Array.from(slotKeys), found.node_key, occ.node_key], [found.id, occ.id])
    errs.push('检测到归属令牌与已登记自建节点槽位冲突，已保留恢复记录'); continue }
   if (found) { bootMap.set(tok, found); obsById.set(found.id, found)
    kCustIds.add(found.id); actCIds.add(found.id); didAlign = true } }
  const alignItems: Array<{ oldKey: string; targetId: string | undefined; um?: WalMut; fromPMap: boolean }> = [
   ...Object.entries({ ...wals }).map(([oldKey, um]) => { const infTok = !um.targetNodeId ? infSlotTok(oldKey, um) : undefined
    return { oldKey, targetId: um.targetNodeId ?? (infTok ? bootMap.get(infTok)?.id : undefined), um, fromPMap: false } }),
   ...Object.entries({ ...pIds }).filter(([, targetId]) => !isCust(targetId))
    .map(([oldKey, targetId]) => ({ oldKey, targetId, um: ownsWal(oldKey, targetId) ? wals[oldKey] : undefined, fromPMap: true })),
   ...Object.entries({ ...bkps }).filter(([, bkp]) => Boolean(bkp.targetNodeId) && !isCust(bkp.targetNodeId))
    .map(([oldKey, bkp]) => ({ oldKey, targetId: bkp.targetNodeId, um: bkp.targetNodeId && ownsWal(oldKey, bkp.targetNodeId) ? wals[oldKey] : undefined, fromPMap: true })), ]
  for (const { oldKey, targetId, um, fromPMap } of alignItems) { const pairKey = targetId ? `${oldKey}\0${targetId}` : '', umTok = effWTok(oldKey, um)
   if (failKeys.has(oldKey) || (umTok && pinToks.has(umTok))) { failNode([targetId], [oldKey], umTok); if (fromPMap) actPKeys.add(oldKey); continue }
   if (!targetId || failIds.has(targetId) || cleanIds.has(targetId) || candMap.has(pairKey)) continue
   let detail: NDet | null = obsById.get(targetId) ?? null
   if (!detail) { try { detail = await fetchById(targetId); if (detail) obsById.set(targetId, detail) } catch (alignErr) { failNode([targetId], [oldKey], umTok)
     if (fromPMap) actPKeys.add(oldKey)
     errs.push(fmtErr(alignErr, `对齐目标节点「${targetId}」失败`).message); continue } }
   if (!detail) { const checkWal = um ?? (fromPMap && ownsWal(oldKey, targetId) ? wals[oldKey] : undefined)
    if (isBlkWin(null, checkWal)) { failNode([targetId], [oldKey], effWTok(oldKey, checkWal))
     if (fromPMap) actPKeys.add(oldKey)
     errs.push(`节点「${oldKey}」存在未确认完成的超时变更请求，已保留恢复记录`); continue }
    if (umTok && !(await chkUniq(umTok, [], [oldKey], [targetId], targetId, true))) { if (fromPMap) actPKeys.add(oldKey); continue }
    retireAbsent(oldKey, targetId, umTok)
    if (!fromPMap && ownsWal(oldKey, targetId, umTok)) delete wals[oldKey]
    didAlign = true; continue }
   const detailTok = !detail.is_builtin ? origTok(detail.system ?? '', safeId) : null
   if ((detailTok && !(await chkUniq(detailTok, [detail], [oldKey, detail.node_key], [targetId, detail.id], detail.id))) ||
       (umTok && umTok !== detailTok && !(await chkUniq(umTok, [detail], [oldKey, detail.node_key], [targetId, detail.id], detail.id)))) {
    if (fromPMap) actPKeys.add(oldKey); continue }
   if (failIds.has(detail.id) || failKeys.has(detail.node_key) || (detailTok && pinToks.has(detailTok)) || (umTok && pinToks.has(umTok))) {
    failCls(detailTok ?? umTok, [detail], [oldKey, detail.node_key], [targetId, detail.id]); if (fromPMap) actPKeys.add(oldKey); continue }
   const liveWalAtDest = wals[detail.node_key] && ownsWal(detail.node_key, detail.id, umTok) ? wals[detail.node_key] : undefined
   if ((fromPMap ? hasBlkWal(detail, oldKey, detail.node_key) : isBlkWin(detail, um)) || (liveWalAtDest !== undefined && isBlkWin(detail, liveWalAtDest))) {
    failNode([targetId], [oldKey, detail.node_key], umTok, effWTok(detail.node_key, liveWalAtDest))
    if (fromPMap) actPKeys.add(oldKey)
    errs.push(`节点「${detail.node_key}」仍有未确认完成的超时写入或未确认完成的后台变更请求，已保留恢复记录供稍候重试`); continue }
   if (detail.node_key !== oldKey) { const clearsOldWal = wals[oldKey] !== undefined && ownsWal(oldKey, detail.id, umTok)
    const ownedWal = clearsOldWal ? wals[oldKey] : undefined, ownedWalTok = effWTok(oldKey, ownedWal)
    const customMove = isCust(detail.id, detail, ownedWal ?? um)
    const srcBkp = bkps[oldKey]
    const walProvesPatch = !customMove && isProvenPatch(detail, ownedWal, Boolean(srcBkp))
    const movesBackup = !customMove && srcBkp !== undefined && (srcBkp.targetNodeId === detail.id || (!srcBkp.targetNodeId && (pIds[oldKey] === detail.id || (pIds[oldKey] === undefined && walProvesPatch))))
    const tokAtOld = !fromPMap ? oToks[oldKey] : undefined
    const mOwnTok = tokAtOld && (ownedWalTok === tokAtOld || (!detail.is_builtin && hasCTok(detail.system ?? '', safeId, tokAtOld))) ? tokAtOld : undefined
    const pTokAtOld = !fromPMap ? pToks[oldKey] : undefined
    const mPendTok = pTokAtOld && (ownedWalTok === pTokAtOld || (!detail.is_builtin && hasCTok(detail.system ?? '', safeId, pTokAtOld))) ? pTokAtOld : undefined
    const effectiveTok = customMove ? (mOwnTok ?? mPendTok ?? ownedWalTok ?? umTok) : undefined
    candMap.set(pairKey, { oldKey, liveKey: detail.node_key, targetId: detail.id, clearsOldWal, um: ownedWal, effectiveTok,
     movesBackup, backup: movesBackup ? { ...srcBkp!, targetNodeId: detail.id } : undefined, movesPatchedId: !customMove && pIds[oldKey] === detail.id,
     wasPatched: !customMove && actPKeys.has(oldKey) && (pIds[oldKey] === detail.id || srcBkp?.targetNodeId === detail.id || (pIds[oldKey] === undefined && walProvesPatch)),
     ownedTok: mOwnTok, ownedTpl: mOwnTok ? remOTpls[oldKey] : undefined, pendingTok: mPendTok, pendingTpl: mPendTok ? remPTpls[oldKey] : undefined, }) } }
  for (const nodeId of Array.from(new Set([...record.createdNodeIds, ...actCIds]))) { if (failIds.has(nodeId) || cleanIds.has(nodeId)) { if (failIds.has(nodeId)) keepEnr(nodeId); continue }
   let cDet: NDet | null = obsById.get(nodeId) ?? null
   if (!cDet) { try { cDet = await fetchById(nodeId); if (cDet) obsById.set(nodeId, cDet) } catch (cAlignErr) {
     failNode([nodeId], []); keepEnr(nodeId)
     errs.push(fmtErr(cAlignErr, `对齐自建节点「${nodeId}」失败`).message); continue } }
   if (!cDet || cDet.is_builtin) continue
   const customCTok = origTok(cDet.system ?? '', safeId)
   if (customCTok && !(await chkUniq(customCTok, [cDet], [cDet.node_key], [nodeId, cDet.id], cDet.id))) { keepEnr(nodeId); continue }
   if (failIds.has(cDet.id) || failKeys.has(cDet.node_key) || (customCTok && pinToks.has(customCTok))) {
    failCls(customCTok ?? undefined, [cDet], [cDet.node_key], [nodeId, cDet.id]); keepEnr(nodeId); continue }
   const matchSrcKeys = new Set<string>([
    ...Object.entries(oToks).filter(([k, tok]) => k !== cDet!.node_key && !failKeys.has(k) && Boolean(tok) && !pinToks.has(tok) && hasCTok(cDet!.system ?? '', safeId, tok)).map(([k]) => k),
    ...Object.entries(pToks).filter(([k, tok]) => k !== cDet!.node_key && !failKeys.has(k) && Boolean(tok) && !pinToks.has(tok) && hasCTok(cDet!.system ?? '', safeId, tok)).map(([k]) => k),
    ...Object.entries(wals).filter(([k, um]) => { const wTok = !um.targetNodeId ? infSlotTok(k, um) : undefined; return k !== cDet!.node_key && !failKeys.has(k) && Boolean(wTok && !pinToks.has(wTok) && bootMap.get(wTok)?.id === cDet!.id) }).map(([k]) => k), ])
   for (const tokSrcKey of matchSrcKeys) { const cPairKey = `${tokSrcKey}\0${cDet.id}`
    if (candMap.has(cPairKey)) continue
    const oTokAtSrc = oToks[tokSrcKey]
    const mOwnTok = oTokAtSrc && hasCTok(cDet.system ?? '', safeId, oTokAtSrc) ? oTokAtSrc : undefined
    const pTokAtSrc = pToks[tokSrcKey]
    const mPendTok = pTokAtSrc && hasCTok(cDet.system ?? '', safeId, pTokAtSrc) ? pTokAtSrc : undefined
    const legacyWal = wals[tokSrcKey]
    if (legacyWal?.targetNodeId && legacyWal.targetNodeId !== cDet.id && ((mOwnTok && walBinds(tokSrcKey, legacyWal, mOwnTok)) || (mPendTok && walBinds(tokSrcKey, legacyWal, mPendTok)))) {
     failCls(mOwnTok ?? mPendTok, [cDet], [cDet.node_key, tokSrcKey], [nodeId, cDet.id, legacyWal.targetNodeId])
     keepEnr(nodeId); errs.push('检测到归属令牌与未决目标节点不一致，已保留恢复记录以防误删'); break }
    const wTokAtSrc = legacyWal && legacyWal.targetNodeId === undefined ? infSlotTok(tokSrcKey, legacyWal) : undefined
    const matchedWalTok = wTokAtSrc && hasCTok(cDet.system ?? '', safeId, wTokAtSrc) ? wTokAtSrc : undefined
    if (hasBlkWal(cDet, cDet.node_key, tokSrcKey)) {
     failNode([nodeId, cDet.id], [cDet.node_key, tokSrcKey], mOwnTok, mPendTok, matchedWalTok)
     keepEnr(nodeId); errs.push(`独立节点「${cDet.node_key}」仍有未确认完成的后台变更，已保留恢复记录供稍候重试`); break }
    const effectiveTok = mOwnTok ?? mPendTok ?? matchedWalTok
    const matchedLegacyWal = legacyWal && legacyWal.targetNodeId === undefined && Boolean(effectiveTok) && ownsWal(tokSrcKey, cDet.id, effectiveTok) ? legacyWal : undefined
    candMap.set(cPairKey, { oldKey: tokSrcKey, liveKey: cDet.node_key, targetId: cDet.id, clearsOldWal: matchedLegacyWal !== undefined, um: matchedLegacyWal, effectiveTok,
     movesBackup: false, movesPatchedId: false, wasPatched: false, ownedTok: mOwnTok, ownedTpl: mOwnTok ? remOTpls[tokSrcKey] : undefined,
     pendingTok: mPendTok, pendingTpl: mPendTok ? remPTpls[tokSrcKey] : undefined, }) } }
  let accMoves = Array.from(candMap.values())
  const preFailKeys = new Set(failKeys)
  const isMoveRejected = (m: SlotMove): boolean => { const mWTok = getWalTok(m.um)
   return failIds.has(m.targetId) || preFailKeys.has(m.oldKey) || preFailKeys.has(m.liveKey) ||
    Boolean((m.effectiveTok && pinToks.has(m.effectiveTok)) || (m.ownedTok && pinToks.has(m.ownedTok)) || (m.pendingTok && pinToks.has(m.pendingTok)) || (mWTok && pinToks.has(mWTok))) }
  while (accMoves.length > 0) { const preFiltered: SlotMove[] = []
   for (const m of accMoves) { if (isMoveRejected(m)) {
     failNode([m.targetId], [m.clearsOldWal || m.movesBackup || m.movesPatchedId || m.wasPatched ? m.oldKey : null, m.liveKey], m.ownedTok, m.pendingTok, m.effectiveTok, getWalTok(m.um)); continue }
    preFiltered.push(m) }
   if (preFiltered.length !== accMoves.length) { accMoves = preFiltered; continue }
   const dstTgts = new Map<string, Set<string>>(), dstBkps = new Map<string, number>()
   const dstOToks = new Map<string, Set<string>>(), dstPToks = new Map<string, Set<string>>()
   const addToSetMap = (mp: Map<string, Set<string>>, k: string, v: string) => { let s = mp.get(k); if (!s) { s = new Set<string>(); mp.set(k, s) } s.add(v) }
   for (const m of accMoves) { addToSetMap(dstTgts, m.liveKey, m.targetId)
    if (m.movesBackup) dstBkps.set(m.liveKey, (dstBkps.get(m.liveKey) ?? 0) + 1)
    if (m.ownedTok) addToSetMap(dstOToks, m.liveKey, m.ownedTok)
    if (m.pendingTok) addToSetMap(dstPToks, m.liveKey, m.pendingTok) }
   const vacWal = new Set(accMoves.filter((m) => m.clearsOldWal && ownsWal(m.oldKey, m.targetId, m.effectiveTok)).map((m) => m.oldKey))
   const vacBkp = new Set(accMoves.filter((m) => m.movesBackup && (!bkps[m.oldKey]?.targetNodeId || bkps[m.oldKey]?.targetNodeId === m.targetId)).map((m) => m.oldKey))
   const vacPId = new Set(accMoves.filter((m) => m.movesPatchedId && pIds[m.oldKey] === m.targetId).map((m) => m.oldKey))
   const vacPSet = new Set(accMoves.filter((m) => m.wasPatched && (pIds[m.oldKey] === undefined || vacPId.has(m.oldKey)) && (bkps[m.oldKey] === undefined || vacBkp.has(m.oldKey))).map((m) => m.oldKey))
   const vacOTok = new Set(accMoves.filter((m) => Boolean(m.ownedTok) && oToks[m.oldKey] === m.ownedTok).map((m) => m.oldKey))
   const vacPTok = new Set(accMoves.filter((m) => Boolean(m.pendingTok) && pToks[m.oldKey] === m.pendingTok).map((m) => m.oldKey))
   const nextAcc: SlotMove[] = []
   for (const m of accMoves) { const customIncoming = Boolean(m.effectiveTok || m.ownedTok || m.pendingTok) || isCust(m.targetId, null, m.um)
    const unvacPMatch = !customIncoming && (pIds[m.liveKey] === m.targetId || (pIds[m.liveKey] === undefined && bkps[m.liveKey]?.targetNodeId === m.targetId))
    const occupied = (dstTgts.get(m.liveKey)?.size ?? 0) > 1 || (dstBkps.get(m.liveKey) ?? 0) > 1 ||
     (dstOToks.get(m.liveKey)?.size ?? 0) > 1 || (dstPToks.get(m.liveKey)?.size ?? 0) > 1 ||
     (wals[m.liveKey] !== undefined && !vacWal.has(m.liveKey) && !ownsWal(m.liveKey, m.targetId, m.effectiveTok)) ||
     (bkps[m.liveKey] !== undefined && !vacBkp.has(m.liveKey) && (m.movesBackup || customIncoming || bkps[m.liveKey]?.targetNodeId !== m.targetId)) ||
     (pIds[m.liveKey] !== undefined && !vacPId.has(m.liveKey) && (customIncoming || pIds[m.liveKey] !== m.targetId)) ||
     (actPKeys.has(m.liveKey) && !vacPSet.has(m.liveKey) && !unvacPMatch) ||
     (oToks[m.liveKey] !== undefined && !vacOTok.has(m.liveKey) && (!m.ownedTok || oToks[m.liveKey] !== m.ownedTok)) ||
     (pToks[m.liveKey] !== undefined && !vacPTok.has(m.liveKey) && (!m.pendingTok || pToks[m.liveKey] !== m.pendingTok))
    if (occupied) { failNode([m.targetId], [m.clearsOldWal || m.movesBackup || m.movesPatchedId || m.wasPatched ? m.oldKey : null, m.liveKey], m.ownedTok, m.pendingTok, m.effectiveTok)
     errs.push(`节点「${m.liveKey}」目标槽位尚未腾空，已保留「${m.oldKey}」原恢复记录供下一轮重试`); continue }
    nextAcc.push(m) }
   if (nextAcc.length === accMoves.length) break
   accMoves = nextAcc }
  if (accMoves.length > 0) { for (const m of accMoves) { if (m.clearsOldWal && ownsWal(m.oldKey, m.targetId, m.effectiveTok)) delete wals[m.oldKey]
    if (m.movesBackup && (!bkps[m.oldKey]?.targetNodeId || bkps[m.oldKey]?.targetNodeId === m.targetId)) delete bkps[m.oldKey]
    if (m.movesPatchedId && pIds[m.oldKey] === m.targetId) delete pIds[m.oldKey]
    if (m.ownedTok && oToks[m.oldKey] === m.ownedTok) { delete oToks[m.oldKey]; delete remOTpls[m.oldKey] }
    if (m.pendingTok && pToks[m.oldKey] === m.pendingTok) { delete pToks[m.oldKey]; delete remPTpls[m.oldKey] } }
   for (const m of accMoves) { if (m.wasPatched && pIds[m.oldKey] === undefined && bkps[m.oldKey] === undefined) actPKeys.delete(m.oldKey) }
   for (const m of accMoves) { if (m.um !== undefined) { const curDestWal = wals[m.liveKey]
     const chosenWal = curDestWal && ownsWal(m.liveKey, m.targetId, m.effectiveTok) && (curDestWal.startedAt ?? 0) > (m.um.startedAt ?? 0) ? curDestWal : m.um
     wals[m.liveKey] = { ...chosenWal, targetNodeId: chosenWal.targetNodeId ?? m.targetId } }
    if (m.movesBackup && m.backup) bkps[m.liveKey] = m.backup
    if (m.wasPatched || m.movesPatchedId || m.movesBackup) { pIds[m.liveKey] = m.targetId; actPKeys.add(m.liveKey) }
    if (m.ownedTok) { oToks[m.liveKey] = m.ownedTok; if (m.ownedTpl !== undefined) remOTpls[m.liveKey] = m.ownedTpl; else delete remOTpls[m.liveKey] }
    if (m.pendingTok) { pToks[m.liveKey] = m.pendingTok; if (m.pendingTpl !== undefined) remPTpls[m.liveKey] = m.pendingTpl; else delete remPTpls[m.liveKey] } }
   didAlign = true }
  if (didAlign) saveCkpt() }
 for (const nodeId of Array.from(new Set([...record.createdNodeIds, ...actCIds]))) { if (failIds.has(nodeId)) { keepEnr(nodeId); continue }
  if (cleanIds.has(nodeId)) { actCIds.delete(nodeId); continue }
  let resId: string = nodeId, curKey: string | null = null, srcK: string | null = null, attTok: string | undefined
  const sweepCustom = (tok: string | undefined) => { fin404([nodeId, resId], srcK, [curKey], tok)
   for (const k of [curKey, srcK]) if (k && bkps[k] === undefined && pIds[k] === resId) { actPKeys.delete(k); delete pIds[k] }
   for (const [uk, um] of Object.entries({ ...wals })) if ((um.targetNodeId === nodeId || um.targetNodeId === resId || (!um.targetNodeId && [curKey, srcK].includes(uk))) && ownsWal(uk, um.targetNodeId ?? resId, tok)) delete wals[uk]
   saveCkpt() }
  try { const cDet = await fetchById(nodeId)
   if (!cDet) { const blockingEntry = Object.values(wals).find((um) => um.targetNodeId === nodeId && um.kind === 'create' && inGraceWin(um))
    if (blockingEntry) { failNode([nodeId], [], getWalTok(blockingEntry)); keepEnr(nodeId); errs.push(`自建节点「${nodeId}」仍有未确认完成的创建请求，已保留恢复记录`); continue }
    let absentConflict = false
    for (const [uk, um] of Object.entries({ ...wals })) if (um.targetNodeId === nodeId && effWTok(uk, um)) {
     if (!(await chkUniq(effWTok(uk, um), [], [uk], [nodeId], nodeId, true))) absentConflict = true }
    if (absentConflict) { keepEnr(nodeId); continue }
    actCIds.delete(nodeId)
    for (const [uk, um] of Object.entries({ ...wals })) { const ut = effWTok(uk, um); if (um.targetNodeId === nodeId && ownsWal(uk, nodeId, ut)) { retToks(uk, ut); delete wals[uk] } }
    for (const [pk, pid] of Object.entries({ ...pIds })) if (pid === nodeId && bkps[pk] === undefined) { delete pIds[pk]; actPKeys.delete(pk) }
    markClean([nodeId]); saveCkpt(); continue }
   resId = cDet.id; curKey = cDet.node_key; srcK = findSrcKey(cDet) ?? curKey
   if (failIds.has(resId) || failKeys.has(curKey)) { failNode([nodeId, resId], [curKey]); keepEnr(nodeId); continue }
   if (cleanIds.has(resId)) { markClean([nodeId, resId]); actCIds.delete(nodeId); saveCkpt(); continue }
   if (hasBlkWal(cDet, curKey, srcK)) throw new Error(`独立节点「${curKey}」仍有未确认完成的后台变更，已保留恢复记录供稍候重试`)
   const sys = cDet.system ?? '', liveCustomTok = !cDet.is_builtin ? origTok(sys, safeId) : null
   const pickOwnedTok = (k: string) => oToks[k] && !pinToks.has(oToks[k]) && hasCTok(sys, safeId, oToks[k]) ? oToks[k] : undefined
   const pickWalTok = (k: string) => (!wals[k]?.targetNodeId && !failKeys.has(k)) || wals[k]?.targetNodeId === resId ? effWTok(k, wals[k]) : undefined
   const expTok = pickOwnedTok(srcK) ?? pickOwnedTok(curKey) ?? pToks[srcK] ?? pToks[curKey] ?? pickWalTok(srcK) ?? pickWalTok(curKey) ?? oToks[srcK] ?? oToks[curKey]
   attTok = expTok ?? (liveCustomTok ?? undefined)
   if (!(await chkUniq(liveCustomTok, [cDet], [curKey, srcK], [nodeId, resId], resId)) || !(await chkUniq(expTok, [cDet], [curKey, srcK], [nodeId, resId], resId))) {
    keepEnr(nodeId); continue }
   if (failIds.has(resId) || failKeys.has(curKey) || (liveCustomTok && pinToks.has(liveCustomTok)) || (expTok && pinToks.has(expTok)) || (srcK !== curKey && failKeys.has(srcK))) {
    failCls(liveCustomTok ?? expTok, [cDet], [curKey, srcK], [nodeId, resId]); keepEnr(nodeId)
    errs.push(`独立节点「${curKey}」归属令牌存在冲突或关联未决恢复记录，已延后清理`); continue }
   assertSlotSafe(cDet, expTok)
   const recTpl = resolveCustomTpl(cDet, srcK, false, expTok)
   if (expTok) enrollCustom(cDet, expTok, recTpl)
   await cleanCustom(cDet, expTok, recTpl, srcK, true)
   sweepCustom(expTok) } catch (err) { if (is404(err) && (await idsGone([nodeId, resId])) && (await chkUniq(attTok, [], [curKey, srcK], [nodeId, resId], resId, true))) { sweepCustom(attTok); continue }
   failCls(attTok, dupDets(err), [curKey, srcK && ownsWal(srcK, resId, attTok) ? srcK : null], [nodeId, resId])
   if (enrIds.has(nodeId) || enrIds.has(resId)) actCIds.add(resId); else keepEnr(nodeId)
   errs.push(fmtErr(err, `清理自建节点 ${nodeId} 失败`).message) } }
 for (const [pKey, pndTok] of Object.entries({ ...pToks })) { if (pToks[pKey] === undefined) continue
  const rawPendWal = wals[pKey], rawWalTok = getWalTok(rawPendWal)
  let pWal = rawPendWal && (rawWalTok !== undefined ? rawWalTok === pndTok : rawPendWal.kind === 'create') ? rawPendWal : undefined
  let recId: string | null = pWal?.targetNodeId ?? null
  const pWalBinds = Boolean(pWal && walBinds(pKey, pWal, pndTok))
  if (recId) { if (failIds.has(recId) || failKeys.has(pKey) || pinToks.has(pndTok) || (rawWalTok !== undefined && pinToks.has(rawWalTok))) {
    failCls(pndTok, [], [pKey], [recId]); if (rawWalTok) pinTokens(rawWalTok); continue }
   if (cleanIds.has(recId)) { if (ownsWal(pKey, recId, rawWalTok ?? pndTok)) delete wals[pKey]
    if (pWalBinds && !pinToks.has(pndTok)) { delete pToks[pKey]; delete remPTpls[pKey] }
    saveCkpt(); pWal = undefined; recId = null
    if (pToks[pKey] === undefined) continue } } else if (failKeys.has(pKey) || pinToks.has(pndTok)) { failCls(pndTok, [], [pKey]); continue }
  const fbPendTpl = remPTpls[pKey] ?? remOTpls[pKey] ?? pWal?.initialUserTemplate
  const rstPend = () => { pToks[pKey] = pndTok
   if (fbPendTpl !== undefined) remPTpls[pKey] = fbPendTpl }
  let sameKeyDetail: NDet | null = null
  if (recId) { let tDet: NDet | null = null
   try { tDet = await fetchById(recId) } catch (idErr) { failNode([recId], [pKey], pndTok); rstPend()
    errs.push(fmtErr(idErr, `对账挂起目标节点「${recId}」失败`).message); continue }
   if (!tDet) { if (isBlkWin(null, pWal)) { failNode([recId], [pKey], pndTok); rstPend()
     errs.push(`节点「${pKey}」仍有未确认完成的超时写入请求，已保留归属凭证以防延迟落盘`); continue }
    if (pWalBinds && !(await chkUniq(pndTok, [], [pKey], [recId], recId, true))) { rstPend(); continue }
    markClean([recId]); actCIds.delete(recId)
    delete wals[pKey]
    if (pWalBinds && !pinToks.has(pndTok)) { delete pToks[pKey]; delete remPTpls[pKey] }
    saveCkpt()
    if (pWalBinds) continue
    pWal = undefined; recId = null } else if (tDet.node_key === pKey) { sameKeyDetail = tDet } else { const targetKey = tDet.node_key
    const tgtTok = effWTok(pKey, pWal) ?? oToks[targetKey] ?? pndTok
    const tLiveTok = !tDet.is_builtin ? origTok(tDet.system ?? '', safeId) : null
    if (!(await chkUniq(tgtTok, [tDet], [pKey, targetKey], [recId, tDet.id], tDet.id)) || !(await chkUniq(tLiveTok, [tDet], [pKey, targetKey], [recId, tDet.id], tDet.id))) continue
    const tplForTarget = resolveCustomTpl(tDet, pKey, true, tgtTok)
    const targetMatchesTok = !tDet.is_builtin && Boolean(tgtTok) && hasCTok(tDet.system ?? '', safeId, tgtTok)
    if (failIds.has(tDet.id) || failKeys.has(targetKey) || failKeys.has(pKey) || (tgtTok && pinToks.has(tgtTok)) || (tLiveTok && pinToks.has(tLiveTok)) || !isSlotVacant(targetKey)) {
     failCls(tgtTok ?? tLiveTok ?? undefined, [tDet], [pKey, targetKey], [recId, tDet.id])
     if (!isSlotVacant(targetKey)) errs.push(`节点「${targetKey}」目标槽位尚未空闲，已保留原恢复记录供下一轮统一对齐`)
     continue }
    if (pWal) wals[targetKey] = pWal
    delete wals[pKey]
    if (targetMatchesTok && tgtTok) enrollCustom(tDet, tgtTok, tplForTarget)
    saveCkpt()
    let tgtMatchTok = pWalBinds
    try { if (cleanIds.has(tDet.id)) delete wals[targetKey]; else if (hasBlkWal(tDet, targetKey)) {
      tgtMatchTok = false; failNode([tDet.id], [targetKey], tgtTok)
      errs.push(`节点「${targetKey}」仍有未确认完成的后台变更请求，请稍候重试`) } else { const res = await enrollClean(tDet, tgtTok, pKey, true, true)
      if (res === 'cleaned') tgtMatchTok = tgtTok === pndTok
      markClean([tDet.id]); actCIds.delete(tDet.id); delete wals[targetKey] }
     if (tgtMatchTok && !pinToks.has(pndTok) && !failIds.has(tDet.id)) { delete pToks[pKey]; delete remPTpls[pKey] }
     saveCkpt() } catch (tErr) { if (is404(tErr) && (await idsGone([tDet.id])) && (await chkUniq(tgtTok, [], [pKey, targetKey], [recId, tDet.id], tDet.id, true))) {
      fin404([tDet.id], null, [targetKey], tgtTok); delete wals[targetKey]
      if (tgtMatchTok && !pinToks.has(pndTok)) { delete pToks[pKey]; delete remPTpls[pKey] }
      saveCkpt() } else { tgtMatchTok = false; failCls(tgtTok ?? tLiveTok ?? undefined, [tDet, ...dupDets(tErr)], [pKey, targetKey], [recId, tDet.id])
      errs.push(fmtErr(tErr, `对账清理重命名节点「${targetKey}」失败`).message) } }
    if (tgtMatchTok && pToks[pKey] === undefined) continue
    pWal = undefined; recId = null } }
  if (pToks[pKey] === undefined && !wals[pKey]) continue
  let resId: string | null = recId, resKey: string | null = null
  try { const lookupPendingKey = basePendKey(pKey)
   const rawAtPending = sameKeyDetail ?? (recId ? await fetchById(recId) : (lookupPendingKey ? await fetchByKey(lookupPendingKey) : null))
   const exactAtPending = !recId && rawAtPending && rawAtPending.node_key !== lookupPendingKey ? null : rawAtPending
   let pndDetail = exactAtPending
   if (!recId) { const discovered = await discTok(safeId, pndTok)
    pndDetail = discovered ?? (exactAtPending && !exactAtPending.is_builtin && hasTrace(exactAtPending.system ?? '') ? exactAtPending : null) }
   if (!pndDetail) { if (isBlkWin(null, pWal ?? wals[pKey])) { failNode([resId], [pKey], pndTok); rstPend()
     errs.push(`节点「${pKey}」仍有未确认完成的超时写入请求，已保留归属凭证以防延迟落盘`) } else if (!(await chkUniq(pndTok, [], [pKey], [recId], recId, true))) {
     rstPend() } else if (!pinToks.has(pndTok)) {
     markClean([recId]); if (recId) actCIds.delete(recId)
     delete pToks[pKey]; delete remPTpls[pKey]
     if (pWal && wals[pKey] === pWal) delete wals[pKey]
     saveCkpt() }
    continue }
   resId = pndDetail.id; resKey = pndDetail.node_key
   const pndLiveTok = !pndDetail.is_builtin ? origTok(pndDetail.system ?? '', safeId) : null
   if (!(await chkUniq(pndTok, [pndDetail], [pKey, resKey], [resId, recId], resId)) || !(await chkUniq(pndLiveTok, [pndDetail], [pKey, resKey], [resId, recId], resId))) { rstPend(); continue }
   if (failIds.has(resId) || failKeys.has(pKey) || failKeys.has(resKey) || pinToks.has(pndTok) || (pndLiveTok !== null && pinToks.has(pndLiveTok))) {
    failCls(pndTok ?? pndLiveTok ?? undefined, [pndDetail], [pKey, resKey], [resId, recId]); rstPend(); continue }
   if (cleanIds.has(resId)) { const walOwned = (pWal && wals[pKey] === pWal) || ownsWal(pKey, resId, pndTok)
    if (!pinToks.has(pndTok)) { delete pToks[pKey]; delete remPTpls[pKey] }
    if (walOwned) delete wals[pKey]
    saveCkpt(); continue }
   const recPendTpl = resolveCustomTpl(pndDetail, pKey, true, pndTok)
   if (hasBlkWal(pndDetail, pKey, resKey)) { failNode([resId, recId], [pKey, resKey], pndTok)
    pToks[pKey] = pndTok
    if (recPendTpl !== undefined) remPTpls[pKey] = recPendTpl
    errs.push(`节点「${pKey}」仍有未确认完成的后台变更请求，请稍候重试`); continue }
   const cleanRes = await enrollClean(pndDetail, pndTok, pKey, true, true)
   if (cleanRes === 'cleaned') { if (pWal && wals[pKey] === pWal) delete wals[pKey]
    fin404([resId, recId], pKey, [resKey], pndTok) } else if (!pinToks.has(pndTok)) {
    if (pWal && wals[pKey] === pWal && ownsWal(pKey, pndDetail.id, pndTok)) {
     if (pWal.kind === 'delete' || (pWal.kind === 'patch' && !isPatchDone(pndDetail, pWal))) {
      await fenceVer(pndDetail, `卸载模组「${record.pack.name}」收敛挂起节点未决围栏`) }
     delete wals[pKey] }
    delete pToks[pKey]; delete remPTpls[pKey] }
   saveCkpt() } catch (err) { if (is404(err) && (await idsGone([resId, recId])) && (await chkUniq(pndTok, [], [pKey, resKey], [resId, recId], resId ?? recId, true))) {
    if (pWal && wals[pKey] === pWal && !pinToks.has(pndTok)) delete wals[pKey]
    fin404([resId, recId], pKey, [resKey], pndTok)
    saveCkpt(); continue }
   failCls(pndTok, dupDets(err), [pKey, resKey], [resId, recId]); rstPend()
   errs.push(fmtErr(err, `对账清理挂起节点「${pKey}」失败`).message) } }
 for (const nodeKey of Array.from(new Set([...actPKeys, ...Object.keys(pIds), ...Object.keys(bkps)]))) { const sourceUnresolved = wals[nodeKey]
  const recId = (!isCust(pIds[nodeKey]) ? pIds[nodeKey] : undefined) ?? (!isCust(bkps[nodeKey]?.targetNodeId) ? bkps[nodeKey]?.targetNodeId : undefined) ?? null
  if (recId) { if (failIds.has(recId)) { failNode([recId], [nodeKey]); actPKeys.add(nodeKey); continue }
   if (cleanIds.has(recId)) { retireAbsent(nodeKey, recId); saveCkpt() } else { let tDet: NDet | null = null
    try { tDet = await fetchById(recId) } catch (idErr) { failNode([recId], [nodeKey]); actPKeys.add(nodeKey)
     errs.push(fmtErr(idErr, `读取目标节点「${recId}」失败`).message); continue }
    if (!tDet) { if (isBlkWin(null, sourceUnresolved)) { failNode([recId], [nodeKey]); actPKeys.add(nodeKey)
      errs.push(`节点「${nodeKey}」存在未确认完成的更新操作，已保留恢复记录`); continue }
     retireAbsent(nodeKey, recId); saveCkpt() } else if (tDet.node_key === nodeKey) { await reconcilePatch(tDet, nodeKey); continue
    } else {
     if (!migrateSlot(nodeKey, tDet.id, tDet.node_key, getWalTok(sourceUnresolved) !== undefined)) { actPKeys.add(nodeKey); continue }
     await reconcilePatch(tDet, tDet.node_key) } } }
  if (!actPKeys.has(nodeKey) && pIds[nodeKey] === undefined && bkps[nodeKey] === undefined) continue
  if (failKeys.has(nodeKey)) { if (bkps[nodeKey] !== undefined || pIds[nodeKey] !== undefined) actPKeys.add(nodeKey); continue }
  try { const rawOccupant = await fetchByKey(nodeKey)
   const occupantDetail = rawOccupant?.node_key === nodeKey ? rawOccupant : null
   const unresolvedAtKey = wals[nodeKey]
   if (!occupantDetail) { failNode([unresolvedAtKey?.targetNodeId], [nodeKey], getWalTok(unresolvedAtKey)); actPKeys.add(nodeKey)
    errs.push(isBlkWin(null, unresolvedAtKey) ? `节点「${nodeKey}」存在未确认完成的更新操作，已保留恢复记录` : `节点「${nodeKey}」在原键位未找到且缺少已核验的稳定目标 ID，已保留恢复基线以防节点已重命名`)
    continue }
   await reconcilePatch(occupantDetail, nodeKey) } catch (err) { failNode([], [nodeKey]); actPKeys.add(nodeKey)
   errs.push(fmtErr(err, `还原节点「${nodeKey}」失败`).message) } }
 for (const uKey of Object.keys({ ...wals })) { const curMut = wals[uKey]
  if (!curMut) continue
  const recId = curMut.targetNodeId ?? null, initWTok = effWTok(uKey, curMut)
  if (recId) { if (failIds.has(recId) || failKeys.has(uKey) || (initWTok !== undefined && pinToks.has(initWTok))) {
    failCls(initWTok, [], [uKey], [recId]); continue }
   if (cleanIds.has(recId)) { retireAbsent(uKey, recId, initWTok); if (ownsWal(uKey, recId, initWTok)) delete wals[uKey]; saveCkpt(); continue }
  } else if (handledWalKeys.has(uKey) || failKeys.has(uKey) || (initWTok !== undefined && pinToks.has(initWTok))) continue
  let resId: string | null = recId, resKey: string | null = null
  let enrId: string | null = recId, enrKey: string | null = null, attTok: string | undefined = initWTok
  try { if (curMut.kind === 'create' || curMut.kind === 'delete') { const isCre = curMut.kind === 'create'
    const cMutTok = !recId ? attTok : (curMut.originToken ?? attTok)
    if (cMutTok) attTok = cMutTok
    const rawItem = recId ? await fetchById(recId) : await fetchByKey(uKey)
    const exactItem = !recId && rawItem && rawItem.node_key !== uKey ? null : rawItem
    let iDet = exactItem
    if (!recId && cMutTok) { if (inGraceWin(curMut)) { failNode([resId], [uKey], cMutTok)
      if (isCre) pToks[uKey] = cMutTok
      if (isCre && curMut.initialUserTemplate !== undefined) remPTpls[uKey] = curMut.initialUserTemplate
      errs.push(`节点「${uKey}」仍有未确认完成的超时变更请求，已保留恢复凭证`); continue }
     const discovered = await discTok(safeId, cMutTok)
     iDet = discovered ?? (exactItem && !exactItem.is_builtin && hasTrace(exactItem.system ?? '') ? exactItem : null) } else if (!recId && (!exactItem || exactItem.is_builtin)) {
     if (inGraceWin(curMut)) { failNode([resId], [uKey], cMutTok); errs.push(`节点「${uKey}」仍有未确认完成的超时变更请求，已保留恢复凭证`); continue } }
    if (!iDet) { if ((isCre && inGraceWin(curMut)) || (!isCre && (inGraceWin(curMut) || (!recId && !cMutTok)))) {
      failNode([resId], recId ? [] : [uKey], cMutTok)
      if (isCre && cMutTok) pToks[uKey] = cMutTok
      if (isCre && curMut.initialUserTemplate !== undefined) remPTpls[uKey] = curMut.initialUserTemplate
      errs.push(`节点「${uKey}」仍有未确认完成或缺少稳定目标标识的变更请求，已保留恢复凭证`) } else if (!(cMutTok && !(await chkUniq(cMutTok, [], [uKey], [recId], recId, true)))) {
      markClean([recId]); if (recId) actCIds.delete(recId)
      retToks(uKey, cMutTok, isCre); delete wals[uKey]; saveCkpt() }
     continue }
    resId = iDet.id; resKey = iDet.node_key
    const itemLiveTok = !iDet.is_builtin ? origTok(iDet.system ?? '', safeId) : null
    if (!(await chkUniq(cMutTok, [iDet], [resKey, uKey], [resId, recId], resId)) || !(await chkUniq(itemLiveTok, [iDet], [resKey, uKey], [resId, recId], resId))) continue
    if (failIds.has(resId) || failKeys.has(resKey) || failKeys.has(uKey) || (cMutTok && pinToks.has(cMutTok)) || (itemLiveTok && pinToks.has(itemLiveTok))) {
     failCls(cMutTok ?? itemLiveTok ?? undefined, [iDet], [resKey, uKey], [resId, recId]); continue }
    if (cleanIds.has(resId)) { if (ownsWal(resKey, resId, cMutTok)) delete wals[resKey]
     retToks(uKey, cMutTok, isCre); delete wals[uKey]; saveCkpt(); continue }
    if (hasBlkWal(iDet, uKey, resKey)) { failNode([resId, recId], [resKey, ...(!recId ? [uKey] : [])], cMutTok)
     if (isCre && cMutTok) { pToks[uKey] = cMutTok
      if (curMut.initialUserTemplate !== undefined) remPTpls[uKey] = curMut.initialUserTemplate }
     errs.push(`节点「${uKey}」仍有未确认完成的后台变更请求，请稍候重试`); continue }
    const cdRes = await enrollClean(iDet, cMutTok, uKey, isCre, true)
    if (cdRes === 'cleaned') { enrId = iDet.id; enrKey = iDet.node_key; markClean([recId]) } else {
     if (!iDet.is_builtin && hasTrace(iDet.system ?? '')) throw new Error(`独立节点「${iDet.node_key}」仍存在缺少归属令牌的模组痕迹，已保留恢复记录`)
     if (!isCre) await fenceVer(iDet, `卸载模组「${record.pack.name}」收敛未决删除围栏`) }
    if (enrKey && ownsWal(enrKey, resId, cMutTok)) delete wals[enrKey]
    retToks(uKey, cMutTok, isCre); delete wals[uKey]; saveCkpt() } else { const cPatchTok = !recId ? getWalTok(curMut) : undefined
    if (cPatchTok) attTok = cPatchTok
    const rawPDetail = recId ? await fetchById(recId) : await fetchByKey(uKey)
    const exactPDetail = !recId && rawPDetail && rawPDetail.node_key !== uKey ? null : rawPDetail
    let pDet = exactPDetail
    if (cPatchTok) { if (inGraceWin(curMut)) { failNode([resId], [uKey], cPatchTok); errs.push(`节点「${uKey}」仍有未确认完成的超时写入，已保留恢复记录`); continue }
     const discovered = await discTok(safeId, cPatchTok)
     pDet = discovered ?? (exactPDetail && !exactPDetail.is_builtin && hasTrace(exactPDetail.system ?? '') ? exactPDetail : null) }
    if (!pDet) { if (inGraceWin(curMut) || (!recId && !cPatchTok)) { failNode([resId], recId ? [] : [uKey], attTok)
      errs.push(`节点「${uKey}」存在未确认完成或缺少稳定目标 ID 的记录，已保留恢复快照`); continue }
     if (attTok && !(await chkUniq(attTok, [], [uKey], [recId], recId, true))) continue
     if (recId) retireAbsent(uKey, recId, attTok); else retToks(uKey, cPatchTok, false)
     delete wals[uKey]; saveCkpt(); continue }
    resId = pDet.id; resKey = pDet.node_key
    const pLiveTok = !pDet.is_builtin ? origTok(pDet.system ?? '', safeId) : null
    if (!(await chkUniq(attTok, [pDet], [resKey, uKey], [resId, recId], resId)) || !(await chkUniq(pLiveTok, [pDet], [resKey, uKey], [resId, recId], resId))) continue
    if (failIds.has(resId) || failKeys.has(resKey) || failKeys.has(uKey) || (attTok && pinToks.has(attTok)) || (pLiveTok && pinToks.has(pLiveTok))) {
     failCls(attTok ?? pLiveTok ?? undefined, [pDet], [resKey, uKey], [resId, recId]); continue }
    const curSys = pDet.system ?? ''
    const slotOwnedTok = pDet.node_key === uKey ? oToks[uKey] : oToks[pDet.node_key]
    const mSlotOTok = !pDet.is_builtin && slotOwnedTok && hasCTok(curSys, safeId, slotOwnedTok) ? slotOwnedTok : undefined
    const expTok = cPatchTok ?? getWalTok(curMut) ?? (recId && kCustIds.has(resId) ? slotOwnedTok : mSlotOTok)
    attTok = expTok ?? (pLiveTok ?? undefined)
    if (expTok && !(await chkUniq(expTok, [pDet], [resKey, uKey], [resId, recId], resId))) continue
    const customCandidate = isCust(resId, pDet, curMut) || Boolean(cPatchTok) || (!pDet.is_builtin && Boolean(expTok) && !bkps[resKey] && !bkps[uKey])
    const bkp = !customCandidate ? (bkps[resKey] ?? bkps[uKey]) : undefined
    if (cleanIds.has(resId) && !bkp && !hasTrace(curSys)) { if (ownsWal(resKey, resId, expTok)) delete wals[resKey]
     retToks(uKey, expTok, false); delete wals[uKey]; saveCkpt(); continue }
    if (hasBlkWal(pDet, uKey, resKey)) { failNode([resId, recId], [resKey, ...(!recId ? [uKey] : [])], expTok)
     errs.push(`节点「${uKey}」仍有未确认完成的超时写入，已保留恢复记录`); continue }
    if (customCandidate) { enrId = pDet.id; enrKey = pDet.node_key
     if (expTok) { const pRes = await enrollClean(pDet, expTok, uKey, false, true)
      if (pRes === 'skipped') { if (!pDet.is_builtin && hasTrace(pDet.system ?? '')) throw new Error(`独立节点「${pDet.node_key}」仍存在缺少归属令牌的模组痕迹，已保留恢复记录`)
       if (!isPatchDone(pDet, curMut)) await fenceVer(pDet, `卸载模组「${record.pack.name}」收敛未决更新围栏`) }
     } else await cleanCustom(pDet, undefined, undefined, uKey, true)
     markClean([resId, recId]); actCIds.delete(resId)
     if (ownsWal(pDet.node_key, resId, expTok)) delete wals[pDet.node_key]
     retToks(uKey, expTok, false); delete wals[uKey]; saveCkpt() } else { if (hasForeignPatch(resKey, resId)) {
      failNode([resId, recId], [uKey, resKey])
      errs.push(`节点「${resKey}」所在键位仍存有其他节点的未决恢复记录，已延后清理以防覆盖`); continue }
     const provenAtU = pIds[uKey] === resId || bkps[uKey]?.targetNodeId === resId || isProvenPatch(pDet, curMut, Boolean(bkp))
     const idBoundElsewhereAtU = cleanIds.has(resId) || Object.entries(pIds).some(([k, id]) => k !== uKey && k !== resKey && id === resId) || Object.entries(bkps).some(([k, b]) => k !== uKey && k !== resKey && b.targetNodeId === resId)
     if ((!recId && (resKey !== uKey || idBoundElsewhereAtU || (bkp ? !hasRepBlk(curSys, safeId) : (!hasAnyModBlock(curSys, safeId) || hasRepBlk(curSys, safeId) || origTok(curSys, safeId) !== null)))) || (Boolean(recId) && !provenAtU)) {
      failNode([recId ? resId : null], [uKey])
      if (bkp || actPKeys.has(uKey)) actPKeys.add(uKey)
      errs.push(`节点「${uKey}」旧版未决记录缺少已核验的目标绑定或本模组标记，已保留恢复记录`); continue }
     if (resKey !== uKey) { const keepOld = actPKeys.has(uKey) && pIds[uKey] !== resId
      if (!migrateSlot(uKey, resId, resKey, false, keepOld)) { failNode([recId], []); continue } } else {
      actPKeys.add(resKey); if (recId) pIds[resKey] = resId
      saveCkpt() }
     await reconcilePatch(pDet, resKey)
     if (!failIds.has(resId) && !failKeys.has(resKey)) { markClean([resId, recId])
      if (!failKeys.has(uKey) && (resKey === uKey || provenAtU)) {
       if (pIds[uKey] === undefined || pIds[uKey] === resId) { actPKeys.delete(uKey); delete pIds[uKey] }
       if (!bkps[uKey]?.targetNodeId || bkps[uKey]?.targetNodeId === resId) delete bkps[uKey] }
      retToks(uKey, attTok, false); delete wals[uKey]; saveCkpt() } } } } catch (uErr) {
   if (is404(uErr) && (await idsGone([resId, enrId, recId])) && (await chkUniq(attTok, [], [...(!recId ? [uKey] : []), resKey, enrKey], [resId, enrId, recId], resId ?? enrId ?? recId, true))) {
    fin404([resId, enrId, recId], uKey, [enrKey, resKey], attTok)
    const hadProvenAtU = !isCust(resId ?? recId, null, curMut) && !attTok && (pIds[uKey] !== undefined ? [resId, recId].includes(pIds[uKey]) : Boolean(bkps[uKey]?.targetNodeId && [resId, recId].includes(bkps[uKey]?.targetNodeId ?? null)))
    if (!failKeys.has(uKey) && hadProvenAtU) { actPKeys.delete(uKey); delete pIds[uKey]; delete bkps[uKey] }
    if (resKey && hadProvenAtU) { actPKeys.delete(resKey); delete pIds[resKey]; delete bkps[resKey] }
    delete wals[uKey]; saveCkpt(); continue }
   failCls(attTok, dupDets(uErr), [...(!recId ? [uKey] : []), resKey, enrKey], [resId, enrId, recId])
   errs.push(fmtErr(uErr, `清理未决节点「${uKey}」失败`).message) } }
 for (const [ownedKey, ownedTok] of Object.entries({ ...oToks })) { if (oToks[ownedKey] === undefined) continue
  if (pinToks.has(ownedTok) || failKeys.has(ownedKey)) { failCls(ownedTok, [], [ownedKey]); continue }
  let oId: string | null = null, oKey: string | null = null
  try { if (Object.values(wals).some((um) => getWalTok(um) === ownedTok && inGraceWin(um))) {
    failNode([], [ownedKey], ownedTok); errs.push(`节点「${ownedKey}」仍有未确认完成的变更请求，已保留归属凭证`); continue }
   const rawOwned = await fetchByKey(ownedKey)
   const exactOwned = rawOwned?.node_key === ownedKey ? rawOwned : null
   const oDet = (await discTok(safeId, ownedTok)) ?? (exactOwned && !exactOwned.is_builtin && hasTrace(exactOwned.system ?? '') ? exactOwned : null)
   if (!oDet) { if (!(await chkUniq(ownedTok, [], [ownedKey], [], undefined, true))) continue
    retToks(ownedKey, ownedTok, false); saveCkpt(); continue }
   oId = oDet.id; oKey = oDet.node_key
   const oLiveTok = !oDet.is_builtin ? origTok(oDet.system ?? '', safeId) : null
   if (!(await chkUniq(ownedTok, [oDet], [ownedKey, oKey], [oId], oId)) || !(await chkUniq(oLiveTok, [oDet], [ownedKey, oKey], [oId], oId))) continue
   if (failIds.has(oId) || failKeys.has(oKey) || pinToks.has(ownedTok) || (oLiveTok !== null && pinToks.has(oLiveTok))) { failCls(ownedTok ?? oLiveTok ?? undefined, [oDet], [ownedKey, oKey], [oId]); continue }
   if (cleanIds.has(oId) && !hasTrace(oDet.system ?? '')) { retToks(ownedKey, ownedTok, false); saveCkpt(); continue }
   if (hasBlkWal(oDet, ownedKey, oKey)) { failNode([oId], [ownedKey, oKey], ownedTok); errs.push(`节点「${oKey}」仍有未确认完成的后台变更请求，请稍候重试`); continue }
   await enrollClean(oDet, ownedTok, ownedKey, false, true)
   retToks(ownedKey, ownedTok, false); saveCkpt() } catch (oErr) { if (is404(oErr) && oId && (await idsGone([oId])) && (await chkUniq(ownedTok, [], [ownedKey, oKey], [oId], oId, true))) {
    fin404([oId], ownedKey, [oKey], ownedTok); saveCkpt(); continue }
   failCls(ownedTok, dupDets(oErr), [ownedKey, oKey], [oId])
   errs.push(fmtErr(oErr, `对账清理归属节点「${ownedKey}」失败`).message) } }
 if (errs.length === 0 && (actCIds.size > 0 || actPKeys.size > 0 || Object.keys(pIds).length > 0 || Object.keys(bkps).length > 0 || Object.keys(wals).length > 0 || Object.keys(oToks).length > 0 || Object.keys(pToks).length > 0 || failIds.size > 0 || failKeys.size > 0)) {
  errs.push('模组仍存在未收敛的恢复记录，已保留检查点供安全重试') }
 if (errs.length > 0) { saveCkpt()
  throw new Error(`卸载模组「${record.pack.name}」部分未完成，已保留剩余恢复信息供重试：${errs.join('；')}`) }
 bridge.commitPackRecord(safeId, undefined) }
