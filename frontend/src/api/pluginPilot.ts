import { fetchJson } from './http'

const root = '/api/v1/plugin-pilot'
export type Project = { id: string; slug: string; title: string }
export type Model = { profile_id: string; name: string; model: string; protocol: string; signature: string }
export type Inputs = {
  chapters: { id: string; number: number; title: string; characters: number }[]
  characters: { id: string; name: string }[]
}
export type Candidate = {
  id: string
  plugin: { id: string; version: string; digest: string }
  model: Model
  snapshot: {
    project_id: string
    chapter: { id: string; title: string; content: string; revision: string }
    character: { id: string; name: string; revision: string }
  }
  diff: { field: string; before: string; after: string }[]
  output: { evidence: { field: string; quote: string }[] }
  usage: { input_tokens: number; output_tokens: number; calls: number; input_token_upper_bound: number }
  adopted_command_id?: string | null
}
export type CommandResult = { status: string; command_id: string; candidate_id?: string; message?: string; affected_rows?: number }
const path = (value: string) => encodeURIComponent(value)

export const pluginPilotApi = {
  catalog: () => fetchJson<{ plugins: { id: string; name: string; version: string }[] }>(`${root}/catalog`),
  projects: () => fetchJson<Project[]>(`${root}/projects`),
  model: () => fetchJson<Model>(`${root}/model`),
  inputs: (project: string) => fetchJson<Inputs>(`${root}/projects/${path(project)}/inputs`),
  candidates: (project: string) => fetchJson<Candidate[]>(`${root}/projects/${path(project)}/candidates`),
  run: (body: { plugin_id: string; project_id: string; chapter_id: string; character_id: string; model_signature: string; consent: true }) =>
    fetchJson<Candidate>(`${root}/runs`, { method: 'POST', body, timeoutMs: 60000 }),
  adopt: (candidate: string, body: { project_id: string; command_id: string; confirm: true }) =>
    fetchJson<CommandResult>(`${root}/candidates/${path(candidate)}/adopt`, { method: 'POST', body, timeoutMs: 15000 }),
  command: (project: string, command: string) =>
    fetchJson<CommandResult>(`${root}/projects/${path(project)}/commands/${path(command)}`),
}
