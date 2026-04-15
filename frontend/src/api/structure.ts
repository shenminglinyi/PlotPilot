/**
 * 故事结构 API
 */

import { apiClient } from './config'

export type NodeType = 'part' | 'volume' | 'act' | 'chapter'

export interface StoryNode {
  id: string
  novel_id: string
  parent_id: string | null
  node_type: NodeType
  number: number
  title: string
  description?: string
  order_index: number
  chapter_start?: number
  chapter_end?: number
  chapter_count: number
  metadata: Record<string, any>
  created_at: string
  updated_at: string
  level: number
  icon: string
  display_name: string
  word_count?: number
  status?: string
  children?: StoryNode[]
}

export interface StoryTree {
  novel_id: string
  tree: StoryNode[] | { nodes: StoryNode[] }
}

export interface CreateNodeRequest {
  node_type: NodeType
  number: number
  title: string
  parent_id?: string
  description?: string
  order_index?: number
}

export interface UpdateNodeRequest {
  title?: string
  description?: string
  number?: number
}

export const structureApi = {
  /**
   * 获取小说的完整结构树
   */
  getTree: (novelId: string) =>
    apiClient.get<StoryTree>(`/novels/${novelId}/structure`),

  /**
   * 获取子节点（用于渐进式加载）
   */
  getChildren: (novelId: string, parentId?: string) =>
    apiClient.get<{ parent_id: string | null; children: StoryNode[] }>(
      `/novels/${novelId}/structure/children`,
      { params: { parent_id: parentId } }
    ),

  /**
   * 创建节点
   */
  createNode: (novelId: string, data: CreateNodeRequest) =>
    apiClient.post<{ success: boolean; node: StoryNode }>(
      `/novels/${novelId}/structure/nodes`,
      data
    ),

  /**
   * 更新节点
   */
  updateNode: (novelId: string, nodeId: string, data: UpdateNodeRequest) =>
    apiClient.put<{ success: boolean; node: StoryNode }>(
      `/novels/${novelId}/structure/nodes/${nodeId}`,
      data
    ),

  /**
   * 删除节点
   */
  deleteNode: (novelId: string, nodeId: string) =>
    apiClient.delete<{ success: boolean }>(
      `/novels/${novelId}/structure/nodes/${nodeId}`
    ),

  /**
   * 重新排序节点
   */
  reorderNodes: (novelId: string, nodeIds: string[]) =>
    apiClient.post<{ success: boolean; nodes: StoryNode[] }>(
      `/novels/${novelId}/structure/reorder`,
      { node_ids: nodeIds }
    ),

  /**
   * 更新章节范围
   */
  updateChapterRanges: (novelId: string) =>
    apiClient.post<{ success: boolean }>(
      `/novels/${novelId}/structure/update-ranges`
    )
}
