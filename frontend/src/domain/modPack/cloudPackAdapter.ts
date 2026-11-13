import {
  fetchSquareAssetDetail,
  fetchSquareCommunityDetail,
  type SquareAsset,
  type SquareCommunityAsset,
} from '@/api/cloudSquare'
import {
  SAFE_NODE_KEY_RE,
  inferRoleFromZone,
  sanitizeModIdAtom,
  stripModDelimiterComments,
} from '@/domain/modPack/modProtocol'
import type {
  ModNodeOverride,
  NarrativeModPack,
  PlotPilotModManifest,
} from '@/domain/modPack/types'

export function convertOfficialAssetToPack(asset: SquareAsset): NarrativeModPack {
  const role = inferRoleFromZone(asset.zone)
  const rawSlot = (asset.slot_key || '').trim()
  const safeAssetAtom = sanitizeModIdAtom(asset.id, 'official')
  const targetSlot =
    rawSlot && SAFE_NODE_KEY_RE.test(rawSlot) && !rawSlot.includes('..') ? rawSlot : ''
  const bodyText = stripModDelimiterComments(
    (asset.template_text || asset.sample_excerpt || asset.summary || '').trim(),
  )
  const applyCount = asset.metrics?.apply_count ?? 0
  const usageLabel = asset.metrics?.cold_start ? '云端书元 · 新上架' : `应用 ${applyCount}`

  const nodeKey = targetSlot || `cloud-seed-${safeAssetAtom}`
  const override: ModNodeOverride = {
    nodeKey,
    nodeLabel: asset.zone_label ? `${asset.zone_label} · ${asset.title}` : asset.title,
    mode: 'standalone_node',
    systemContent: bodyText ? `### 云端书元设定（${asset.title}）\n${bodyText}` : '',
    userTemplate:
      asset.variables && asset.variables.length > 0
        ? asset.variables.map(v => `{${v.key}}`).join('\n')
        : '{context}\n\n{outline}',
    backendCategory: 'planning',
  }

  return {
    id: `cloud-official-${safeAssetAtom}`,
    name: asset.title,
    glyph: asset.title.trim().charAt(0) || '书',
    author: 'PlotPilot 云端书元库',
    repoOrOrigin: 'plotpilot.xyz · 官方书元',
    trustLevel: 'cloud-verified',
    roleCategory: role.category,
    roleLabel: asset.zone_label || role.label,
    summary: asset.summary || '来自 plotpilot.xyz 官方书元库的开局与结构模板。',
    readmeSections: [
      {
        heading: '书元定位与作用',
        body:
          asset.summary ||
          '提供经过拆解的题材切入点与冲突发动机，装入本地后可在规划或创作工作流中直接调用。',
      },
      ...(asset.sample_excerpt
        ? [{ heading: '样章与设定摘录', body: asset.sample_excerpt }]
        : []),
    ],
    version: asset.version ? `v${asset.version.replace(/^v/i, '')}` : 'v1.0.0',
    license: 'PlotPilot Cloud',
    updatedAt: '云端实时同步',
    usageLabel,
    replacesBuiltin: Boolean(targetSlot),
    overrides: [override],
    tags: [...(asset.genre_tags ?? []), ...(asset.hook_tags ?? [])].slice(0, 5),
    cloudSourceId: asset.id,
  }
}

export function convertCommunityAssetToPack(item: SquareCommunityAsset): NarrativeModPack {
  const inner = item.asset
  const safeItemAtom = sanitizeModIdAtom(item.id, 'community')
  const title = (inner?.title || item.title || '社区共享模组').trim()
  const summary = (
    inner?.summary ||
    item.summary ||
    item.safe_sample ||
    '来自 plotpilot.xyz 社区作者分享的创作模板。'
  ).trim()
  const authorName = item.author?.pen_name || item.author?.display_name || '匿名作者'
  const role = inferRoleFromZone(inner?.zone)
  const bodyText = stripModDelimiterComments(
    (inner?.template_text || item.safe_sample || inner?.sample_excerpt || summary).trim(),
  )

  const trials = item.counters?.trial ?? 0
  const likes = item.counters?.like ?? item.counters?.view ?? 0

  return {
    id: `cloud-community-${safeItemAtom}`,
    name: title,
    glyph: title.charAt(0) || '社',
    author: authorName,
    repoOrOrigin: 'plotpilot.xyz · 社区共享',
    trustLevel: item.review_status === 'approved' ? 'cloud-verified' : 'community-unreviewed',
    roleCategory: role.category,
    roleLabel: inner?.zone_label || '社区共享模板',
    summary,
    readmeSections: [
      { heading: '作者说明', body: summary },
      ...(item.safe_sample ? [{ heading: '效果样例', body: item.safe_sample }] : []),
      ...(item.ai_disclosure ? [{ heading: '创作披露', body: item.ai_disclosure }] : []),
    ],
    version: inner?.version ? `v${inner.version.replace(/^v/i, '')}` : 'v1.0.0',
    license: 'Community Share',
    updatedAt: item.published_at
      ? new Date(item.published_at * 1000).toISOString().slice(0, 10)
      : '社区同步',
    usageLabel: trials > 0 ? `试用 ${trials}` : `热度 ${likes}`,
    replacesBuiltin: false,
    overrides: [
      {
        nodeKey: `cloud-comm-${safeItemAtom}`,
        nodeLabel: `${title}（${authorName}）`,
        mode: 'standalone_node',
        systemContent: `### 社区模组：${title}\n${bodyText}`,
        userTemplate: '{context}\n\n{outline}',
        backendCategory: 'creative',
      },
    ],
    tags: [...(inner?.genre_tags ?? []), ...(inner?.hook_tags ?? [])].slice(0, 5),
    cloudSourceId: item.id,
  }
}

export async function hydrateCloudPackDetail(pack: NarrativeModPack): Promise<NarrativeModPack> {
  if (!pack.cloudSourceId) return pack
  try {
    if (pack.id.startsWith('cloud-official-')) {
      const full = await fetchSquareAssetDetail(pack.cloudSourceId)
      if (full) return convertOfficialAssetToPack(full)
    } else if (pack.id.startsWith('cloud-community-')) {
      const full = await fetchSquareCommunityDetail(pack.cloudSourceId)
      if (full) return convertCommunityAssetToPack(full)
    }
  } catch {
    // 网络波动使用摘要兜底
  }
  const fallbackOverrides = pack.overrides.map(o => ({
    ...o,
    systemContent: stripModDelimiterComments(
      o.systemContent.trim() || `### ${pack.name}\n${pack.summary}`,
    ),
  }))
  return { ...pack, overrides: fallbackOverrides }
}

export function createManifestFromPack(pack: NarrativeModPack): PlotPilotModManifest {
  return {
    schema: 'plotpilot-mod/v1',
    exportedAt: new Date().toISOString(),
    pack,
  }
}
