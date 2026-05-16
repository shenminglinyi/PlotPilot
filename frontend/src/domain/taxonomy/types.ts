/**
 * 通用题材 / 分区知识树（platform-agnostic）。
 * 与 shared/taxonomy/*.json 的 schema_kind=plotpilot.taxonomy_bundle 对齐。
 */

export interface LocalizedLabels {
  [locale: string]: string
}

export type TaxonomyFacets = Record<string, string>

export interface TaxonomyNode {
  id: string
  labels: LocalizedLabels
  facets?: TaxonomyFacets
  children?: TaxonomyNode[]
}

export interface TaxonomyBundleMeta {
  schema_kind: string
  schema_version: number
  id: string
  locale: string
  domain: string
  title?: string
  description?: string
  facet_keys_semantics?: Record<string, string>
}

export interface TaxonomyBundle extends TaxonomyBundleMeta {
  roots: TaxonomyNode[]
}

export const CN_LOCALE = 'zh-CN'

export function pickLocaleLabel(node: TaxonomyNode, locale = CN_LOCALE): string {
  const L = node.labels || {}
  return L[locale] || L[CN_LOCALE] || L['zh'] || Object.values(L)[0] || node.id
}
