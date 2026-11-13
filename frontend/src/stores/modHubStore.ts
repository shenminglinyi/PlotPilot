import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { promptPlazaApi, type PromptNode, type PromptNodeDetail } from '@/api/llmControl'
import { sendSquareEvent } from '@/api/cloudSquare'
import { storageKeys } from '@/config/storageKeys'
import { CURATED_MOD_PACKS } from '@/domain/modPack/curatedPacks'
import { convertCommunityAssetToPack, convertOfficialAssetToPack, createManifestFromPack, hydrateCloudPackDetail } from '@/domain/modPack/cloudPackAdapter'
import { MOD_MANIFEST_MAX_BYTES, assertValidModId, assertValidNodeKey, assertSafeProtocolBody, buildModEndMarker, buildModStartMarker, buildOwnedCustomBlock, extractCustomOriginToken, fetchTrustedBrowserFallbackJson, generateOriginToken, hasAnyModBlock, hasMatchingCustomOriginToken, hasPackModMention, hasReplacedModBlock, injectModProtocolBlock, parseAnyModJson, prepareOwnedCustomSystemUpdate, prepareSystemReplacement, resolveRemoteCandidateUrls, restoreReplacedModBlock, sanitizeModIdAtom, stripModDelimiterComments, stripModProtocolBlock, stripOwnedCustomBlock, validatePackInvariants, type ModBlockMode } from '@/domain/modPack/modProtocol'
import { executeModPackUninstall } from '@/domain/modPack/modUninstallEngine'
import { AMBIGUOUS_MUTATION_GRACE_MS, buildDeleteNodePreconditionConfig, buildOwnedCustomUpdatePreconditions, buildSystemUpdatePreconditions, discoverCustomNodeByOriginToken, fenceNodeVersion, fetchExistingNodeOrNull, fetchNodeByVerifiedId, findForeignDependentPackNames as findForeignDepsInMap, formatBackendError, hasForeignContentLayers, hasPatchMutationCommitted, isDefinitivePreCommitHttpError, isHttpNotFound, isMissingLegacyRemoteEndpoint, isWithinAmbiguityWindow, readStoredRecords, readStoredRecordsStrict, withNodeLocks, writeStoredPackRecordStrict, writeStoredRecordsStrict } from '@/domain/modPack/modWalCommon'
import type { InstalledModRecord, ModNodeOverride, NarrativeModPack, ReplacedNodeBackup, UnresolvedNodeMutation } from '@/domain/modPack/types'
export { AMBIGUOUS_MUTATION_GRACE_MS, MOD_MANIFEST_MAX_BYTES, assertValidModId, assertValidNodeKey, assertSafeProtocolBody, buildModEndMarker, buildModStartMarker, buildOwnedCustomBlock, extractCustomOriginToken, generateOriginToken, hasAnyModBlock, hasMatchingCustomOriginToken, hasPackModMention, hasReplacedModBlock, injectModProtocolBlock, parseAnyModJson, prepareOwnedCustomSystemUpdate, prepareSystemReplacement, resolveRemoteCandidateUrls, restoreReplacedModBlock, sanitizeModIdAtom, stripModDelimiterComments, stripModProtocolBlock, stripOwnedCustomBlock, type ModBlockMode }
type InFlightOrAppliedStep =
 | { kind: 'create_custom'; nodeKey: string; originToken: string; writtenSystem: string; initialUserTemplate: string; completed: boolean; createdId?: string; dispatchError?: unknown }
 | { kind: 'updated_owned_custom'; nodeId: string; nodeKey: string; originToken: string; priorName: string; priorDescription: string; priorSystem: string; priorUserTemplate: string; writtenName: string; writtenDescription: string; writtenSystem: string; updatedUserTemplate?: string; hadPriorOwnedTpl?: string; completed: boolean; dispatchError?: unknown }
 | { kind: 'patched_existing'; targetNodeId: string; nodeKey: string; priorSystem: string; writtenSystem: string; hadPriorBackup?: ReplacedNodeBackup; hadPriorPatchedId?: string; completed: boolean; dispatchError?: unknown }
type ValidatedOverridePlan = | { kind: 'create_new_custom' }
 | { kind: 'update_owned_custom'; detail: PromptNodeDetail; customPlan: { nextSystem: string; verifiedToken: string }; inheritedOwnedTpl?: string }
 | { kind: 'patch_builtin_standalone' | 'append_existing'; detail: PromptNodeDetail; nextSystem: string; priorOwnedBackup?: ReplacedNodeBackup }
 | { kind: 'replace_existing'; detail: PromptNodeDetail; repPlan: { baselineSystem: string; nextSystem: string } }
interface InstallStoreCtx { reloadAuthoritativeMap: () => Record<string, InstalledModRecord>
 commitPackRecord: (packId: string, record: InstalledModRecord | undefined) => Record<string, InstalledModRecord>
 getInstalledMap: () => Record<string, InstalledModRecord>
 findForeignDependentPackNames: (targetNodeKey: string, excludePackId: string, targetNodeId?: string) => string[] }
async function runInstallLocked(resolvedPack: NarrativeModPack, ctx: InstallStoreCtx): Promise<InstalledModRecord> {
 const { reloadAuthoritativeMap, commitPackRecord, getInstalledMap, findForeignDependentPackNames } = ctx
 const initialRecord = reloadAuthoritativeMap()[resolvedPack.id]
 const ownedCreatedIdSet = new Set<string>(initialRecord?.createdNodeIds ?? []), workingCreatedIds = new Set<string>(ownedCreatedIdSet)
 const canonSlotByTok = new Map<string, string>()
 const recOwnedToks: Record<string, string> = { ...(initialRecord?.ownedCustomTokens ?? {}) }
 const recOwnedTpls: Record<string, string> = { ...(initialRecord?.ownedCustomUserTemplates ?? {}) }
 const recPendToks: Record<string, string> = { ...(initialRecord?.pendingCreateTokens ?? {}) }
 const recPendTpls: Record<string, string> = { ...(initialRecord?.pendingCreateTemplates ?? {}) }
 const recUnresolved: Record<string, UnresolvedNodeMutation> = { ...(initialRecord?.unresolvedMutations ?? {}) }
 const recPatchedIds: Record<string, string> = { ...(initialRecord?.patchedNodeIds ?? {}) }
 const initialBackups: Record<string, ReplacedNodeBackup> = { ...(initialRecord?.replacedSystemBackups ?? {}) }
 for (const [bk, bv] of Object.entries(initialBackups)) { if (bv.targetNodeId && !ownedCreatedIdSet.has(bv.targetNodeId) && !recPatchedIds[bk]) recPatchedIds[bk] = bv.targetNodeId }
 let hadReconcilableEntries = Object.keys(recUnresolved).length > 0 || Object.keys(recPendToks).length > 0 || Object.keys(recPendTpls).length > 0
 const lookupTplForToken = (tokMap: Record<string, string>, tplMap: Record<string, string>, tok: string | undefined, preferredKey?: string): { foundSlot: boolean; tpl: string | undefined } => {
  if (!tok) return { foundSlot: false, tpl: undefined }
  if (preferredKey && tokMap[preferredKey] === tok) return { foundSlot: true, tpl: tplMap[preferredKey] }
  for (const [k, v] of Object.entries(tokMap)) if (v === tok) return { foundSlot: true, tpl: tplMap[k] }
  return { foundSlot: false, tpl: undefined } }
 const syncTokenBaselineOnMap = (tokMap: Record<string, string>, tplMap: Record<string, string>, canonicalKey: string, tok: string, tpl: string | undefined, pruneAliases = false, keepSlots?: Record<string, unknown>): void => {
  tokMap[canonicalKey] = tok
  if (tpl !== undefined) tplMap[canonicalKey] = tpl; else delete tplMap[canonicalKey]
  for (const [k, v] of Object.entries({ ...tokMap })) { if (k === canonicalKey || v !== tok) continue
   if (pruneAliases && !keepSlots?.[k]) { delete tokMap[k]; delete tplMap[k] } else if (tpl !== undefined) tplMap[k] = tpl; else delete tplMap[k] } }
 const extractWalCustomToken = (um: UnresolvedNodeMutation | undefined): string | undefined =>
  um ? (um.originToken ?? extractCustomOriginToken(um.priorSystem ?? '', resolvedPack.id) ?? extractCustomOriginToken(um.writtenSystem ?? '', resolvedPack.id) ?? undefined) : undefined
 const baseKeyOfPendingSlot = (k: string): string => { const i = k.indexOf('#pending:'); return i >= 0 ? k.slice(0, i) : k }
 const delPendingByTok = (tokMap: Record<string, string>, tplMap: Record<string, string>, tok: string | undefined): void => { if (!tok) return
  for (const [k, v] of Object.entries({ ...tokMap })) if (v === tok) { delete tokMap[k]; delete tplMap[k] } }
 const archivePendingCred = (tokMap: Record<string, string>, tplMap: Record<string, string>, slotKey: string, tok: string, explicitTpl?: string): void => {
  const resolvedTpl = explicitTpl !== undefined ? explicitTpl : lookupTplForToken(tokMap, tplMap, tok, slotKey).tpl
  delPendingByTok(tokMap, tplMap, tok)
  const archiveKey = `${baseKeyOfPendingSlot(slotKey)}#pending:${tok}`
  tokMap[archiveKey] = tok
  if (resolvedTpl !== undefined) tplMap[archiveKey] = resolvedTpl; else delete tplMap[archiveKey] }
 const preflightCache = new Map<string, PromptNodeDetail | null>()
 const getPreflightDetail = async (key: string): Promise<PromptNodeDetail | null> => { if (preflightCache.has(key)) return preflightCache.get(key) ?? null
  const d = await fetchExistingNodeOrNull(key)
  const exact = d?.node_key === key ? d : null
  preflightCache.set(key, exact)
  return exact }
 const relocateDisplacedToken = async (tokMap: Record<string, string>, tplMap: Record<string, string>, slotKey: string, incomingTok: string,
  unresolvedMap: Record<string, UnresolvedNodeMutation>, visited = new Set<string>(), ): Promise<void> => { const displacedTok = tokMap[slotKey]
  if (!displacedTok || displacedTok === incomingTok) return
  if (visited.has(slotKey)) throw new Error(`节点键「${slotKey}」存在循环重命名的自建归属凭证，请先在已安装列表中执行对齐`)
  const nextVisited = new Set(visited); nextVisited.add(slotKey)
  const displacedTpl = lookupTplForToken(tokMap, tplMap, displacedTok, slotKey).tpl
  const candidateIds = new Set<string>([...ownedCreatedIdSet, ...workingCreatedIds])
  for (const um of Object.values(unresolvedMap)) if (um.targetNodeId) candidateIds.add(um.targetNodeId)
  const matchedCands: PromptNodeDetail[] = []
  for (const cid of candidateIds) { const cLive = await fetchNodeByVerifiedId(cid)
   if (cLive && !cLive.is_builtin && hasMatchingCustomOriginToken(cLive.system ?? '', resolvedPack.id, displacedTok)) matchedCands.push(cLive) }
  if (matchedCands.length > 1) throw new Error('检测到多个自定义节点携带同一归属令牌，已中止覆盖以保护恢复记录')
  let matchedLive: PromptNodeDetail | null = matchedCands[0] ?? null
  if (!matchedLive) { matchedLive = await discoverCustomNodeByOriginToken(resolvedPack.id, displacedTok)
   if (matchedLive) { preflightCache.set(matchedLive.node_key, matchedLive); ownedCreatedIdSet.add(matchedLive.id); workingCreatedIds.add(matchedLive.id) } }
  if (matchedLive) { if (matchedLive.node_key === slotKey) throw new Error(`节点键「${slotKey}」仍被归属令牌匹配的独立节点占用，已中止覆盖`)
   await relocateDisplacedToken(tokMap, tplMap, matchedLive.node_key, displacedTok, unresolvedMap, nextVisited)
   const liveTpl = tokMap[matchedLive.node_key] === displacedTok ? tplMap[matchedLive.node_key] : displacedTpl
   syncTokenBaselineOnMap(tokMap, tplMap, matchedLive.node_key, displacedTok, liveTpl, true, unresolvedMap)
   if (tokMap[slotKey] === displacedTok && extractWalCustomToken(unresolvedMap[slotKey]) !== displacedTok) { delete tokMap[slotKey]; delete tplMap[slotKey] }
   if (canonSlotByTok.get(displacedTok) === slotKey) canonSlotByTok.set(displacedTok, matchedLive.node_key)
   if (tokMap === recOwnedToks) hadReconcilableEntries = true
   return }
  if (Object.values(unresolvedMap).some(um => extractWalCustomToken(um) === displacedTok && isWithinAmbiguityWindow(um))) { throw new Error(`节点键「${slotKey}」仍有原自建节点未决变更，请稍候重试`) }
  delete tokMap[slotKey]; delete tplMap[slotKey]
  if (tokMap === recOwnedToks) hadReconcilableEntries = true }
 const promoteDiscoveredCustom = async (live: PromptNodeDetail, tok: string, resolvedTpl: string | undefined, ownedTokMap: Record<string, string>, ownedTplMap: Record<string, string>,
  pendingTokMap: Record<string, string>, pendingTplMap: Record<string, string>, unresolvedMap: Record<string, UnresolvedNodeMutation>, legacySlotKey?: string, ): Promise<void> => {
  ownedCreatedIdSet.add(live.id); workingCreatedIds.add(live.id)
  await relocateDisplacedToken(ownedTokMap, ownedTplMap, live.node_key, tok, unresolvedMap)
  syncTokenBaselineOnMap(ownedTokMap, ownedTplMap, live.node_key, tok, resolvedTpl, true, unresolvedMap)
  delPendingByTok(pendingTokMap, pendingTplMap, tok)
  if (legacySlotKey && !pendingTokMap[legacySlotKey]) delete pendingTplMap[legacySlotKey] }
 for (const [uKey, uMut] of Object.entries({ ...recUnresolved })) { const uMutTok = extractWalCustomToken(uMut)
  if (uMut.kind === 'create') { const baseUKey = baseKeyOfPendingSlot(uKey)
   let uLive: PromptNodeDetail | null = null
   if (uMut.targetNodeId) uLive = await fetchNodeByVerifiedId(uMut.targetNodeId)
   else if (uMutTok) { uLive = await discoverCustomNodeByOriginToken(resolvedPack.id, uMutTok); if (uLive) preflightCache.set(uLive.node_key, uLive) }
   else if (baseUKey) uLive = await getPreflightDetail(baseUKey)
   const fallbackSlotTpl = !recPendToks[uKey] ? recPendTpls[uKey] : undefined
   const pendingMatchedTpl = lookupTplForToken(recPendToks, recPendTpls, uMutTok, uKey).tpl ?? fallbackSlotTpl
   if (uLive && !uLive.is_builtin && uMutTok && hasMatchingCustomOriginToken(uLive.system ?? '', resolvedPack.id, uMutTok)) {
    const recTpl = uMut.initialUserTemplate ?? pendingMatchedTpl ?? lookupTplForToken(recOwnedToks, recOwnedTpls, uMutTok, uLive.node_key).tpl
    await promoteDiscoveredCustom(uLive, uMutTok, recTpl, recOwnedToks, recOwnedTpls, recPendToks, recPendTpls, recUnresolved, uKey)
    delete recUnresolved[uKey] } else if (isWithinAmbiguityWindow(uMut)) { throw new Error(`节点「${baseUKey}」存在上次超时未确认结果的创建操作，为防止状态竞争已暂缓本次安装，请稍候数秒重试`) } else if (uMut.targetNodeId) {
    if (!uLive) ownedCreatedIdSet.delete(uMut.targetNodeId)
    else if (!uLive.is_builtin && (hasAnyModBlock(uLive.system ?? '', resolvedPack.id) || hasPackModMention(uLive.system ?? '', resolvedPack.id))) ownedCreatedIdSet.add(uLive.id)
    delPendingByTok(recPendToks, recPendTpls, uMutTok)
    if (!recPendToks[uKey]) delete recPendTpls[uKey]; delete recUnresolved[uKey] } else {
    if (uMutTok) archivePendingCred(recPendToks, recPendTpls, baseUKey, uMutTok, uMut.initialUserTemplate ?? pendingMatchedTpl)
    if (!recPendToks[uKey]) delete recPendTpls[uKey]; delete recUnresolved[uKey] } } else if (uMut.kind === 'delete') {
   let byIdLive: PromptNodeDetail | null = null
   if (uMut.targetNodeId) byIdLive = await fetchNodeByVerifiedId(uMut.targetNodeId)
   else if (uMutTok) { if (isWithinAmbiguityWindow(uMut)) throw new Error(`节点「${uKey}」存在上次超时未确认结果的回滚删除操作，已暂缓本次安装，请稍候数秒重试`)
    byIdLive = await discoverCustomNodeByOriginToken(resolvedPack.id, uMutTok); if (byIdLive) preflightCache.set(byIdLive.node_key, byIdLive) }
   else byIdLive = await getPreflightDetail(uKey)
   if (!byIdLive) { if (!uMut.targetNodeId && isWithinAmbiguityWindow(uMut)) throw new Error(`节点「${uKey}」存在上次超时未确认结果的回滚删除操作，已暂缓本次安装，请稍候数秒重试`)
    if (!uMut.targetNodeId && !uMutTok) throw new Error(`节点「${uKey}」存在缺少稳定目标 ID 与归属令牌的未决删除且原键位未找到节点，请先在已安装列表中对齐或清理`)
    if (uMut.targetNodeId) ownedCreatedIdSet.delete(uMut.targetNodeId)
    delete recUnresolved[uKey]
    if (uMutTok) {
     for (const [k, v] of Object.entries({ ...recOwnedToks })) if (v === uMutTok && !recUnresolved[k]) { delete recOwnedToks[k]; delete recOwnedTpls[k] }
     delPendingByTok(recPendToks, recPendTpls, uMutTok)
    } else if (!uMut.targetNodeId) await relocateDisplacedToken(recOwnedToks, recOwnedTpls, uKey, '', recUnresolved)
    if (!recPendToks[uKey]) delete recPendTpls[uKey] } else if (isWithinAmbiguityWindow(uMut)) { throw new Error(`节点「${uKey}」存在上次超时未确认结果的回滚删除操作，已暂缓本次安装，请稍候数秒重试`)
   } else { try { byIdLive = await fenceNodeVersion(byIdLive, `收敛模组「${resolvedPack.name}」超时未决删除围栏`)
     preflightCache.set(byIdLive.node_key, byIdLive) } catch (fenceErr) { if (isHttpNotFound(fenceErr) && !(await fetchNodeByVerifiedId(byIdLive.id))) {
      if (uMut.targetNodeId) ownedCreatedIdSet.delete(uMut.targetNodeId)
      ownedCreatedIdSet.delete(byIdLive.id); delete recUnresolved[uKey]
      if (uMutTok) {
       for (const [k, v] of Object.entries({ ...recOwnedToks })) if (v === uMutTok && !recUnresolved[k]) { delete recOwnedToks[k]; delete recOwnedTpls[k] }
       delPendingByTok(recPendToks, recPendTpls, uMutTok) }
      if (!recPendToks[uKey]) delete recPendTpls[uKey]; continue }
     throw formatBackendError(fenceErr, `收敛节点「${byIdLive.node_key}」未决删除围栏失败`) }
    if (uMutTok && !byIdLive.is_builtin && hasMatchingCustomOriginToken(byIdLive.system ?? '', resolvedPack.id, uMutTok)) { ownedCreatedIdSet.add(byIdLive.id)
     const recoveredTpl = uMut.initialUserTemplate !== undefined ? uMut.initialUserTemplate : lookupTplForToken(recOwnedToks, recOwnedTpls, uMutTok, byIdLive.node_key).tpl
     await relocateDisplacedToken(recOwnedToks, recOwnedTpls, byIdLive.node_key, uMutTok, recUnresolved)
     syncTokenBaselineOnMap(recOwnedToks, recOwnedTpls, byIdLive.node_key, uMutTok, recoveredTpl, true, recUnresolved) }
    delete recUnresolved[uKey] } } else { const knownPatchTargetId = uMut.targetNodeId ?? (!uMutTok ? (recPatchedIds[uKey] ?? initialBackups[uKey]?.targetNodeId) : undefined)
   const customPatchTok = !knownPatchTargetId ? uMutTok : undefined
   let uLive: PromptNodeDetail | null = null
   if (knownPatchTargetId) uLive = await fetchNodeByVerifiedId(knownPatchTargetId)
   else if (customPatchTok) { uLive = await discoverCustomNodeByOriginToken(resolvedPack.id, customPatchTok) ?? (!isWithinAmbiguityWindow(uMut) ? await getPreflightDetail(uKey) : null)
    if (uLive) preflightCache.set(uLive.node_key, uLive) }
   else uLive = await getPreflightDetail(uKey)
   const uLiveSys = uLive?.system ?? ''
   const verifiedCustomTok = uLive && !uLive.is_builtin
    ? (uMutTok && hasMatchingCustomOriginToken(uLiveSys, resolvedPack.id, uMutTok) ? uMutTok : Object.values(recOwnedToks).find(t => Boolean(t) && hasMatchingCustomOriginToken(uLiveSys, resolvedPack.id, t)))
    : undefined
   if (uLive && hasPatchMutationCommitted(uLive, uMut)) { const targetTemplateKey = uLive.node_key
    if (verifiedCustomTok) ownedCreatedIdSet.add(uLive.id)
    const hasOwnedCustomBinding = Boolean(uLive.id && ownedCreatedIdSet.has(uLive.id)) || Boolean(verifiedCustomTok)
    const applyReconciledTpl = async (nextTpl: string | undefined, clearLegacyKey = false) => { if (verifiedCustomTok) {
      await relocateDisplacedToken(recOwnedToks, recOwnedTpls, targetTemplateKey, verifiedCustomTok, recUnresolved)
      syncTokenBaselineOnMap(recOwnedToks, recOwnedTpls, targetTemplateKey, verifiedCustomTok, nextTpl, true, recUnresolved) } else if (nextTpl === undefined) {
      if (clearLegacyKey && !recOwnedToks[uKey]) delete recOwnedTpls[uKey]
      if (!recOwnedToks[targetTemplateKey]) delete recOwnedTpls[targetTemplateKey] } }
    if (uMut.targetOwnedUserTemplate === null) await applyReconciledTpl(undefined, true)
    else if (uMut.targetOwnedUserTemplate !== undefined) await applyReconciledTpl(uMut.targetOwnedUserTemplate)
    else if (uMut.writtenUserTemplate !== undefined && hasOwnedCustomBinding) await applyReconciledTpl(uMut.writtenUserTemplate)
    delete recUnresolved[uKey] } else if (isWithinAmbiguityWindow(uMut)) { throw new Error(`节点「${uKey}」存在上次超时未确认结果的更新操作，为保护原始基线快照已暂缓本次安装，请稍候数秒重试`) } else { if (uLive) { try {
      uLive = await fenceNodeVersion(uLive, `收敛模组「${resolvedPack.name}」超时未决更新围栏`)
      preflightCache.set(uLive.node_key, uLive) } catch (fenceErr) { if (isHttpNotFound(fenceErr) && !(await fetchNodeByVerifiedId(uLive.id))) uLive = null
      else throw formatBackendError(fenceErr, `收敛节点「${uLive.node_key}」未决更新围栏失败`) } } else if (!knownPatchTargetId && !customPatchTok) {
     throw new Error(`节点「${uKey}」存在缺少稳定目标 ID 的未决更新且原键位未找到节点，无法建立版本围栏，请先在已安装列表中对齐或清理`) }
    if (uLive && verifiedCustomTok) { ownedCreatedIdSet.add(uLive.id)
     const existingTpl = lookupTplForToken(recOwnedToks, recOwnedTpls, verifiedCustomTok, uLive.node_key)
     const fallbackTpl = uMut.initialUserTemplate !== undefined ? uMut.initialUserTemplate : (uMut.priorUserTemplate !== undefined ? undefined : existingTpl.tpl)
     await relocateDisplacedToken(recOwnedToks, recOwnedTpls, uLive.node_key, verifiedCustomTok, recUnresolved)
     syncTokenBaselineOnMap(recOwnedToks, recOwnedTpls, uLive.node_key, verifiedCustomTok, fallbackTpl, true, recUnresolved) }
    delete recUnresolved[uKey] } } }
 for (const [pKey, pToken] of Object.entries({ ...recPendToks })) { if (!pToken) { delete recPendToks[pKey]; delete recPendTpls[pKey]; continue }
  const baseKey = baseKeyOfPendingSlot(pKey)
  const pLive = await discoverCustomNodeByOriginToken(resolvedPack.id, pToken)
  if (pLive) preflightCache.set(pLive.node_key, pLive)
  const pendingTpl = lookupTplForToken(recPendToks, recPendTpls, pToken, pKey).tpl
  if (pLive && !pLive.is_builtin && hasMatchingCustomOriginToken(pLive.system ?? '', resolvedPack.id, pToken)) {
   const recTpl = pendingTpl !== undefined ? pendingTpl : lookupTplForToken(recOwnedToks, recOwnedTpls, pToken, pLive.node_key).tpl
   await promoteDiscoveredCustom(pLive, pToken, recTpl, recOwnedToks, recOwnedTpls, recPendToks, recPendTpls, recUnresolved, pKey)
  } else archivePendingCred(recPendToks, recPendTpls, baseKey, pToken, pendingTpl) }
 for (const leftoverTplKey of Object.keys({ ...recPendTpls })) { if (!recPendToks[leftoverTplKey]) delete recPendTpls[leftoverTplKey] }
 workingCreatedIds.clear()
 for (const cid of ownedCreatedIdSet) workingCreatedIds.add(cid)
 const recPatchedKeys = new Set<string>([...(initialRecord?.patchedNodeKeys ?? []), ...Object.keys(recPatchedIds), ...Object.keys(initialBackups)])
 const hasRetainedBaselineState = ownedCreatedIdSet.size > 0 || Object.keys(recOwnedToks).length > 0 ||
  Object.keys(recPendToks).length > 0 || Object.keys(recUnresolved).length > 0 ||
  recPatchedKeys.size > 0 || (initialRecord !== undefined && initialRecord.pack.overrides.length === 0)
 const copyIfNonEmpty = <T>(m: Record<string, T>): Record<string, T> | undefined => Object.keys(m).length ? { ...m } : undefined
 const recBaselineRec: InstalledModRecord | undefined = hasRetainedBaselineState ? {
  pack: initialRecord?.pack ?? resolvedPack, installedAt: initialRecord?.installedAt ?? new Date().toISOString(),
  createdNodeIds: Array.from(ownedCreatedIdSet), ownedCustomTokens: copyIfNonEmpty(recOwnedToks),
  ownedCustomUserTemplates: copyIfNonEmpty(recOwnedTpls), pendingCreateTokens: copyIfNonEmpty(recPendToks),
  pendingCreateTemplates: copyIfNonEmpty(recPendTpls), patchedNodeKeys: Array.from(recPatchedKeys),
  patchedNodeIds: copyIfNonEmpty(recPatchedIds), replacedSystemBackups: copyIfNonEmpty(initialBackups), unresolvedMutations: copyIfNonEmpty(recUnresolved), } : undefined
 if (hadReconcilableEntries) commitPackRecord(resolvedPack.id, recBaselineRec)
 const isIdBoundElsewhere = (nodeKey: string, detailId: string): boolean => ownedCreatedIdSet.has(detailId) ||
  Object.entries(recPatchedIds).some(([k, id]) => k !== nodeKey && id === detailId) ||
  Object.entries(initialBackups).some(([k, b]) => k !== nodeKey && b.targetNodeId === detailId)
 const resolveVerifiedPriorBackup = (nodeKey: string, detailId: string, detailSys: string): ReplacedNodeBackup | undefined => {
  const slotPatchedId = recPatchedIds[nodeKey], slotBackup = initialBackups[nodeKey]
  const legacyBkpUnbound = !slotPatchedId && Boolean(slotBackup && !slotBackup.targetNodeId) && (isIdBoundElsewhere(nodeKey, detailId) || !hasReplacedModBlock(detailSys, resolvedPack.id))
  const legacyPatchUnbound = !slotPatchedId && !slotBackup && recPatchedKeys.has(nodeKey) &&
   (isIdBoundElsewhere(nodeKey, detailId) || !hasAnyModBlock(detailSys, resolvedPack.id) || hasReplacedModBlock(detailSys, resolvedPack.id) || extractCustomOriginToken(detailSys, resolvedPack.id) !== null)
  if ((slotPatchedId && slotPatchedId !== detailId) || (slotBackup?.targetNodeId && slotBackup.targetNodeId !== detailId) || legacyBkpUnbound || legacyPatchUnbound) {
   throw new Error(`节点键「${nodeKey}」仍关联已重命名原目标节点的恢复基线，请先在已安装列表中还原或对齐后再覆盖该键位`) }
  return slotBackup ?? Object.values(initialBackups).find(b => b.targetNodeId === detailId) }
 const assertNoDisplacedPatchedBaselineAtKey = (nodeKey: string, customDetailId?: string) => { const slotPatchedId = recPatchedIds[nodeKey], slotBackup = initialBackups[nodeKey]
  if ((slotPatchedId !== undefined && slotPatchedId !== customDetailId) || (slotBackup !== undefined && (customDetailId === undefined || slotBackup.targetNodeId !== customDetailId)) || (slotPatchedId === undefined && slotBackup === undefined && initialRecord?.patchedNodeKeys.includes(nodeKey))) {
   throw new Error(`节点键「${nodeKey}」仍关联已重命名原目标节点的恢复基线，请先在已安装列表中还原或对齐后再覆盖该键位`) } }
 const validateAndPlanOverride = (override: ModNodeOverride, detail: PromptNodeDetail | null, ownedTokensMap: Record<string, string>, ownedTemplatesMap: Record<string, string>,
 ): ValidatedOverridePlan => { for (const [otherId, otherRec] of Object.entries(getInstalledMap())) { if (otherId === resolvedPack.id) continue
   const foreignUnresolved = otherRec.unresolvedMutations?.[override.nodeKey] ?? (detail ? Object.values(otherRec.unresolvedMutations ?? {}).find(u => u.targetNodeId === detail.id) : undefined)
   const foreignUnsettled = foreignUnresolved && (!detail ? (foreignUnresolved.kind === 'create' || isWithinAmbiguityWindow(foreignUnresolved)) : (foreignUnresolved.kind !== 'patch' || !hasPatchMutationCommitted(detail, foreignUnresolved)))
   if (foreignUnsettled) throw new Error(`目标节点「${override.nodeKey}」存在模组「${otherRec.pack.name}」未确认完成的后台变更，请稍候数秒或先恢复该模组`) }
  const assertNoForeignReplacementTakeover = (detailId: string, prefix: string) => { for (const [otherId, otherRec] of Object.entries(getInstalledMap())) {
    if (otherId === resolvedPack.id) continue
    if (otherRec.replacedSystemBackups?.[override.nodeKey] || Object.values(otherRec.replacedSystemBackups ?? {}).some(b => b.targetNodeId === detailId)) {
     throw new Error(`${prefix}「${override.nodeKey}」当前已被模组「${otherRec.pack.name}」完整接管，请先停用该模组`) } } }
  const buildAppendPlan = (kind: 'patch_builtin_standalone' | 'append_existing', target: PromptNodeDetail): ValidatedOverridePlan => {
   const priorOwnedBackup = resolveVerifiedPriorBackup(override.nodeKey, target.id, target.system ?? '')
   const baseForAppend = priorOwnedBackup ? restoreReplacedModBlock(target.system ?? '', resolvedPack.id, priorOwnedBackup.baselineSystem) : (target.system ?? '')
   return { kind, detail: target, nextSystem: injectModProtocolBlock(baseForAppend, resolvedPack.id, override.systemContent), priorOwnedBackup } }
  if (override.mode === 'standalone_node') { if (!detail) { assertNoDisplacedPatchedBaselineAtKey(override.nodeKey); return { kind: 'create_new_custom' } }
   if (!detail.is_builtin) { if (!ownedCreatedIdSet.has(detail.id)) throw new Error(`节点键「${override.nodeKey}」已被现有自定义节点占用，为防止覆盖或误删非本模组创建的节点，已取消安装`)
    assertNoDisplacedPatchedBaselineAtKey(override.nodeKey, detail.id)
    assertNoForeignReplacementTakeover(detail.id, '自定义节点')
    const candidateKeys = [detail.node_key, override.nodeKey, ...Object.keys(ownedTokensMap), ...Object.keys(recOwnedToks)]
    let matchedTok: string | undefined, matchedTpl: string | undefined, hasMatchedSlot = false
    for (const k of candidateKeys) { const inWorking = Object.prototype.hasOwnProperty.call(ownedTokensMap, k)
     const tok = inWorking ? ownedTokensMap[k] : recOwnedToks[k]
     if (tok && hasMatchingCustomOriginToken(detail.system ?? '', resolvedPack.id, tok)) {
      matchedTok = tok; matchedTpl = inWorking ? ownedTemplatesMap[k] : recOwnedTpls[k]; hasMatchedSlot = true; break } }
    const slotInWorking = Object.prototype.hasOwnProperty.call(ownedTokensMap, override.nodeKey)
    const expectedTok = matchedTok ?? (slotInWorking ? ownedTokensMap[override.nodeKey] : recOwnedToks[override.nodeKey])
    const inheritedOwnedTpl = hasMatchedSlot ? matchedTpl : expectedTok ? (slotInWorking ? ownedTemplatesMap[override.nodeKey] : recOwnedTpls[override.nodeKey]) : undefined
    const customPlan = prepareOwnedCustomSystemUpdate(detail.system ?? '', resolvedPack.id, override.systemContent, expectedTok)
    if (override.userTemplate !== undefined) { const currentTpl = detail.user_template ?? ''
     if (currentTpl !== override.userTemplate && (inheritedOwnedTpl === undefined || currentTpl !== inheritedOwnedTpl)) {
      throw new Error(`独立节点「${override.nodeKey}」的 User 模板包含手动编辑内容，为防止覆盖丢失您的修改已中止更新`) } }
    return { kind: 'update_owned_custom', detail, customPlan, inheritedOwnedTpl } }
   return buildAppendPlan('patch_builtin_standalone', detail) }
  if (!detail) throw new Error(`目标节点「${override.nodeKey}」在本地引擎中不存在，无法执行 ${override.mode} 挂载`)
  if (!detail.is_builtin && ownedCreatedIdSet.has(detail.id)) throw new Error(`节点「${override.nodeKey}」是由本模组创建的独立自定义节点，升级时请保持 standalone_node 模式`)
  if (override.mode === 'replace_system') { assertNoForeignReplacementTakeover(detail.id, '节点')
   const priorOwnedBackup = resolveVerifiedPriorBackup(override.nodeKey, detail.id, detail.system ?? '')
   const repPlan = prepareSystemReplacement(detail.system ?? '', resolvedPack.id, override.systemContent, priorOwnedBackup?.baselineSystem)
   return { kind: 'replace_existing', detail, repPlan } }
  return buildAppendPlan('append_existing', detail) }
 const preflightReplacements = new Map<string, { baselineSystem: string; nextSystem: string; targetNodeId: string }>()
 for (const override of resolvedPack.overrides) { const detail = await getPreflightDetail(override.nodeKey)
  const plan = validateAndPlanOverride(override, detail, recOwnedToks, recOwnedTpls)
  if (plan.kind === 'replace_existing') { preflightReplacements.set(override.nodeKey, { ...plan.repPlan, targetNodeId: plan.detail.id }) } }
 workingCreatedIds.clear()
 for (const cid of ownedCreatedIdSet) workingCreatedIds.add(cid)
 const wrkOwnedToks: Record<string, string> = { ...recOwnedToks }
 const wrkOwnedTpls: Record<string, string> = { ...recOwnedTpls }
 const wrkPendToks: Record<string, string> = { ...recPendToks }
 const wrkPendTpls: Record<string, string> = { ...recPendTpls }
 const wrkUnresolved: Record<string, UnresolvedNodeMutation> = { ...recUnresolved }
 const wrkPatchedKeys = new Set<string>(recPatchedKeys)
 const wrkPatchedIds: Record<string, string> = { ...recPatchedIds }
 const wrkBackups: Record<string, ReplacedNodeBackup> = { ...initialBackups }
 let walPadChars = Math.max(768, resolvedPack.overrides.length * 448)
 const buildWorkingSnapshot = (includePad: boolean): InstalledModRecord => ({ pack: resolvedPack, installedAt: initialRecord?.installedAt || new Date().toISOString(),
  createdNodeIds: Array.from(workingCreatedIds), ownedCustomTokens: copyIfNonEmpty(wrkOwnedToks), ownedCustomUserTemplates: copyIfNonEmpty(wrkOwnedTpls),
  pendingCreateTokens: copyIfNonEmpty(wrkPendToks), pendingCreateTemplates: copyIfNonEmpty(wrkPendTpls),
  patchedNodeKeys: Array.from(wrkPatchedKeys), patchedNodeIds: copyIfNonEmpty(wrkPatchedIds),
  replacedSystemBackups: copyIfNonEmpty(wrkBackups), unresolvedMutations: copyIfNonEmpty(wrkUnresolved),
  walReservationPad: includePad && walPadChars > 0 ? '0'.repeat(walPadChars) : undefined, })
 const commitWorkingRecord = (includePad = true): InstalledModRecord => { const snapshot = buildWorkingSnapshot(includePad)
  commitPackRecord(resolvedPack.id, snapshot)
  return snapshot }
 const assertSlotWalWritable = (slotKey: string, targetId: string, originTok?: string): void => { const cur = wrkUnresolved[slotKey], curTok = extractWalCustomToken(cur)
  if (!cur || (cur.targetNodeId ? cur.targetNodeId === targetId : Boolean(originTok && curTok === originTok))) return
  throw new Error(`节点键「${slotKey}」存在其他目标的未决变更记录，已保留恢复记录供稍候重试`) }
 const clearSlotWalIfTarget = (slotKey: string, targetId?: string, originTok?: string): void => { const cur = wrkUnresolved[slotKey]
  if (!cur) return
  const curTok = extractWalCustomToken(cur)
  if (cur.targetNodeId) { if (targetId && cur.targetNodeId !== targetId) return } else if (curTok) { if (!originTok || curTok !== originTok) return } else if (targetId || originTok) return
  delete wrkUnresolved[slotKey] }
 const deleteOrStripOwnedCustomDetail = async (targetDetail: PromptNodeDetail, expectedTok: string | undefined, recordedTpl: string | undefined, summaryText: string, includePad: boolean,
 ): Promise<{ hadValidBlock: boolean; strippedSystem: string }> => { const tKey = targetDetail.node_key
  const { strippedSystem, hadValidBlock } = stripOwnedCustomBlock(targetDetail.system ?? '', resolvedPack.id, expectedTok)
  const canDeleteWhole = hadValidBlock && strippedSystem === '' && recordedTpl !== undefined && (targetDetail.user_template ?? '') === recordedTpl
  if (canDeleteWhole) { assertSlotWalWritable(tKey, targetDetail.id, expectedTok)
   wrkUnresolved[tKey] = { kind: 'delete', targetNodeId: targetDetail.id, originToken: expectedTok, initialUserTemplate: recordedTpl, startedAt: Date.now() }
   commitWorkingRecord(includePad)
   try { await promptPlazaApi.deleteNode(targetDetail.id, buildDeleteNodePreconditionConfig(targetDetail)) } catch (delErr) { if (!isHttpNotFound(delErr)) {
     if (isDefinitivePreCommitHttpError(delErr)) { clearSlotWalIfTarget(tKey, targetDetail.id, expectedTok); commitWorkingRecord(includePad) }
     throw delErr } } } else if (hadValidBlock && strippedSystem !== (targetDetail.system ?? '')) { assertSlotWalWritable(tKey, targetDetail.id, expectedTok)
   wrkUnresolved[tKey] = { kind: 'patch', targetNodeId: targetDetail.id, priorSystem: targetDetail.system ?? '', writtenSystem: strippedSystem,
    originToken: expectedTok, initialUserTemplate: recordedTpl, startedAt: Date.now(), }
   commitWorkingRecord(includePad)
   try { await promptPlazaApi.updateNode(tKey, { ...buildSystemUpdatePreconditions(targetDetail), system: strippedSystem, change_summary: summaryText }, { silentGlobalFeedback: true })
   } catch (stripErr) { if (isDefinitivePreCommitHttpError(stripErr) && !isHttpNotFound(stripErr)) { clearSlotWalIfTarget(tKey, targetDetail.id, expectedTok); commitWorkingRecord(includePad) }
    throw stripErr } }
  return { hadValidBlock, strippedSystem } }
 for (const override of resolvedPack.overrides) { const repPlan = preflightReplacements.get(override.nodeKey)
  if (repPlan) { wrkPatchedKeys.add(override.nodeKey); wrkPatchedIds[override.nodeKey] = repPlan.targetNodeId
   wrkBackups[override.nodeKey] = { baselineSystem: repPlan.baselineSystem, targetNodeId: repPlan.targetNodeId } } }
 try { commitWorkingRecord(true) } catch (preflightStorageErr) { try { reloadAuthoritativeMap() } catch { /* keep memory */ } throw preflightStorageErr }
 const actTargetCreatedIds = new Set<string>()
 canonSlotByTok.clear()
 const actTargetPatchedKeys = new Set<string>()
 const actPatchedTargetIds = new Set<string>()
 const observedTargetNodeIds = new Set<string>()
 const observedCustomTokById = new Map<string, string>()
 const appliedSteps: InFlightOrAppliedStep[] = []
 try { for (const override of resolvedPack.overrides) { const rawLive = await fetchExistingNodeOrNull(override.nodeKey)
   const liveDetail = rawLive?.node_key === override.nodeKey ? rawLive : null
   if (liveDetail?.id) { observedTargetNodeIds.add(liveDetail.id)
    const obsTok = !liveDetail.is_builtin ? extractCustomOriginToken(liveDetail.system ?? '', resolvedPack.id) : null
    if (obsTok) observedCustomTokById.set(liveDetail.id, obsTok) }
   if (liveDetail && !liveDetail.is_builtin && !ownedCreatedIdSet.has(liveDetail.id)) {
    const matchedPending = Object.entries(wrkPendToks).find(([, pTok]) => Boolean(pTok) && hasMatchingCustomOriginToken(liveDetail.system ?? '', resolvedPack.id, pTok))
    if (matchedPending) { const [pSlot, pTok] = matchedPending, uniqueLive = await discoverCustomNodeByOriginToken(resolvedPack.id, pTok)
     if (uniqueLive && uniqueLive.id === liveDetail.id) { const pTpl = lookupTplForToken(wrkPendToks, wrkPendTpls, pTok, pSlot).tpl
      await promoteDiscoveredCustom(liveDetail, pTok, pTpl, wrkOwnedToks, wrkOwnedTpls, wrkPendToks, wrkPendTpls, wrkUnresolved, pSlot) } } }
   const stepPlan = validateAndPlanOverride(override, liveDetail, wrkOwnedToks, wrkOwnedTpls)
   if (stepPlan.kind === 'create_new_custom') { const originToken = generateOriginToken()
    const wrappedSystem = buildOwnedCustomBlock(resolvedPack.id, originToken, override.systemContent)
    const initialTpl = override.userTemplate ?? '{context}\n\n{outline}'
    await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, override.nodeKey, originToken, wrkUnresolved)
    const displacedPendingTok = wrkPendToks[override.nodeKey]
    if (displacedPendingTok && displacedPendingTok !== originToken) {
     archivePendingCred(wrkPendToks, wrkPendTpls, override.nodeKey, displacedPendingTok, wrkPendTpls[override.nodeKey]) }
    wrkPendToks[override.nodeKey] = originToken; wrkPendTpls[override.nodeKey] = initialTpl
    wrkUnresolved[override.nodeKey] = { kind: 'create', originToken, initialUserTemplate: initialTpl, writtenSystem: wrappedSystem, startedAt: Date.now() }
    walPadChars = Math.max(0, walPadChars - 224)
    commitWorkingRecord(true)
    const createStep: InFlightOrAppliedStep = { kind: 'create_custom', nodeKey: override.nodeKey, originToken, writtenSystem: wrappedSystem, initialUserTemplate: initialTpl, completed: false, }
    appliedSteps.push(createStep)
    let created: Awaited<ReturnType<typeof promptPlazaApi.createNode>>
    try { created = await promptPlazaApi.createNode({ node_key: override.nodeKey, name: override.nodeLabel, description: resolvedPack.summary,
      category: override.backendCategory || 'creative', system: wrappedSystem, user_template: initialTpl, }, { silentGlobalFeedback: true })
    } catch (wErr) { createStep.dispatchError = wErr; throw wErr }
    const createdId = created?.node?.id
    if (!createdId) { const missingIdErr = new Error(`创建自定义节点「${override.nodeKey}」未返回有效节点 ID`); createStep.dispatchError = missingIdErr; throw missingIdErr }
    createStep.completed = true; createStep.createdId = createdId
    workingCreatedIds.add(createdId)
    await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, override.nodeKey, originToken, wrkUnresolved)
    syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, override.nodeKey, originToken, initialTpl)
    canonSlotByTok.set(originToken, override.nodeKey)
    delPendingByTok(wrkPendToks, wrkPendTpls, originToken)
    delete wrkUnresolved[override.nodeKey]
    commitWorkingRecord(true)
    actTargetCreatedIds.add(createdId); observedTargetNodeIds.add(createdId)
    continue }
   if (stepPlan.kind === 'update_owned_custom') { const { detail: curDetail, customPlan, inheritedOwnedTpl: hadPriorOwnedTpl } = stepPlan
    const priorName = curDetail.name, priorDescription = curDetail.description || '', priorSystem = curDetail.system ?? '', priorUserTemplate = curDetail.user_template ?? ''
    await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, override.nodeKey, customPlan.verifiedToken, wrkUnresolved)
    wrkOwnedToks[override.nodeKey] = customPlan.verifiedToken
    const preWriteBaselineTpl = override.userTemplate !== undefined && priorUserTemplate === override.userTemplate ? override.userTemplate : hadPriorOwnedTpl
    if (preWriteBaselineTpl !== undefined) wrkOwnedTpls[override.nodeKey] = preWriteBaselineTpl; else delete wrkOwnedTpls[override.nodeKey]
    const needsWrite = override.nodeLabel !== priorName || resolvedPack.summary !== priorDescription || customPlan.nextSystem !== priorSystem || (override.userTemplate !== undefined && override.userTemplate !== priorUserTemplate)
    if (needsWrite) { assertSlotWalWritable(override.nodeKey, curDetail.id, customPlan.verifiedToken)
     wrkUnresolved[override.nodeKey] = { kind: 'patch', targetNodeId: curDetail.id, priorName, priorDescription, priorSystem, priorUserTemplate,
      writtenName: override.nodeLabel, writtenDescription: resolvedPack.summary, writtenSystem: customPlan.nextSystem,
      writtenUserTemplate: override.userTemplate, originToken: customPlan.verifiedToken, initialUserTemplate: preWriteBaselineTpl,
      targetOwnedUserTemplate: override.userTemplate !== undefined ? override.userTemplate : (preWriteBaselineTpl ?? null), startedAt: Date.now(), }
     walPadChars = Math.max(0, walPadChars - 224); commitWorkingRecord(true)
     const updateCustomStep: InFlightOrAppliedStep = { kind: 'updated_owned_custom', nodeId: curDetail.id, nodeKey: override.nodeKey, originToken: customPlan.verifiedToken,
      priorName, priorDescription, priorSystem, priorUserTemplate, writtenName: override.nodeLabel, writtenDescription: resolvedPack.summary,
      writtenSystem: customPlan.nextSystem, updatedUserTemplate: override.userTemplate, hadPriorOwnedTpl, completed: false, }
     appliedSteps.push(updateCustomStep)
     try { await promptPlazaApi.updateNode(override.nodeKey, {
       ...buildOwnedCustomUpdatePreconditions(curDetail), name: override.nodeLabel, description: resolvedPack.summary, system: customPlan.nextSystem,
       ...(override.userTemplate !== undefined ? { user_template: override.userTemplate } : {}), change_summary: `更新模组「${resolvedPack.name}」(${resolvedPack.version})`,
      }, { silentGlobalFeedback: true }) } catch (wErr) { updateCustomStep.dispatchError = wErr; throw wErr }
     updateCustomStep.completed = true; clearSlotWalIfTarget(override.nodeKey, curDetail.id, customPlan.verifiedToken) }
    const nextOwnedTpl = override.userTemplate !== undefined ? override.userTemplate : preWriteBaselineTpl
    syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, override.nodeKey, customPlan.verifiedToken, nextOwnedTpl)
    canonSlotByTok.set(customPlan.verifiedToken, override.nodeKey); commitWorkingRecord(true)
    actTargetCreatedIds.add(curDetail.id); continue }
   const curDetail = stepPlan.detail, priorSystem = curDetail.system ?? '', isReplace = stepPlan.kind === 'replace_existing'
   const nextSystem = isReplace ? stepPlan.repPlan.nextSystem : stepPlan.nextSystem
   const hadPriorBackup = isReplace ? initialBackups[override.nodeKey] : stepPlan.priorOwnedBackup
   const summaryPrefix = isReplace ? '接管节点：模组' : stepPlan.kind === 'patch_builtin_standalone' ? '启用模组' : '挂载模组'
   wrkPatchedKeys.add(override.nodeKey); wrkPatchedIds[override.nodeKey] = curDetail.id
   if (isReplace) wrkBackups[override.nodeKey] = { baselineSystem: stepPlan.repPlan.baselineSystem, targetNodeId: curDetail.id }
   if (nextSystem !== priorSystem) { assertSlotWalWritable(override.nodeKey, curDetail.id)
    wrkUnresolved[override.nodeKey] = { kind: 'patch', targetNodeId: curDetail.id, priorSystem, writtenSystem: nextSystem, startedAt: Date.now() }
    walPadChars = Math.max(0, walPadChars - 224); commitWorkingRecord(true)
    const patchStep: InFlightOrAppliedStep = { kind: 'patched_existing', targetNodeId: curDetail.id, nodeKey: override.nodeKey, priorSystem, writtenSystem: nextSystem,
     hadPriorBackup, hadPriorPatchedId: recPatchedIds[override.nodeKey], completed: false, }
    appliedSteps.push(patchStep)
    try {
     await promptPlazaApi.updateNode(override.nodeKey, { ...buildSystemUpdatePreconditions(curDetail), system: nextSystem, change_summary: `${summaryPrefix}「${resolvedPack.name}」(${resolvedPack.version})` }, { silentGlobalFeedback: true })
    } catch (wErr) { patchStep.dispatchError = wErr; throw wErr }
    patchStep.completed = true; clearSlotWalIfTarget(override.nodeKey, curDetail.id); commitWorkingRecord(true) } else commitWorkingRecord(true)
   actTargetPatchedKeys.add(override.nodeKey); actPatchedTargetIds.add(curDetail.id) } } catch (stepErr) { const compErrors: string[] = []
  for (const override of resolvedPack.overrides) { if (!appliedSteps.some(s => s.nodeKey === override.nodeKey)) {
    if (recPatchedKeys.has(override.nodeKey)) wrkPatchedKeys.add(override.nodeKey); else wrkPatchedKeys.delete(override.nodeKey)
    if (recPatchedIds[override.nodeKey] !== undefined) wrkPatchedIds[override.nodeKey] = recPatchedIds[override.nodeKey]; else delete wrkPatchedIds[override.nodeKey]
    if (initialBackups[override.nodeKey]) wrkBackups[override.nodeKey] = initialBackups[override.nodeKey]; else delete wrkBackups[override.nodeKey] } }
  for (let idx = appliedSteps.length - 1; idx >= 0; idx -= 1) { const step = appliedSteps[idx]
   try { const clearOwnedCustomSlotIfToken = (k: string, tok: string) => {
     if (!wrkOwnedToks[k] || wrkOwnedToks[k] === tok) { delete wrkOwnedToks[k]; delete wrkOwnedTpls[k] } }
    if (step.kind === 'create_custom') {
     let live: PromptNodeDetail | null = null
     if (step.completed && step.createdId) live = await fetchNodeByVerifiedId(step.createdId)
     else if (!isDefinitivePreCommitHttpError(step.dispatchError)) live = await discoverCustomNodeByOriginToken(resolvedPack.id, step.originToken)
     if (!live) { if (step.completed) { if (step.createdId) workingCreatedIds.delete(step.createdId)
       clearOwnedCustomSlotIfToken(step.nodeKey, step.originToken)
       delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
       clearSlotWalIfTarget(step.nodeKey, step.createdId, step.originToken); commitWorkingRecord(true) } else if (isDefinitivePreCommitHttpError(step.dispatchError)) {
       delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
       clearSlotWalIfTarget(step.nodeKey, step.createdId, step.originToken); commitWorkingRecord(true) } else compErrors.push(`${step.nodeKey}: 创建请求超时或状态未决，已保留归属凭证以防延迟落盘失管`)
     } else if (!live.is_builtin && hasMatchingCustomOriginToken(live.system ?? '', resolvedPack.id, step.originToken)) { const liveKey = live.node_key
      workingCreatedIds.add(live.id)
      await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, liveKey, step.originToken, wrkUnresolved)
      wrkOwnedToks[liveKey] = step.originToken; wrkOwnedTpls[liveKey] = step.initialUserTemplate
      delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
      const deps = findForeignDependentPackNames(liveKey, resolvedPack.id, live.id)
      if (deps.length > 0 || hasForeignContentLayers(live.system ?? '', resolvedPack.id)) { clearSlotWalIfTarget(step.nodeKey, live.id, step.originToken); commitWorkingRecord(true)
       compErrors.push(`${liveKey}: 新建节点已挂载其他模组内容，已保留节点归属避免破坏外层模组`); continue }
      await deleteOrStripOwnedCustomDetail(live, step.originToken, step.initialUserTemplate, `模组「${resolvedPack.name}」安装回滚并保留用户编辑内容`, true)
      workingCreatedIds.delete(live.id)
      clearOwnedCustomSlotIfToken(liveKey, step.originToken); clearOwnedCustomSlotIfToken(step.nodeKey, step.originToken)
      delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
      clearSlotWalIfTarget(liveKey, live.id, step.originToken); clearSlotWalIfTarget(step.nodeKey, live.id, step.originToken)
      commitWorkingRecord(true) } else if (step.completed) { delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
      if (hasAnyModBlock(live.system ?? '', resolvedPack.id) || hasPackModMention(live.system ?? '', resolvedPack.id)) {
       clearSlotWalIfTarget(step.nodeKey, step.createdId, step.originToken); commitWorkingRecord(true)
       compErrors.push(`${live.node_key}: 新建节点边界标记已被手动改写，已保留节点以防覆盖您的修改`) } else { if (step.createdId) workingCreatedIds.delete(step.createdId)
       clearOwnedCustomSlotIfToken(step.nodeKey, step.originToken)
       clearSlotWalIfTarget(step.nodeKey, step.createdId, step.originToken); commitWorkingRecord(true) } } else if (isDefinitivePreCommitHttpError(step.dispatchError)) {
      delPendingByTok(wrkPendToks, wrkPendTpls, step.originToken)
      clearSlotWalIfTarget(step.nodeKey, step.createdId, step.originToken); commitWorkingRecord(true) } else compErrors.push(`${step.nodeKey}: 创建请求超时或状态未决，已保留归属凭证以防延迟落盘失管`)
    } else if (step.kind === 'updated_owned_custom') { const live = await fetchNodeByVerifiedId(step.nodeId)
     const pruneMovedStepSlot = () => { if (live && live.node_key !== step.nodeKey && wrkOwnedToks[step.nodeKey] === step.originToken && !wrkUnresolved[step.nodeKey]) {
       delete wrkOwnedToks[step.nodeKey]; delete wrkOwnedTpls[step.nodeKey] } }
     const forwardCommittedUnchanged = Boolean(live) && hasPatchMutationCommitted(live!, { kind: 'patch', writtenName: step.writtenName, writtenDescription: step.writtenDescription,
      writtenSystem: step.writtenSystem, writtenUserTemplate: step.updatedUserTemplate, })
     if (forwardCommittedUnchanged && live) { assertSlotWalWritable(live.node_key, live.id, step.originToken)
      const preRevertTpl = step.updatedUserTemplate !== undefined ? step.updatedUserTemplate : step.hadPriorOwnedTpl
      if (live.node_key !== step.nodeKey) clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken)
      await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, live.node_key, step.originToken, wrkUnresolved)
      syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, live.node_key, step.originToken, preRevertTpl, true, wrkUnresolved)
      wrkUnresolved[live.node_key] = { kind: 'patch', targetNodeId: live.id, priorName: step.writtenName, priorDescription: step.writtenDescription, priorSystem: step.writtenSystem,
       priorUserTemplate: step.updatedUserTemplate ?? step.priorUserTemplate, writtenName: step.priorName, writtenDescription: step.priorDescription, writtenSystem: step.priorSystem,
       writtenUserTemplate: step.updatedUserTemplate !== undefined ? step.priorUserTemplate : undefined,
       originToken: step.originToken, initialUserTemplate: preRevertTpl, targetOwnedUserTemplate: step.hadPriorOwnedTpl ?? null, startedAt: Date.now(), }
      pruneMovedStepSlot(); commitWorkingRecord(true)
      try { await promptPlazaApi.updateNode(live.node_key, { ...buildOwnedCustomUpdatePreconditions(live), name: step.priorName, description: step.priorDescription, system: step.priorSystem,
        ...(step.updatedUserTemplate !== undefined ? { user_template: step.priorUserTemplate } : {}), change_summary: `模组「${resolvedPack.name}」安装中断自动恢复`, }, { silentGlobalFeedback: true })
      } catch (rErr) { if (isDefinitivePreCommitHttpError(rErr) && !isHttpNotFound(rErr)) { clearSlotWalIfTarget(live.node_key, live.id, step.originToken); commitWorkingRecord(true) }
       throw rErr }
      clearSlotWalIfTarget(live.node_key, live.id, step.originToken); clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken)
      syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, live.node_key, step.originToken, step.hadPriorOwnedTpl)
      pruneMovedStepSlot(); commitWorkingRecord(true) } else if (step.completed) { if (!live) { workingCreatedIds.delete(step.nodeId); clearOwnedCustomSlotIfToken(step.nodeKey, step.originToken)
       clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken); commitWorkingRecord(true)
      } else if (hasAnyModBlock(live.system ?? '', resolvedPack.id) || hasPackModMention(live.system ?? '', resolvedPack.id)) { workingCreatedIds.add(live.id)
       await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, live.node_key, step.originToken, wrkUnresolved)
       syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, live.node_key, step.originToken, step.updatedUserTemplate ?? step.hadPriorOwnedTpl, true, wrkUnresolved)
       clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken); pruneMovedStepSlot(); commitWorkingRecord(true)
       compErrors.push(`${step.nodeKey}: 独立节点在安装期间检测到新增用户修改，为保护您的编辑内容已跳过旧快照覆盖并保留恢复记录`) } else { workingCreatedIds.delete(step.nodeId); workingCreatedIds.delete(live.id)
       clearOwnedCustomSlotIfToken(step.nodeKey, step.originToken); clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken); commitWorkingRecord(true) }
     } else if (isDefinitivePreCommitHttpError(step.dispatchError)) { clearSlotWalIfTarget(step.nodeKey, step.nodeId, step.originToken)
      if (wrkOwnedToks[step.nodeKey] === step.originToken) {
       syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, step.nodeKey, step.originToken, step.hadPriorOwnedTpl)
       pruneMovedStepSlot() }
      commitWorkingRecord(true) } else compErrors.push(`${step.nodeKey}: 独立节点更新结果未决，已保留恢复记录以防延迟落盘`) } else if (step.kind === 'patched_existing') { const deleteSlotBackupIfTarget = () => {
      const curBkp = wrkBackups[step.nodeKey]
      if (!curBkp?.targetNodeId || curBkp.targetNodeId === step.targetNodeId) delete wrkBackups[step.nodeKey] }
     const restorePriorSlotBackupState = () => { const curPatchedId = wrkPatchedIds[step.nodeKey]
      if (curPatchedId === undefined || curPatchedId === step.targetNodeId) {
       if (recPatchedKeys.has(step.nodeKey)) wrkPatchedKeys.add(step.nodeKey); else wrkPatchedKeys.delete(step.nodeKey)
       if (step.hadPriorPatchedId !== undefined) wrkPatchedIds[step.nodeKey] = step.hadPriorPatchedId; else delete wrkPatchedIds[step.nodeKey] }
      const curBkp = wrkBackups[step.nodeKey]
      if (!curBkp?.targetNodeId || curBkp.targetNodeId === step.targetNodeId) {
       if (initialBackups[step.nodeKey]) wrkBackups[step.nodeKey] = initialBackups[step.nodeKey]; else delete wrkBackups[step.nodeKey] } }
     const canRelocatePatchedToLiveKey = (destKey: string, targetId: string): boolean => destKey === step.nodeKey || (
       (wrkPatchedIds[destKey] === undefined || wrkPatchedIds[destKey] === targetId) && (!wrkPatchedKeys.has(destKey) || wrkPatchedIds[destKey] === targetId) &&
       (wrkBackups[destKey] === undefined || wrkBackups[destKey].targetNodeId === targetId) && wrkOwnedToks[destKey] === undefined &&
       wrkPendToks[destKey] === undefined && (wrkUnresolved[destKey] === undefined ||
        (wrkUnresolved[destKey].targetNodeId === targetId && extractWalCustomToken(wrkUnresolved[destKey]) === undefined && wrkUnresolved[destKey].kind === 'patch'))
      )
     const unwindStepWalAfterConfirmedRestore = () => { clearSlotWalIfTarget(step.nodeKey, step.targetNodeId); restorePriorSlotBackupState(); commitWorkingRecord(true) }
     const live = await fetchNodeByVerifiedId(step.targetNodeId)
     if (live && (live.system ?? '') === step.writtenSystem) { assertSlotWalWritable(live.node_key, live.id)
      const curBkp = wrkBackups[step.nodeKey]
      if (initialBackups[step.nodeKey] && (!curBkp?.targetNodeId || curBkp.targetNodeId === step.targetNodeId)) wrkBackups[step.nodeKey] = initialBackups[step.nodeKey]
      wrkUnresolved[live.node_key] = { kind: 'patch', targetNodeId: live.id, priorSystem: step.writtenSystem, writtenSystem: step.priorSystem, startedAt: Date.now() }
      commitWorkingRecord(true)
      try {
       await promptPlazaApi.updateNode(live.node_key, { ...buildSystemUpdatePreconditions(live), system: step.priorSystem, change_summary: `模组「${resolvedPack.name}」安装中断自动恢复` }, { silentGlobalFeedback: true })
      } catch (rErr) { if (isDefinitivePreCommitHttpError(rErr) && !isHttpNotFound(rErr)) { clearSlotWalIfTarget(live.node_key, live.id); commitWorkingRecord(true) }
       throw rErr }
      clearSlotWalIfTarget(live.node_key, live.id); unwindStepWalAfterConfirmedRestore() } else if (step.completed) { clearSlotWalIfTarget(step.nodeKey, step.targetNodeId)
      if (!live) {
       if (!wrkPatchedIds[step.nodeKey] || wrkPatchedIds[step.nodeKey] === step.targetNodeId) { wrkPatchedKeys.delete(step.nodeKey); delete wrkPatchedIds[step.nodeKey] }
       deleteSlotBackupIfTarget(); commitWorkingRecord(true) } else if (hasReplacedModBlock(live.system ?? '', resolvedPack.id)) {
       const targetSlot = canRelocatePatchedToLiveKey(live.node_key, live.id) ? live.node_key : step.nodeKey
       const stepBkp = wrkBackups[step.nodeKey]
       const ownBkp = (stepBkp && (!stepBkp.targetNodeId || stepBkp.targetNodeId === live.id) ? stepBkp : undefined) ?? (step.hadPriorBackup && (!step.hadPriorBackup.targetNodeId || step.hadPriorBackup.targetNodeId === live.id) ? step.hadPriorBackup : undefined)
       if (targetSlot !== step.nodeKey) { if (ownBkp) wrkBackups[targetSlot] = { ...ownBkp, targetNodeId: live.id }
        deleteSlotBackupIfTarget()
        if (!wrkPatchedIds[step.nodeKey] || wrkPatchedIds[step.nodeKey] === live.id) { delete wrkPatchedIds[step.nodeKey]; if (!wrkBackups[step.nodeKey]) wrkPatchedKeys.delete(step.nodeKey) }
       } else if (ownBkp) wrkBackups[step.nodeKey] = { ...ownBkp, targetNodeId: live.id }
       wrkPatchedKeys.add(targetSlot); wrkPatchedIds[targetSlot] = live.id; commitWorkingRecord(true)
       compErrors.push(`${live.node_key}: 节点在安装期间检测到新增用户修改，为保护您的编辑内容已跳过旧快照覆盖并保留原始基线快照`)
      } else if (hasAnyModBlock(live.system ?? '', resolvedPack.id) || hasPackModMention(live.system ?? '', resolvedPack.id)) {
       const targetSlot = canRelocatePatchedToLiveKey(live.node_key, live.id) ? live.node_key : step.nodeKey
       deleteSlotBackupIfTarget()
       if (targetSlot !== step.nodeKey) { if (wrkBackups[targetSlot]?.targetNodeId === live.id) delete wrkBackups[targetSlot]
        if (!wrkPatchedIds[step.nodeKey] || wrkPatchedIds[step.nodeKey] === live.id) { delete wrkPatchedIds[step.nodeKey]; if (!wrkBackups[step.nodeKey]) wrkPatchedKeys.delete(step.nodeKey) }
       }
       wrkPatchedKeys.add(targetSlot); wrkPatchedIds[targetSlot] = live.id; commitWorkingRecord(true)
       compErrors.push(`${live.node_key}: 节点在安装期间检测到新增用户修改，为保护您的编辑内容已跳过旧快照覆盖并保留恢复记录`) } else { restorePriorSlotBackupState(); deleteSlotBackupIfTarget(); commitWorkingRecord(true) }
     } else if (isDefinitivePreCommitHttpError(step.dispatchError)) { unwindStepWalAfterConfirmedRestore() } else { compErrors.push(`${step.nodeKey}: 更新请求超时或状态未决，已保留原始基线快照以防延迟提交丢失原稿`) } }
   } catch (compErr) { compErrors.push(`${step.nodeKey}: ${compErr instanceof Error ? compErr.message : String(compErr)}`) } }
  if (compErrors.length === 0) { try { commitPackRecord(resolvedPack.id, recBaselineRec) } catch { /* baseline restored */ }
   throw formatBackendError(stepErr, `安装模组「${resolvedPack.name}」失败`) }
  try { commitWorkingRecord(false) } catch (persistCompErr) { compErrors.push(`存储同步告警: ${persistCompErr instanceof Error ? persistCompErr.message : String(persistCompErr)}`) }
  const primaryMsg = formatBackendError(stepErr, `安装模组「${resolvedPack.name}」中断`).message
  throw new Error(`${primaryMsg}（部分节点状态需保留恢复记录供在「已安装」中重试清理：${compErrors.join('；')}）`) }
 for (const ov of resolvedPack.overrides) { if (ov.mode !== 'replace_system' && actTargetPatchedKeys.has(ov.nodeKey)) {
   const slotBkp = wrkBackups[ov.nodeKey], activePid = wrkPatchedIds[ov.nodeKey]
   if (slotBkp && activePid && (!slotBkp.targetNodeId || slotBkp.targetNodeId === activePid)) delete wrkBackups[ov.nodeKey] } }
 for (const [bKey, bVal] of Object.entries({ ...wrkBackups })) { if (!bVal.targetNodeId) continue
  const matchingActiveOv = resolvedPack.overrides.find(o => actTargetPatchedKeys.has(o.nodeKey) && wrkPatchedIds[o.nodeKey] === bVal.targetNodeId)
  if (matchingActiveOv && matchingActiveOv.mode !== 'replace_system') delete wrkBackups[bKey] }
 commitWorkingRecord(false)
 const stillTargetedNodeIds = new Set<string>([...actTargetCreatedIds, ...observedTargetNodeIds])
 const cleanedCustomTokens = new Set<string>(), retainedCustomTokens = new Set<string>(), dupCustomToks = new Set<string>()
 let hasUnverifiedRetainedCustom = false
 const releaseOwnedTokenSlots = (tok: string | undefined): void => { if (!tok || dupCustomToks.has(tok)) return
  cleanedCustomTokens.add(tok); delPendingByTok(wrkPendToks, wrkPendTpls, tok)
  for (const [k, slotTok] of Object.entries({ ...wrkOwnedToks })) if (slotTok === tok && !wrkUnresolved[k]) { delete wrkOwnedToks[k]; delete wrkOwnedTpls[k] }
 }
 const cleanOrRetainObsoleteCustomNode = async (oldNodeId: string, prefetchedDetail?: PromptNodeDetail | null): Promise<void> => { if (stillTargetedNodeIds.has(oldNodeId)) {
   workingCreatedIds.add(oldNodeId); if (!actTargetCreatedIds.has(oldNodeId)) hasUnverifiedRetainedCustom = true; return }
  let oldKeyForCleanup: string | null = null, verifiedNodeTok: string | undefined
  try { const oldNodeDetail = prefetchedDetail !== undefined ? prefetchedDetail : await fetchNodeByVerifiedId(oldNodeId)
   if (!oldNodeDetail) { workingCreatedIds.delete(oldNodeId); commitWorkingRecord(false); return }
   const oldKey = oldNodeDetail.node_key, oldSys = oldNodeDetail.system ?? ''; oldKeyForCleanup = oldKey
   const liveObsTok = !oldNodeDetail.is_builtin ? extractCustomOriginToken(oldSys, resolvedPack.id) : null
   if (liveObsTok && dupCustomToks.has(liveObsTok)) { workingCreatedIds.add(oldNodeId); retainedCustomTokens.add(liveObsTok); hasUnverifiedRetainedCustom = true; commitWorkingRecord(false); return }
   const matchedTokSlot = wrkOwnedToks[oldKey] && hasMatchingCustomOriginToken(oldSys, resolvedPack.id, wrkOwnedToks[oldKey])
    ? oldKey : Object.entries(wrkOwnedToks).find(([, tok]) => Boolean(tok) && hasMatchingCustomOriginToken(oldSys, resolvedPack.id, tok))?.[0]
   const matchedPendingSlot = matchedTokSlot ? undefined : (wrkPendToks[oldKey] && hasMatchingCustomOriginToken(oldSys, resolvedPack.id, wrkPendToks[oldKey])
    ? oldKey : Object.entries(wrkPendToks).find(([, tok]) => Boolean(tok) && hasMatchingCustomOriginToken(oldSys, resolvedPack.id, tok))?.[0])
   verifiedNodeTok = matchedTokSlot ? wrkOwnedToks[matchedTokSlot] : (matchedPendingSlot ? wrkPendToks[matchedPendingSlot] : undefined)
   const recordedTpl = matchedTokSlot ? wrkOwnedTpls[matchedTokSlot] : (matchedPendingSlot ? wrkPendTpls[matchedPendingSlot] : undefined)
   const deps = findForeignDependentPackNames(oldKey, resolvedPack.id, oldNodeId)
   if (deps.length > 0 || hasForeignContentLayers(oldSys, resolvedPack.id)) { workingCreatedIds.add(oldNodeId)
    if (verifiedNodeTok) { await relocateDisplacedToken(wrkOwnedToks, wrkOwnedTpls, oldKey, verifiedNodeTok, wrkUnresolved)
     syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, oldKey, verifiedNodeTok, recordedTpl, true, wrkUnresolved)
     delPendingByTok(wrkPendToks, wrkPendTpls, verifiedNodeTok)
     retainedCustomTokens.add(verifiedNodeTok) } else hasUnverifiedRetainedCustom = true
    commitWorkingRecord(false); return }
   const { hadValidBlock } = await deleteOrStripOwnedCustomDetail(oldNodeDetail, verifiedNodeTok, recordedTpl, `升级模组「${resolvedPack.name}」并剥离已废弃的模组区间`, false)
   if (hadValidBlock || (!hasAnyModBlock(oldSys, resolvedPack.id) && !hasPackModMention(oldSys, resolvedPack.id))) {
    workingCreatedIds.delete(oldNodeId); clearSlotWalIfTarget(oldKey, oldNodeId, verifiedNodeTok)
    releaseOwnedTokenSlots(verifiedNodeTok); commitWorkingRecord(false) } else {
    workingCreatedIds.add(oldNodeId); if (verifiedNodeTok) retainedCustomTokens.add(verifiedNodeTok); else hasUnverifiedRetainedCustom = true
    commitWorkingRecord(false) } } catch (cleanCustomErr) { if (isHttpNotFound(cleanCustomErr) && !(await fetchNodeByVerifiedId(oldNodeId).catch(() => ({ id: oldNodeId })))) {
    workingCreatedIds.delete(oldNodeId); if (oldKeyForCleanup) clearSlotWalIfTarget(oldKeyForCleanup, oldNodeId, verifiedNodeTok)
    releaseOwnedTokenSlots(verifiedNodeTok); commitWorkingRecord(false) } else {
    workingCreatedIds.add(oldNodeId); if (verifiedNodeTok) retainedCustomTokens.add(verifiedNodeTok); else hasUnverifiedRetainedCustom = true
    commitWorkingRecord(false) } } }
 for (const [pKey, pTok] of Object.entries({ ...wrkPendToks })) { if (!pTok) { delete wrkPendToks[pKey]; delete wrkPendTpls[pKey]; continue }
  if (Object.values(wrkUnresolved).some(um => extractWalCustomToken(um) === pTok && isWithinAmbiguityWindow(um))) continue
  try { const lateLive = await discoverCustomNodeByOriginToken(resolvedPack.id, pTok)
   const pTpl = lookupTplForToken(wrkPendToks, wrkPendTpls, pTok, pKey).tpl
   if (lateLive) {
    await promoteDiscoveredCustom(lateLive, pTok, pTpl, wrkOwnedToks, wrkOwnedTpls, wrkPendToks, wrkPendTpls, wrkUnresolved, pKey)
   } else archivePendingCred(wrkPendToks, wrkPendTpls, baseKeyOfPendingSlot(pKey), pTok, pTpl)
  } catch { hasUnverifiedRetainedCustom = true; retainedCustomTokens.add(pTok); commitWorkingRecord(false) } }
 const prefetchedObsolete = new Map<string, PromptNodeDetail | null | 'err'>()
 for (const oldNodeId of Array.from(ownedCreatedIdSet)) { if (stillTargetedNodeIds.has(oldNodeId)) continue
  try { const d = await fetchNodeByVerifiedId(oldNodeId); prefetchedObsolete.set(oldNodeId, d)
   const t = d && !d.is_builtin ? extractCustomOriginToken(d.system ?? '', resolvedPack.id) : null
   if (d && t) observedCustomTokById.set(d.id, t) } catch { prefetchedObsolete.set(oldNodeId, 'err') } }
 const seenObsToks = new Set<string>()
 for (const t of observedCustomTokById.values()) { if (seenObsToks.has(t)) dupCustomToks.add(t); else seenObsToks.add(t) }
 for (const pre of prefetchedObsolete.values()) { const t = pre && pre !== 'err' && !pre.is_builtin ? extractCustomOriginToken(pre.system ?? '', resolvedPack.id) : null
  if (t && !dupCustomToks.has(t)) { try { await discoverCustomNodeByOriginToken(resolvedPack.id, t) } catch { dupCustomToks.add(t); hasUnverifiedRetainedCustom = true } } }
 for (const oldNodeId of Array.from(ownedCreatedIdSet)) { const pre = prefetchedObsolete.get(oldNodeId)
  if (pre === 'err') { workingCreatedIds.add(oldNodeId); hasUnverifiedRetainedCustom = true; commitWorkingRecord(false) } else await cleanOrRetainObsoleteCustomNode(oldNodeId, pre) }
 for (const [tok, canonicalKey] of canonSlotByTok) {
  syncTokenBaselineOnMap(wrkOwnedToks, wrkOwnedTpls, canonicalKey, tok, wrkOwnedTpls[canonicalKey], true, wrkUnresolved)
  retainedCustomTokens.add(tok) }
 if (!hasUnverifiedRetainedCustom) { for (const slotTok of Array.from(new Set(Object.values(wrkOwnedToks)))) {
   if (!slotTok || retainedCustomTokens.has(slotTok) || cleanedCustomTokens.has(slotTok)) continue
   if (Object.values(wrkUnresolved).some(um => extractWalCustomToken(um) === slotTok && isWithinAmbiguityWindow(um))) { retainedCustomTokens.add(slotTok); continue }
   try { const orphanLive = await discoverCustomNodeByOriginToken(resolvedPack.id, slotTok)
    if (orphanLive) { ownedCreatedIdSet.add(orphanLive.id); await cleanOrRetainObsoleteCustomNode(orphanLive.id, orphanLive)
     if (workingCreatedIds.has(orphanLive.id)) retainedCustomTokens.add(slotTok) } else cleanedCustomTokens.add(slotTok) } catch { retainedCustomTokens.add(slotTok); commitWorkingRecord(false) }
  }
  for (const [k, slotTok] of Object.entries({ ...wrkOwnedToks })) if (!retainedCustomTokens.has(slotTok) && !wrkUnresolved[k]) { delete wrkOwnedToks[k]; delete wrkOwnedTpls[k] }
  for (const k of Object.keys({ ...wrkOwnedTpls })) if (!wrkOwnedToks[k] && !wrkUnresolved[k]) delete wrkOwnedTpls[k] }
 for (const oldKey of Array.from(new Set([...wrkPatchedKeys, ...Object.keys(wrkPatchedIds), ...Object.keys(wrkBackups)]))) { if (actTargetPatchedKeys.has(oldKey)) continue
  const recordedOldId = wrkPatchedIds[oldKey] ?? wrkBackups[oldKey]?.targetNodeId ?? initialBackups[oldKey]?.targetNodeId
  if (recordedOldId && actPatchedTargetIds.has(recordedOldId)) { wrkPatchedKeys.delete(oldKey); delete wrkPatchedIds[oldKey]; delete wrkBackups[oldKey]
   clearSlotWalIfTarget(oldKey, recordedOldId); commitWorkingRecord(false); continue }
  try { const rawOldDetail = recordedOldId ? await fetchNodeByVerifiedId(recordedOldId) : await fetchExistingNodeOrNull(oldKey)
   const oldDetail = !recordedOldId && rawOldDetail && rawOldDetail.node_key !== oldKey ? null : rawOldDetail
   if (!oldDetail) { if (!recordedOldId) { wrkPatchedKeys.add(oldKey); if (initialBackups[oldKey]) wrkBackups[oldKey] = initialBackups[oldKey]; commitWorkingRecord(false); continue }
    wrkPatchedKeys.delete(oldKey); delete wrkPatchedIds[oldKey]; delete wrkBackups[oldKey]
    clearSlotWalIfTarget(oldKey, recordedOldId); commitWorkingRecord(false); continue }
   const liveOldKey = oldDetail.node_key, currentSys = oldDetail.system ?? '', oldBackup = wrkBackups[oldKey] ?? initialBackups[oldKey]
   const oldIdBoundElsewhere = workingCreatedIds.has(oldDetail.id) || actPatchedTargetIds.has(oldDetail.id) ||
    Object.entries(wrkPatchedIds).some(([k, id]) => k !== oldKey && id === oldDetail.id) || Object.entries(wrkBackups).some(([k, b]) => k !== oldKey && b.targetNodeId === oldDetail.id)
   if (!recordedOldId && (oldIdBoundElsewhere || (oldBackup && !hasReplacedModBlock(currentSys, resolvedPack.id)) || (!oldBackup && (!hasAnyModBlock(currentSys, resolvedPack.id) || hasReplacedModBlock(currentSys, resolvedPack.id) || extractCustomOriginToken(currentSys, resolvedPack.id) !== null)))) {
    throw new Error(`旧节点「${oldKey}」缺少稳定目标 ID 且当前键位节点不含本模组标记`) }
   const cleanedSys = oldBackup ? restoreReplacedModBlock(currentSys, resolvedPack.id, oldBackup.baselineSystem) : stripModProtocolBlock(currentSys, resolvedPack.id)
   if (hasAnyModBlock(cleanedSys, resolvedPack.id) || hasPackModMention(cleanedSys, resolvedPack.id)) throw new Error(`旧节点「${liveOldKey}」仍残留未剥离的替换块`)
   if (cleanedSys !== currentSys) { assertSlotWalWritable(oldKey, oldDetail.id)
    if (oldBackup) wrkBackups[oldKey] = { ...oldBackup, targetNodeId: oldDetail.id }
    wrkPatchedIds[oldKey] = oldDetail.id
    wrkUnresolved[oldKey] = { kind: 'patch', targetNodeId: oldDetail.id, priorSystem: currentSys, writtenSystem: cleanedSys, startedAt: Date.now() }
    commitWorkingRecord(false)
    try {
     await promptPlazaApi.updateNode(liveOldKey, { ...buildSystemUpdatePreconditions(oldDetail), system: cleanedSys, change_summary: `升级模组「${resolvedPack.name}」并释放旧节点接管` }, { silentGlobalFeedback: true })
    } catch (oldPatchErr) { if (isDefinitivePreCommitHttpError(oldPatchErr) && !isHttpNotFound(oldPatchErr)) { clearSlotWalIfTarget(oldKey, oldDetail.id); commitWorkingRecord(false) }
     throw oldPatchErr }
   } else if (wrkUnresolved[oldKey] && (!wrkUnresolved[oldKey].targetNodeId || wrkUnresolved[oldKey].targetNodeId === oldDetail.id) && (wrkUnresolved[oldKey].kind === 'delete' || !hasPatchMutationCommitted(oldDetail, wrkUnresolved[oldKey]))) {
    await fenceNodeVersion(oldDetail, `升级模组「${resolvedPack.name}」收敛旧节点未决围栏`) }
   wrkPatchedKeys.delete(oldKey); delete wrkPatchedIds[oldKey]; delete wrkBackups[oldKey]
   clearSlotWalIfTarget(oldKey, oldDetail.id); commitWorkingRecord(false) } catch { wrkPatchedKeys.add(oldKey); if (recordedOldId) wrkPatchedIds[oldKey] = recordedOldId
   if (initialBackups[oldKey]) wrkBackups[oldKey] = initialBackups[oldKey]
   commitWorkingRecord(false) } }
 if (resolvedPack.cloudSourceId && resolvedPack.id.startsWith('cloud-community-')) void sendSquareEvent(resolvedPack.cloudSourceId, 'apply').catch(() => undefined)
 const finalRecord = buildWorkingSnapshot(false)
 finalRecord.installedAt = new Date().toISOString()
 commitPackRecord(resolvedPack.id, finalRecord)
 return finalRecord }
export const useModHubStore = defineStore('modHub', () => { const installedMap = ref<Record<string, InstalledModRecord>>(readStoredRecords())
 const busyPackIds = ref<Record<string, boolean>>({})
 const reloadAuthoritativeMap = (): Record<string, InstalledModRecord> => { const a = readStoredRecordsStrict(); installedMap.value = a; return a }
 const commitPackRecord = (packId: string, record: InstalledModRecord | undefined): Record<string, InstalledModRecord> => {
  const merged = writeStoredPackRecordStrict(packId, record); installedMap.value = merged; return merged }
 if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') { window.addEventListener('storage', (event: StorageEvent) => {
   if (event.key === storageKeys.modHubInstalled && Object.keys(busyPackIds.value).length === 0) installedMap.value = readStoredRecords() }) }
 const curatedPacks = computed<NarrativeModPack[]>(() => CURATED_MOD_PACKS)
 const installedList = computed<InstalledModRecord[]>(() => Object.values(installedMap.value).sort((a, b) => b.installedAt.localeCompare(a.installedAt)))
 const installedCount = computed(() => Object.keys(installedMap.value).length)
 const isInstalled = (packId: string): boolean => Boolean(installedMap.value[packId])
 const isBusy = (packId: string): boolean => Boolean(busyPackIds.value[packId])
 const setBusy = (packId: string, state: boolean): void => { if (state) busyPackIds.value = { ...busyPackIds.value, [packId]: true }
  else { const next = { ...busyPackIds.value }; delete next[packId]; busyPackIds.value = next } }
 const findForeignDependentPackNames = (targetNodeKey: string, excludePackId: string, targetNodeId?: string): string[] =>
  findForeignDepsInMap(installedMap.value, targetNodeKey, excludePackId, targetNodeId)
 async function syncWithBackendNodes(nodes: PromptNode[]): Promise<void> { if (!nodes.length) return
  try { await withNodeLocks([], async () => { const authoritative = readStoredRecordsStrict()
    let mutated = false
    for (const pack of CURATED_MOD_PACKS) { if (authoritative[pack.id]) continue
     const matchedNodes = nodes.filter(n => hasAnyModBlock(n.system_preview || '', pack.id))
     if (matchedNodes.length > 0) { authoritative[pack.id] = { pack, installedAt: new Date().toISOString(), createdNodeIds: [],
       patchedNodeKeys: matchedNodes.map(n => n.node_key), patchedNodeIds: Object.fromEntries(matchedNodes.map(n => [n.node_key, n.id])), }
      mutated = true } }
    if (mutated) writeStoredRecordsStrict(authoritative)
    installedMap.value = authoritative }) } catch { /* non-blocking initial sync */ } }
 async function installModPack(pack: NarrativeModPack, knownNodes: PromptNode[] = []): Promise<InstalledModRecord> { const requestedPackId = assertValidModId(pack.id)
  if (isBusy(requestedPackId)) throw new Error(`模组「${pack.name}」正在执行操作，请勿并发重复提交`)
  setBusy(requestedPackId, true)
  try { const resolvedPack = pack.cloudSourceId && pack.overrides.every(o => !o.systemContent.trim()) ? await hydrateCloudPackDetail(pack) : pack
   validatePackInvariants(resolvedPack); void knownNodes
   return await withNodeLocks([resolvedPack.id, ...resolvedPack.overrides.map(o => o.nodeKey)], () => runInstallLocked(resolvedPack, {
    reloadAuthoritativeMap, commitPackRecord, getInstalledMap: () => installedMap.value, findForeignDependentPackNames, })) } finally { setBusy(requestedPackId, false) } }
 async function uninstallModPack(packId: string): Promise<void> { const safeId = assertValidModId(packId)
  if (isBusy(safeId)) throw new Error('该模组正在执行操作，请稍候再试')
  setBusy(safeId, true)
  try { await executeModPackUninstall(safeId, { reloadAuthoritativeMap, commitPackRecord }) } finally { setBusy(safeId, false) } }
 async function installFromSourceInput(rawInput: string, knownNodes: PromptNode[] = []): Promise<InstalledModRecord> { const trimmed = rawInput.trim()
  if (!trimmed) throw new Error('请输入 GitHub 仓库地址（如 github:owner/repo）或选择本地模组 JSON 文件')
  if (trimmed.startsWith('{')) { if (new TextEncoder().encode(trimmed).byteLength > MOD_MANIFEST_MAX_BYTES) throw new Error('粘贴的模组 JSON 超过 1MB 安全上限')
   return installModPack(parseAnyModJson(JSON.parse(trimmed) as unknown, '剪贴板 JSON', 'local'), knownNodes) }
  const { originLabel, candidateUrls } = resolveRemoteCandidateUrls(rawInput)
  const spaceTrimmedSource = rawInput.replace(/^ +| +$/g, '')
  try { const res = await promptPlazaApi.fetchRemoteModManifest(spaceTrimmedSource, { silentGlobalFeedback: true })
   if (res?.manifest) return installModPack(parseAnyModJson(res.manifest, originLabel, 'community-unreviewed'), knownNodes)
   throw new Error('后端远程模组接口返回空清单') } catch (proxyErr) { if (!isMissingLegacyRemoteEndpoint(proxyErr)) throw formatBackendError(proxyErr, '拉取远程模组失败') }
  let lastErr = '未能在目标仓库找到 plotpilot-mod.json 清单文件'
  for (const url of candidateUrls) { try { const json = await fetchTrustedBrowserFallbackJson(url)
    if (json === null) { lastErr = `未找到 ${url}`; continue }
    return installModPack(parseAnyModJson(json, originLabel, 'community-unreviewed'), knownNodes) } catch (err) { lastErr = err instanceof Error ? err.message : String(err); break } }
  throw new Error(`拉取远程模组失败：${lastErr}`) }
 async function installFromLocalFile(file: File, knownNodes: PromptNode[] = []): Promise<InstalledModRecord> { if (file.size > MOD_MANIFEST_MAX_BYTES) throw new Error('模组 JSON 文件超过 1MB 安全上限')
  const rawText = await file.text()
  if (new TextEncoder().encode(rawText).byteLength > MOD_MANIFEST_MAX_BYTES) throw new Error('模组 JSON 内容超过 1MB 安全上限')
  return installModPack(parseAnyModJson(JSON.parse(rawText) as unknown, `本机文件 (${file.name})`, 'local'), knownNodes) }
 const exportPackJson = (pack: NarrativeModPack): string => JSON.stringify(createManifestFromPack(pack), null, 2)
 return { installedMap, installedList, installedCount, curatedPacks, busyPackIds, isInstalled, isBusy,
  syncWithBackendNodes, installModPack, uninstallModPack, installFromSourceInput, installFromLocalFile,
  convertOfficialAssetToPack, convertCommunityAssetToPack, hydrateCloudPackDetail, createManifestFromPack, exportPackJson, } })
