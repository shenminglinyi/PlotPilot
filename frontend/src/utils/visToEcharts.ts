/**
 * vis-network to ECharts Graph Converter
 *
 * Converts vis-network data structures to ECharts Graph format.
 * Used for migrating existing components (Cast.vue, CastGraphCompact.vue, KnowledgeTripleGraph.vue)
 * from vis-network to ECharts.
 */

// ============================================================================
// vis-network Types
// ============================================================================

export interface VisNode {
  id: string | number
  label?: string
  title?: string
  color?: string | { background?: string; border?: string }
  size?: number
  shape?: string
  font?: { size?: number; color?: string }
  borderWidth?: number
  margin?: { top?: number; right?: number; bottom?: number; left?: number }
  // Allow any additional properties to be passed through
  [key: string]: any
}

export interface VisEdge {
  id?: string | number
  from: string | number
  to: string | number
  label?: string
  title?: string
  color?: string | { color?: string; opacity?: number }
  width?: number
  arrows?: string | { to?: boolean | { enabled?: boolean } }
  font?: { size?: number; align?: string; color?: string }
  smooth?: boolean
}

// ============================================================================
// ECharts Types
// ============================================================================

export interface EChartsNode {
  id: string
  name: string
  symbolSize?: number
  symbol?: string
  itemStyle?: {
    color?: string
    borderColor?: string
    borderWidth?: number
  }
  label?: {
    show?: boolean
    fontSize?: number
    color?: string
  }
  category?: number
  tooltip?: {
    formatter?: string
  }
}

export interface EChartsLink {
  source: string
  target: string
  label?: {
    show?: boolean
    formatter?: string
    fontSize?: number
  }
  lineStyle?: {
    color?: string
    width?: number
    opacity?: number
  }
  symbol?: string | [string, string]
}

export interface EChartsGraphData {
  nodes: EChartsNode[]
  links: EChartsLink[]
}

// ============================================================================
// Converter Functions
// ============================================================================

/**
 * Convert a single vis-network node to ECharts node format
 */
export function convertNode(visNode: VisNode): EChartsNode {
  const node: EChartsNode = {
    id: String(visNode.id),
    name: visNode.label || String(visNode.id),
  }

  // Convert size to symbolSize (vis default is ~25, ECharts default is ~10)
  if (visNode.size != null) {
    node.symbolSize = visNode.size
  }

  // Convert shape
  if (visNode.shape) {
    const shapeMap: Record<string, string> = {
      box: 'rect',
      circle: 'circle',
      ellipse: 'circle',
      database: 'rect',
      diamond: 'diamond',
      dot: 'circle',
      square: 'rect',
      triangle: 'triangle',
      triangleDown: 'triangle',
      star: 'pin',
    }
    node.symbol = shapeMap[visNode.shape] || 'circle'
  }

  // Convert color
  if (visNode.color) {
    node.itemStyle = node.itemStyle || {}
    if (typeof visNode.color === 'string') {
      node.itemStyle.color = visNode.color
    } else {
      if (visNode.color.background) {
        node.itemStyle.color = visNode.color.background
      }
      if (visNode.color.border) {
        node.itemStyle.borderColor = visNode.color.border
      }
    }
  }

  // Convert border width
  if (visNode.borderWidth != null) {
    node.itemStyle = node.itemStyle || {}
    node.itemStyle.borderWidth = visNode.borderWidth
  }

  // Convert font
  if (visNode.font) {
    node.label = node.label || { show: true }
    if (visNode.font.size != null) {
      node.label.fontSize = visNode.font.size
    }
    if (visNode.font.color) {
      node.label.color = visNode.font.color
    }
  }

  // Convert title (tooltip)
  if (visNode.title) {
    node.tooltip = {
      formatter: visNode.title,
    }
  }

  // Preserve all additional properties (like location_type, importance, description, etc.)
  const standardKeys = ['id', 'label', 'title', 'color', 'size', 'shape', 'font', 'borderWidth', 'margin']
  for (const key in visNode) {
    if (!standardKeys.includes(key) && visNode[key] !== undefined) {
      ;(node as any)[key] = visNode[key]
    }
  }

  // Apply explicit itemStyle if provided
  if (visNode.itemStyle) {
    node.itemStyle = { ...node.itemStyle, ...visNode.itemStyle }
  }

  return node
}

/**
 * Convert a single vis-network edge to ECharts link format
 */
export function convertEdge(visEdge: VisEdge): EChartsLink {
  const link: EChartsLink = {
    source: String(visEdge.from),
    target: String(visEdge.to),
  }

  // Convert label
  if (visEdge.label) {
    link.label = {
      show: true,
      formatter: visEdge.label,
    }

    // Convert font size for edge label
    if (visEdge.font?.size != null) {
      link.label.fontSize = visEdge.font.size
    }
  }

  // Convert color
  if (visEdge.color) {
    link.lineStyle = link.lineStyle || {}
    if (typeof visEdge.color === 'string') {
      link.lineStyle.color = visEdge.color
    } else if (visEdge.color.color) {
      link.lineStyle.color = visEdge.color.color
      if (visEdge.color.opacity != null) {
        link.lineStyle.opacity = visEdge.color.opacity
      }
    }
  }

  // Convert width
  if (visEdge.width != null) {
    link.lineStyle = link.lineStyle || {}
    link.lineStyle.width = visEdge.width
  }

  // Convert arrows (directional edges)
  if (visEdge.arrows) {
    if (visEdge.arrows === 'to' || visEdge.arrows === 'from') {
      link.symbol = visEdge.arrows === 'to' ? ['none', 'arrow'] : ['arrow', 'none']
    } else if (typeof visEdge.arrows === 'object' && visEdge.arrows.to) {
      link.symbol = ['none', 'arrow']
    }
  }

  // Convert title (tooltip) for edge
  if (visEdge.title) {
    // ECharts doesn't have direct edge tooltip formatter in link object
    // Store it in label formatter if no label exists
    if (!link.label) {
      link.label = {
        show: false,
        formatter: visEdge.title,
      }
    }
  }

  return link
}

/**
 * Convert an array of vis-network nodes to ECharts nodes
 */
export function convertNodes(visNodes: VisNode[]): EChartsNode[] {
  return visNodes.map(convertNode)
}

/**
 * Convert an array of vis-network edges to ECharts links
 */
export function convertEdges(visEdges: VisEdge[]): EChartsLink[] {
  return visEdges.map(convertEdge)
}

/**
 * Convert complete vis-network graph data to ECharts graph format
 *
 * @param visNodes - Array of vis-network nodes
 * @param visEdges - Array of vis-network edges
 * @returns ECharts graph data with nodes and links
 */
export function convertGraph(visNodes: VisNode[], visEdges: VisEdge[]): EChartsGraphData {
  return {
    nodes: convertNodes(visNodes),
    links: convertEdges(visEdges),
  }
}

/**
 * Helper function to extract plain arrays from vis-network DataSet
 * (for components that use DataSet wrapper)
 */
export function extractFromDataSet<T>(dataSet: any): T[] {
  if (!dataSet) return []
  if (Array.isArray(dataSet)) return dataSet
  if (typeof dataSet.get === 'function') {
    return dataSet.get()
  }
  return []
}
