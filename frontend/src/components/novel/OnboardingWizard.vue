<template>
  <n-modal
    v-model:show="visible"
    :mask-closable="false"
    :close-on-esc="false"
    preset="card"
    style="width: 90%; max-width: 640px; max-height: 90vh"
  >
    <template #header>
      <div class="wizard-header">
        <span>新手引导</span>
        <n-button text size="small" @click="handleSkip">
          <template #icon>
            <n-icon size="18"><IconClose /></n-icon>
          </template>
        </n-button>
      </div>
    </template>

    <n-steps :current="currentStep" size="small" class="wizard-steps">
      <n-step title="创建小说" />
      <n-step title="设定世界观" />
      <n-step title="生成大纲" />
      <n-step title="启动自动驾驶" />
    </n-steps>

    <div class="wizard-body">
      <div v-if="currentStep === 1" class="step-panel">
        <div class="step-icon">📖</div>
        <h3 class="step-title">创建你的第一本小说</h3>
        <p class="step-desc">输入书名和故事简介，开启创作之旅</p>
        <n-form ref="formRef" :model="formData" :rules="formRules" label-placement="top" class="step-form">
          <n-form-item label="书名" path="title">
            <n-input v-model:value="formData.title" placeholder="给你的小说起个名字" />
          </n-form-item>
          <n-form-item label="故事简介" path="premise">
            <n-input
              v-model:value="formData.premise"
              type="textarea"
              placeholder="描述你想写的故事…&#10;例如：程序员穿越成状元，用工程思维整顿吏治。"
              :rows="4"
            />
          </n-form-item>
        </n-form>
      </div>

      <div v-else-if="currentStep === 2" class="step-panel">
        <div class="step-icon">🌍</div>
        <h3 class="step-title">设定世界观</h3>
        <p class="step-desc">世界观（Bible）是故事的基石，包含力量体系、社会结构、地理生态等五维框架</p>
        <n-alert type="info" :bordered="false" style="margin-top: 16px">
          完成小说创建后，系统将自动引导你填写世界观设定。你也可以在工作台的「Bible」面板中随时编辑。
        </n-alert>
        <div class="bible-dimensions">
          <div v-for="dim in bibleDimensions" :key="dim.label" class="bible-dim-item">
            <span class="bible-dim-icon">{{ dim.icon }}</span>
            <span class="bible-dim-label">{{ dim.label }}</span>
          </div>
        </div>
      </div>

      <div v-else-if="currentStep === 3" class="step-panel">
        <div class="step-icon">📋</div>
        <h3 class="step-title">生成章节大纲</h3>
        <p class="step-desc">基于世界观和故事简介，AI 一键生成完整的章节规划</p>
        <n-spin :show="generatingOutline" style="margin-top: 16px; width: 100%">
          <div v-if="!outlineGenerated" class="outline-placeholder">
            <n-button
              type="primary"
              :loading="generatingOutline"
              :disabled="!novelCreated"
              @click="handleGenerateOutline"
            >
              一键生成大纲
            </n-button>
            <p v-if="!novelCreated" class="hint-text">请先完成第一步创建小说</p>
          </div>
          <div v-else class="outline-result">
            <n-alert type="success" :bordered="false">大纲生成完成！共规划 {{ outlineChapterCount }} 章</n-alert>
          </div>
        </n-spin>
      </div>

      <div v-else-if="currentStep === 4" class="step-panel">
        <div class="step-icon">🚀</div>
        <h3 class="step-title">启动自动驾驶</h3>
        <p class="step-desc">配置自动驾驶参数，让 AI 持续为你写作章节</p>
        <n-form label-placement="top" class="step-form" style="margin-top: 16px">
          <n-form-item label="起始章节">
            <n-input-number v-model:value="autopilotConfig.fromChapter" :min="1" class="w-full" />
          </n-form-item>
          <n-form-item label="结束章节">
            <n-input-number v-model:value="autopilotConfig.toChapter" :min="1" class="w-full" />
          </n-form-item>
          <n-form-item label="自动保存">
            <n-switch v-model:value="autopilotConfig.autoSave" />
          </n-form-item>
        </n-form>
      </div>
    </div>

    <template #footer>
      <n-space justify="space-between" style="width: 100%">
        <n-button v-if="currentStep > 1" @click="handlePrev">上一步</n-button>
        <div v-else></div>
        <n-space>
          <n-button @click="handleSkip">跳过</n-button>
          <n-button
            v-if="currentStep < 4"
            type="primary"
            :disabled="currentStep === 1 && !step1Valid"
            @click="handleNext"
          >
            下一步
          </n-button>
          <n-button
            v-else
            type="primary"
            @click="handleComplete"
          >
            完成
          </n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { h, ref, computed, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { novelApi } from '@/api/novel'
import { workflowApi } from '@/api/workflow'

const IconClose = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z' }))

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'complete', novelId: string): void
  (e: 'skip'): void
}>()

const message = useMessage()

const visible = computed({
  get: () => props.show,
  set: (v: boolean) => emit('update:show', v),
})

const currentStep = ref(1)

const formData = ref({
  title: '',
  premise: '',
})

const formRules = {
  title: { required: true, message: '请输入书名', trigger: 'blur' },
  premise: { required: true, message: '请输入故事简介', trigger: 'blur' },
}

const step1Valid = computed(() => formData.value.title.trim() !== '' && formData.value.premise.trim() !== '')

const novelCreated = ref(false)
const createdNovelId = ref('')

const generatingOutline = ref(false)
const outlineGenerated = ref(false)
const outlineChapterCount = ref(0)

const autopilotConfig = ref({
  fromChapter: 1,
  toChapter: 10,
  autoSave: true,
})

const bibleDimensions = [
  { icon: '⚡', label: '核心法则' },
  { icon: '🏔️', label: '地理生态' },
  { icon: '🏛️', label: '社会结构' },
  { icon: '📜', label: '历史文化' },
  { icon: '🎭', label: '沉浸细节' },
]

const handleNext = async () => {
  if (currentStep.value === 1) {
    if (!step1Valid.value) {
      message.warning('请填写书名和故事简介')
      return
    }
    await createNovel()
    if (!novelCreated.value) return
  }
  if (currentStep.value < 4) {
    currentStep.value++
  }
}

const handlePrev = () => {
  if (currentStep.value > 1) {
    currentStep.value--
  }
}

const createNovel = async () => {
  try {
    const novelId = `novel-${Date.now()}`
    const result = await novelApi.createNovel({
      novel_id: novelId,
      title: formData.value.title.trim(),
      author: '作者',
      target_chapters: 100,
    })
    if (formData.value.premise.trim()) {
      await novelApi.updateNovel(result.id, {
        premise: formData.value.premise.trim(),
      })
    }
    createdNovelId.value = result.id
    novelCreated.value = true
    autopilotConfig.value.toChapter = Math.min(10, result.target_chapters || 100)
    message.success('小说创建成功')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '创建失败')
  }
}

const handleGenerateOutline = async () => {
  if (!createdNovelId.value) return
  generatingOutline.value = true
  try {
    const result = await workflowApi.planNovel(createdNovelId.value, 'initial')
    outlineChapterCount.value = (result as any).chapters_planned || 0
    outlineGenerated.value = true
    message.success('大纲生成完成')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '大纲生成失败')
  } finally {
    generatingOutline.value = false
  }
}

const handleSkip = () => {
  localStorage.setItem('plotpilot_onboarding_completed', 'true')
  emit('skip')
  emit('update:show', false)
}

const handleComplete = () => {
  localStorage.setItem('plotpilot_onboarding_completed', 'true')
  emit('complete', createdNovelId.value)
  emit('update:show', false)
}

watch(() => props.show, (val) => {
  if (val) {
    currentStep.value = 1
    formData.value = { title: '', premise: '' }
    novelCreated.value = false
    createdNovelId.value = ''
    generatingOutline.value = false
    outlineGenerated.value = false
    outlineChapterCount.value = 0
    autopilotConfig.value = { fromChapter: 1, toChapter: 10, autoSave: true }
  }
})
</script>

<style scoped>
.wizard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.wizard-steps {
  margin-bottom: 24px;
}

.wizard-body {
  min-height: 260px;
}

.step-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
}

.step-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.step-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
}

.step-desc {
  color: #666;
  line-height: 1.6;
  margin: 0 0 8px;
  text-align: center;
  max-width: 420px;
}

.step-form {
  width: 100%;
  margin-top: 16px;
}

.bible-dimensions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  justify-content: center;
}

.bible-dim-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--app-surface-subtle, rgba(79, 70, 229, 0.04));
  border-radius: 20px;
  font-size: 13px;
}

.bible-dim-icon {
  font-size: 16px;
}

.bible-dim-label {
  font-weight: 500;
}

.outline-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.hint-text {
  font-size: 13px;
  color: #999;
  margin: 0;
}

.outline-result {
  width: 100%;
}

.w-full {
  width: 100%;
}
</style>
