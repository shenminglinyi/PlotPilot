import raw from './builtin_cn_v1.bundle.json'
import type { TaxonomyBundle, TaxonomyNode, TaxonomyWritingProfile } from './types'
import { CN_LOCALE, pickLocaleLabel } from './types'

/** 由 `npm run sync:taxonomy` 从 shared/taxonomy/builtin_cn_v1.yaml 生成；勿手改。 */
export const BUILTIN_CN_MARKET_V1 = raw as TaxonomyBundle

export function marketMajorThemeGenre(root: TaxonomyNode, leaf: TaxonomyNode, locale = CN_LOCALE): string {
  return `${pickLocaleLabel(root, locale)} / ${pickLocaleLabel(leaf, locale)}`
}

function facetTextForSelection(root: TaxonomyNode, leaf: TaxonomyNode | undefined, key: string): string {
  const raw = leaf?.facets?.[key] ?? root.facets?.[key]
  return typeof raw === 'string' ? raw.trim() : ''
}

/** 世界观正文：优先取子主题 facets.world_tone，否则回退父级。 */
export function worldToneForSelection(root: TaxonomyNode, leaf?: TaxonomyNode): string {
  return facetTextForSelection(root, leaf, 'world_tone')
}

function writingProfileFacet(root: TaxonomyNode, leaf: TaxonomyNode | undefined): TaxonomyWritingProfile {
  const rootProfile = root.facets?.writing_profile
  const leafProfile = leaf?.facets?.writing_profile
  const base = rootProfile && typeof rootProfile === 'object' ? (rootProfile as TaxonomyWritingProfile) : {}
  const override = leafProfile && typeof leafProfile === 'object' ? (leafProfile as TaxonomyWritingProfile) : {}
  return { ...base, ...override }
}

export function writingProfileForSelection(root: TaxonomyNode, leaf?: TaxonomyNode): TaxonomyWritingProfile {
  return writingProfileFacet(root, leaf)
}

export function themeAgentKeyForSelection(root: TaxonomyNode): string {
  return facetTextForSelection(root, undefined, 'theme_agent_key')
}

export interface FlatSearchHit {
  root: TaxonomyNode
  scoreAid: string
}

export function flattenRootsForSearch(roots: TaxonomyNode[]): FlatSearchHit[] {
  const out: FlatSearchHit[] = []
  for (const root of roots) {
    const major = pickLocaleLabel(root)
    const profile = writingProfileFacet(root, undefined)
    const blob = `${major} ${facetTextForSelection(root, undefined, 'search_blob')} ${facetTextForSelection(root, undefined, 'market_track')} ${profile.story_structure || ''} ${profile.pacing_control || ''} ${profile.writing_style || ''} ${profile.special_requirements || ''}`
    const childLabels =
      root.children?.map((c) => pickLocaleLabel(c)).join(' ') || ''
    out.push({ root, scoreAid: `${blob} ${childLabels}`.toLowerCase() })
  }
  return out
}
