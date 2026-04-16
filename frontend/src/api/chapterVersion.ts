import { apiClient } from './config'

export interface VersionItem {
  version_id: string
  chapter_id: string
  novel_id: string
  chapter_number: number
  summary: string
  created_at: string
}

export interface VersionListResponse {
  versions: VersionItem[]
}

export interface DiffResponse {
  v1_id: string
  v2_id: string
  additions: string[]
  deletions: string[]
}

export interface RollbackResponse {
  snapshot_version_id: string
  restored_version_id: string
}

export const chapterVersionApi = {
  listVersions: (novelId: string, chapterNumber: number) =>
    apiClient.get<VersionListResponse>(
      `/novels/${novelId}/chapters/${chapterNumber}/versions`,
    ) as Promise<VersionListResponse>,

  diff: (novelId: string, chapterNumber: number, v1: string, v2: string) =>
    apiClient.get<DiffResponse>(
      `/novels/${novelId}/chapters/${chapterNumber}/diff`,
      { params: { v1, v2 } },
    ) as Promise<DiffResponse>,

  rollback: (novelId: string, chapterNumber: number, versionId: string) =>
    apiClient.post<RollbackResponse>(
      `/novels/${novelId}/chapters/${chapterNumber}/rollback`,
      { version_id: versionId },
    ) as Promise<RollbackResponse>,
}
