import raw from './builtin_cn_v1.bundle.json'
import type { TaxonomyBundle, TaxonomyNode } from './types'
import { CN_LOCALE, pickLocaleLabel } from './types'

/** 由 `npm run sync:taxonomy` 从 shared/taxonomy/builtin_cn_v1.yaml 生成；勿手改。 */
export const BUILTIN_CN_MARKET_V1 = raw as TaxonomyBundle

export function marketMajorThemeGenre(root: TaxonomyNode, leaf: TaxonomyNode, locale = CN_LOCALE): string {
  return `${pickLocaleLabel(root, locale)} / ${pickLocaleLabel(leaf, locale)}`
}

/** 世界观正文：取自父节点 facets.world_tone（子节点可后续扩展同名 facet 覆盖） */
export function worldToneForSelection(root: TaxonomyNode): string {
  const w = root.facets?.world_tone?.trim()
  return w || ''
}

export function themeAgentKeyForSelection(root: TaxonomyNode): string {
  return (root.facets?.theme_agent_key || '').trim()
}

export interface FlatSearchHit {
  root: TaxonomyNode
  scoreAid: string
}

export function flattenRootsForSearch(roots: TaxonomyNode[]): FlatSearchHit[] {
  const out: FlatSearchHit[] = []
  for (const root of roots) {
    const major = pickLocaleLabel(root)
    const blob = `${major} ${root.facets?.search_blob || ''} ${root.facets?.market_track || ''}`
    const childLabels =
      root.children?.map((c) => pickLocaleLabel(c)).join(' ') || ''
    out.push({ root, scoreAid: `${blob} ${childLabels}`.toLowerCase() })
  }
  return out
}
