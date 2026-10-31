<template>
  <main class="pilot-page">
    <header class="pilot-header">
      <div><h1>人物设定候选</h1><p>官方声明式插件 · 实验功能 · 每次手动运行</p></div>
      <router-link v-if="currentProject" :to="`/book/${currentProject.slug}/workbench`"><n-button>返回工作台</n-button></router-link>
      <router-link v-else to="/"><n-button>返回书架</n-button></router-link>
    </header>
    <n-alert type="info" title="先预览，再决定是否采纳" :bordered="false">
      仅向当前模型发送所选的一章已保存内容及已有角色的姓名、外貌、性格、核心动机。
      最多一次模型请求、输出上限 2048 token、45 秒超时。章节上限 8000 字，较长中文内容还可能触发输入 token 预算。
      候选独立保存；确认采纳只替换预览中的人物字段。来源或人物有任何变更时，都需重新生成。
    </n-alert>
    <n-alert v-if="error" type="error" title="操作未完成" class="pilot-feedback" role="alert">{{ error }}</n-alert>
    <n-alert v-if="feedback" type="info" class="pilot-feedback" aria-live="polite">{{ feedback }}</n-alert>

    <n-card title="1. 选择范围" class="pilot-card" :bordered="false">
      <n-form label-placement="top">
        <div class="pilot-grid">
          <n-form-item label="小说"><n-select v-model:value="projectId" :options="projectOptions" placeholder="选择已有小说" :disabled="busy" /></n-form-item>
          <n-form-item label="官方插件"><n-select v-model:value="pluginId" :options="pluginOptions" :disabled="busy" /></n-form-item>
          <n-form-item label="已保存章节"><n-select v-model:value="chapterId" :options="chapterOptions" placeholder="选择一章" :disabled="busy || !projectId" /></n-form-item>
          <n-form-item label="已有角色"><n-select v-model:value="characterId" :options="characterOptions" placeholder="选择人物" :disabled="busy || !projectId" /></n-form-item>
        </div>
        <p>当前模型：{{ model ? `${model.name} / ${model.model} (${model.protocol})` : '未就绪，请先在工作台配置模型' }}</p>
        <n-button size="small" :disabled="busy" @click="refreshModel">刷新模型配置</n-button>
        <div class="pilot-consent">
          <n-checkbox v-model:checked="consent" :disabled="busy || !chapterId || !characterId || !model">
            我同意本次将「{{ selectedChapter }}」和「{{ selectedCharacter }}」的上述字段发送给当前模型；允许一次模型调用。
          </n-checkbox>
        </div>
        <n-button type="primary" :loading="running" :disabled="!canRun" @click="run">生成候选</n-button>
      </n-form>
    </n-card>

    <n-card v-if="pending" title="待核对的采纳命令" class="pilot-card" :bordered="false">
      <p>命令 {{ pending.command_id }}。结果未明确前，请查询此命令，勿重复提交。</p>
      <n-button :loading="checking" @click="queryPending">查询提交结果</n-button>
      <div v-if="pendingStatus === 'unknown'" class="pilot-consent">
        <p>暂未查到提交结果：可能尚未送达，也可能仍在队列中。可以手动重试原命令；重复到达也只采纳一次。</p>
        <n-checkbox v-model:checked="retryConfirmed" :disabled="busy || checking">我确认使用原候选、原范围和同一个命令 ID 重试本次采纳。</n-checkbox>
        <n-button :disabled="!retryConfirmed || busy || checking" @click="retryPending">使用同一命令重试采纳</n-button>
      </div>
    </n-card>

    <n-card title="2. 已保存候选与差异" class="pilot-card" :bordered="false">
      <template #header-extra><n-button size="small" :disabled="busy || !projectId" :loading="loading" @click="refreshCandidates">刷新列表</n-button></template>
      <n-empty v-if="!candidates.length" description="此小说还没有候选；选择范围并运行后将在这里保留结果。" />
      <div v-for="candidate in candidates" :key="candidate.id" class="pilot-candidate">
        <h2>{{ candidate.snapshot.character.name }} <n-tag size="small" :type="candidate.adopted_command_id ? 'success' : 'default'">{{ candidate.adopted_command_id ? '已采纳' : '待确认' }}</n-tag></h2>
        <p>{{ candidate.snapshot.chapter.title }} · {{ candidate.model.name }} / {{ candidate.model.model }} · 插件 {{ candidate.plugin.version }}</p>
        <small>候选 {{ candidate.id }} · 调用 {{ candidate.usage.calls }} 次 · 输入 {{ candidate.usage.input_tokens }} / 输出 {{ candidate.usage.output_tokens }} token（供应商回报；0 可能表示未提供）</small>
        <div v-for="diff in candidate.diff" :key="diff.field" class="pilot-diff">
          <h3>{{ fieldName(diff.field) }}</h3>
          <div class="pilot-grid"><div><strong>生成前</strong><pre>{{ diff.before || '（空）' }}</pre></div><div><strong>建议替换为</strong><pre>{{ diff.after }}</pre></div></div>
          <blockquote v-for="(evidence, i) in candidate.output.evidence.filter(e => e.field === diff.field)" :key="i">证据：「{{ evidence.quote }}」</blockquote>
        </div>
        <n-collapse>
          <n-collapse-item title="查看完整来源快照与修订" :name="candidate.id">
            <p>章节修订 {{ candidate.snapshot.chapter.revision }}<br />人物修订 {{ candidate.snapshot.character.revision }}</p>
            <pre>{{ candidate.snapshot.chapter.content }}</pre>
          </n-collapse-item>
        </n-collapse>
        <div v-if="!candidate.adopted_command_id" class="pilot-consent">
          <n-checkbox :checked="confirmedId === candidate.id" :disabled="busy || !!pending" @update:checked="checked => confirmedId = checked ? candidate.id : null">我已阅读本候选的完整差异与证据，同意替换这些人物字段。</n-checkbox>
          <n-button type="primary" secondary :loading="adoptingId === candidate.id" :disabled="busy || !!pending || confirmedId !== candidate.id" @click="adopt(candidate)">确认采纳</n-button>
        </div>
      </div>
    </n-card>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NAlert, NButton, NCard, NCheckbox, NCollapse, NCollapseItem, NEmpty, NForm, NFormItem, NSelect, NTag } from 'naive-ui'
import { HttpError } from '@/api/http'
import { pluginPilotApi as api, type Candidate, type CommandResult, type Inputs, type Model, type Project } from '@/api/pluginPilot'

const route = useRoute()
const projects = ref<Project[]>([])
const plugins = ref<{ id: string; name: string }[]>([])
const projectId = ref<string | null>(null)
const pluginId = ref<string | null>(null)
const chapterId = ref<string | null>(null)
const characterId = ref<string | null>(null)
const inputs = ref<Inputs>({ chapters: [], characters: [] })
const model = ref<Model | null>(null)
const consent = ref(false)
const candidates = ref<Candidate[]>([])
const confirmedId = ref<string | null>(null)
const running = ref(false), loading = ref(false), checking = ref(false)
const adoptingId = ref<string | null>(null)
const error = ref(''), feedback = ref('')
const busy = computed(() => running.value || loading.value || !!adoptingId.value)
const pending = ref<{ project_id: string; candidate_id: string; command_id: string; confirm: true } | null>(null)
const pendingStatus = ref(''), retryConfirmed = ref(false)
const pendingKey = 'plotpilot.plugin-pilot.pending-adoption.v1'
const currentProject = computed(() => projects.value.find(p => p.id === projectId.value))
const projectOptions = computed(() => projects.value.map(p => ({ label: p.title, value: p.id })))
const pluginOptions = computed(() => plugins.value.map(p => ({ label: p.name, value: p.id })))
const chapterOptions = computed(() => inputs.value.chapters.map(c => ({ label: `${c.number}. ${c.title}（${c.characters}字）`, value: c.id })))
const characterOptions = computed(() => inputs.value.characters.map(c => ({ label: c.name, value: c.id })))
const selectedChapter = computed(() => inputs.value.chapters.find(c => c.id === chapterId.value)?.title || '未选择')
const selectedCharacter = computed(() => inputs.value.characters.find(c => c.id === characterId.value)?.name || '未选择')
const canRun = computed(() => !busy.value && consent.value && !!model.value && !!projectId.value && !!chapterId.value && !!characterId.value && !!pluginId.value)
const fieldName = (field: string) => ({ appearance: '外貌', personality: '性格', core_motivation: '核心动机' }[field] || field)

function describe(e: unknown): string {
  if (e instanceof HttpError) {
    const detail = (e.body as { detail?: unknown })?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
    return `请求失败（${e.status}），请检查范围、配置或刷新列表。`
  }
  return e instanceof Error ? e.message : '请求未完成，请刷新核对。'
}
function savePending() {
  if (pending.value) localStorage.setItem(pendingKey, JSON.stringify(pending.value))
  else localStorage.removeItem(pendingKey)
}
function handleResult(result: CommandResult) {
  pendingStatus.value = result.status
  retryConfirmed.value = false
  if (result.status === 'committed') feedback.value = '采纳已提交：人物字段已更新，正文未修改。'
  else feedback.value = result.message || '结果尚未确定，请稍后继续查询同一命令。'
  if (['committed', 'conflict', 'failed'].includes(result.status)) {
    pending.value = null
    savePending()
    confirmedId.value = null
  }
}
async function refreshModel() {
  consent.value = false
  model.value = null
  try { model.value = await api.model() } catch (e) { error.value = describe(e) }
}
async function refreshCandidates() {
  if (!projectId.value) return
  const id = projectId.value
  loading.value = true
  try { const rows = await api.candidates(id); if (id === projectId.value) candidates.value = rows }
  catch (e) { error.value = describe(e) } finally { loading.value = false }
}
async function run() {
  if (!canRun.value || !model.value || !projectId.value || !chapterId.value || !characterId.value || !pluginId.value) return
  running.value = true; error.value = ''; feedback.value = '正在生成候选；人物与正文尚未修改。'
  try {
    await api.run({ plugin_id: pluginId.value, project_id: projectId.value, chapter_id: chapterId.value, character_id: characterId.value, model_signature: model.value.signature, consent: true })
    feedback.value = '候选已独立保存，请阅读差异与证据。'
  } catch (e) { error.value = `${describe(e)} 如请求中断，请先刷新候选列表核对，勿盲目重跑。` }
  finally { consent.value = false; running.value = false; await refreshCandidates() }
}
async function adopt(candidate: Candidate) {
  if (pending.value || confirmedId.value !== candidate.id) return
  error.value = ''; feedback.value = ''; adoptingId.value = candidate.id
  pending.value = { project_id: candidate.snapshot.project_id, candidate_id: candidate.id, command_id: crypto.randomUUID(), confirm: true }
  try {
    savePending() // Save before sending so reload/network failure keeps the same ID.
    const result = await api.adopt(candidate.id, { project_id: pending.value.project_id, command_id: pending.value.command_id, confirm: true })
    handleResult(result)
  } catch (e) {
    error.value = describe(e)
    // Always query on a transport/HTTP failure; never create a new command here.
    await queryPending()
  } finally { adoptingId.value = null; await refreshCandidates() }
}
async function queryPending() {
  if (!pending.value) return
  checking.value = true
  try { handleResult(await api.command(pending.value.project_id, pending.value.command_id)); await refreshCandidates() }
  catch (e) { error.value = describe(e) } finally { checking.value = false }
}
async function retryPending() {
  if (!pending.value || pendingStatus.value !== 'unknown' || !retryConfirmed.value || busy.value) return
  const original = { ...pending.value }
  error.value = ''; adoptingId.value = original.candidate_id; retryConfirmed.value = false
  try {
    handleResult(await api.adopt(original.candidate_id, { project_id: original.project_id, command_id: original.command_id, confirm: original.confirm }))
  } catch (e) { error.value = describe(e); await queryPending() }
  finally { adoptingId.value = null; await refreshCandidates() }
}
watch([chapterId, characterId, pluginId], () => { consent.value = false })
watch(projectId, async id => {
  chapterId.value = null; characterId.value = null; consent.value = false; confirmedId.value = null
  inputs.value = { chapters: [], characters: [] }; candidates.value = []; error.value = ''
  if (!id) return
  loading.value = true
  try { const result = await api.inputs(id); if (id === projectId.value) inputs.value = result }
  catch (e) { error.value = describe(e) } finally { loading.value = false }
  await refreshCandidates()
})
onMounted(async () => {
  try {
    const saved = JSON.parse(localStorage.getItem(pendingKey) || 'null')
    if (saved && typeof saved.project_id === 'string' && typeof saved.candidate_id === 'string' && typeof saved.command_id === 'string') pending.value = { ...saved, confirm: true }
    const [books, catalog] = await Promise.all([api.projects(), api.catalog()])
    projects.value = books; plugins.value = catalog.plugins; pluginId.value = catalog.plugins[0]?.id || null
    projectId.value = books.find(p => p.id === route.query.project || p.slug === route.query.project)?.id || books[0]?.id || null
    await refreshModel()
    if (pending.value) await queryPending()
  } catch (e) { error.value = describe(e) }
})
</script>

<style scoped>
.pilot-page { max-width: 1120px; margin: 0 auto; padding: 28px 24px 64px; }
.pilot-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h1 { margin: 0; font-size: 25px; } h2 { font-size: 19px; } h3 { font-size: 15px; }
.pilot-header p, small { opacity: .7; }
.pilot-card, .pilot-feedback { margin-top: 20px; }
.pilot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.pilot-consent { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin: 20px 0; }
.pilot-candidate { padding: 10px 0 24px; border-bottom: 1px solid var(--n-border-color, #8885); }
.pilot-diff { margin: 20px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; line-height: 1.8; margin: 8px 0; padding: 12px; background: #8881; border-radius: 4px; }
blockquote { margin: 12px 0; padding: 8px 12px; border-left: 3px solid #8887; line-height: 1.8; }
@media (max-width: 680px) { .pilot-page { padding: 20px 14px; } .pilot-grid { grid-template-columns: 1fr; gap: 10px; } }
</style>
