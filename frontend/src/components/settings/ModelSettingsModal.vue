<template>
  <n-modal v-model:show="visible" preset="card" title="核心引擎配置 (Model Matrix)" style="width: 700px">
    <n-form :model="formData" label-placement="top">
      
      <div class="mode-switch mb-4">
        <n-switch v-model:value="isUnifiedMode" size="large">
          <template #checked>统一端点配置</template>
          <template #unchecked>独立端点配置</template>
        </n-switch>
        <n-text depth="3" class="text-xs ml-2">
          {{ isUnifiedMode ? '使用同一个 API Key 驱动多个模型' : '为各模型分别配置不同的服务商和 Key' }}
        </n-text>
      </div>

      <!-- 统一端点配置区 -->
      <template v-if="isUnifiedMode">
        <n-card size="small" class="mb-4" title="🌐 全局服务端点">
          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.default_model_provider" @update:value="syncProviders">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.default_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.default_model_base_url" placeholder="如 https://api.deepseek.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('default')" :loading="verifyingDefault" class="mb-4">
            🔗 测试端点并获取模型
          </n-button>
        </n-card>

        <!-- 统一模式下的模型分配 -->
        <n-card size="small" class="mb-4" title="🎯 模型任务分配">
          <n-form-item label="✨ 创作主力模型 (Default Model)">
            <n-space vertical>
              <n-select v-model:value="formData.default_model" :options="paged('default', defaultModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(defaultModelOptions) > 1"
                :page="pages.default"
                @update:page="(p: number) => (pages.default = p)"
                :page-count="pageCount(defaultModelOptions)"
                size="small"
              />
            </n-space>
            <template #feedback>用于正文连写与复杂逻辑推理，建议选择智商最高的模型</template>
          </n-form-item>

          <n-form-item label="⚡ 分析经济模型 (Cheap Model)">
            <n-space vertical>
              <n-select v-model:value="formData.cheap_model" :options="paged('cheap', cheapModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(cheapModelOptions) > 1"
                :page="pages.cheap"
                @update:page="(p: number) => (pages.cheap = p)"
                :page-count="pageCount(cheapModelOptions)"
                size="small"
              />
            </n-space>
            <template #feedback>用于后台数据提取、打分与摘要，建议选择速度最快、最便宜的模型</template>
          </n-form-item>

          <n-form-item label="🧠 知识图谱模型 (Knowledge Model)">
            <n-space vertical>
              <n-select v-model:value="formData.knowledge_model" :options="paged('knowledge', knowledgeModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(knowledgeModelOptions) > 1"
                :page="pages.knowledge"
                @update:page="(p: number) => (pages.knowledge = p)"
                :page-count="pageCount(knowledgeModelOptions)"
                size="small"
              />
            </n-space>
            <template #feedback>专门用于从设定中提取复杂的知识图谱关系，建议选择逻辑推理能力较强的模型</template>
          </n-form-item>

          <n-form-item label="🔍 深度研究模型 (Research Model)">
            <n-space vertical>
              <n-select v-model:value="formData.research_model" :options="paged('research', researchModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(researchModelOptions) > 1"
                :page="pages.research"
                @update:page="(p: number) => (pages.research = p)"
                :page-count="pageCount(researchModelOptions)"
                size="small"
              />
            </n-space>
            <template #feedback>专门负责考据资料、提取关键词，建议选择速度较快的模型</template>
          </n-form-item>
        </n-card>
        <!-- 深度研究模型配置区 -->
        <n-card size="small" class="mb-4" title="🔍 深度研究模型 (Research Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">负责考据资料、提取关键词、分析创意</n-text>
          </template>

          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.research_model_provider" @update:value="() => formData.research_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.research_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.research_model_base_url" placeholder="如 https://api.openai.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('research')" :loading="verifyingResearch" class="mb-4">
            🔗 测试研究端点并获取模型
          </n-button>

          <n-form-item label="选择研究模型">
            <n-space vertical>
              <n-select v-model:value="formData.research_model" :options="paged('research', researchModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(researchModelOptions) > 1"
                :page="pages.research"
                @update:page="(p: number) => (pages.research = p)"
                :page-count="pageCount(researchModelOptions)"
                size="small"
              />
            </n-space>
          </n-form-item>
        </n-card>
      </template>

      <!-- 独立端点配置区 (原逻辑) -->
      <template v-else>
        <!-- 创作主力模型配置区 -->
        <n-card size="small" class="mb-4" title="✨ 创作主力模型 (Default Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">用于正文连写与复杂逻辑推理</n-text>
          </template>
          
          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.default_model_provider" @update:value="() => formData.default_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.default_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.default_model_base_url" placeholder="如 https://api.deepseek.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('default')" :loading="verifyingDefault" class="mb-4">
            🔗 测试主力端点并获取模型
          </n-button>

          <n-form-item label="选择主力模型">
            <n-space vertical>
              <n-select v-model:value="formData.default_model" :options="paged('default', defaultModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(defaultModelOptions) > 1"
                :page="pages.default"
                @update:page="(p: number) => (pages.default = p)"
                :page-count="pageCount(defaultModelOptions)"
                size="small"
              />
            </n-space>
          </n-form-item>
        </n-card>

        <!-- 分析经济模型配置区 -->
        <n-card size="small" class="mb-4" title="⚡ 分析经济模型 (Cheap Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">用于后台数据提取、打分与摘要</n-text>
          </template>
          
          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.cheap_model_provider" @update:value="() => formData.cheap_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.cheap_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.cheap_model_base_url" placeholder="如 https://api.openai.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('cheap')" :loading="verifyingCheap" class="mb-4">
            🔗 测试经济端点并获取模型
          </n-button>

          <n-form-item label="选择经济模型">
            <n-space vertical>
              <n-select v-model:value="formData.cheap_model" :options="paged('cheap', cheapModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(cheapModelOptions) > 1"
                :page="pages.cheap"
                @update:page="(p: number) => (pages.cheap = p)"
                :page-count="pageCount(cheapModelOptions)"
                size="small"
              />
            </n-space>
          </n-form-item>
        </n-card>

        <!-- 知识图谱模型配置区 -->
        <n-card size="small" class="mb-4" title="🧠 知识图谱模型 (Knowledge Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">专门用于复杂设定逻辑推理和关系提取</n-text>
          </template>

          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.knowledge_model_provider" @update:value="() => formData.knowledge_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.knowledge_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.knowledge_model_base_url" placeholder="如 https://api.openai.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('knowledge')" :loading="verifyingKnowledge" class="mb-4">
            🔗 测试知识端点并获取模型
          </n-button>

          <n-form-item label="选择知识图谱模型">
            <n-space vertical>
              <n-select v-model:value="formData.knowledge_model" :options="paged('knowledge', knowledgeModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(knowledgeModelOptions) > 1"
                :page="pages.knowledge"
                @update:page="(p: number) => (pages.knowledge = p)"
                :page-count="pageCount(knowledgeModelOptions)"
                size="small"
              />
            </n-space>
          </n-form-item>
        </n-card>

        <n-card size="small" class="mb-4" title="🔍 深度研究模型 (Research Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">负责考据资料、提取关键词、分析创意</n-text>
          </template>

          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.research_model_provider" @update:value="() => formData.research_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.research_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.research_model_base_url" placeholder="如 https://api.openai.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('research')" :loading="verifyingResearch" class="mb-4">
            🔗 测试研究端点并获取模型
          </n-button>

          <n-form-item label="选择研究模型">
            <n-space vertical>
              <n-select v-model:value="formData.research_model" :options="paged('research', researchModelOptions)" tag filterable />
              <n-pagination
                v-if="pageCount(researchModelOptions) > 1"
                :page="pages.research"
                @update:page="(p: number) => (pages.research = p)"
                :page-count="pageCount(researchModelOptions)"
                size="small"
              />
            </n-space>
          </n-form-item>
        </n-card>

        <n-collapse class="mb-4">
          <n-collapse-item title="🗳️ 评审委员会 (Review Committee)" name="review">
            <n-card size="small" class="mb-4" title="🧾 事实审查官模型 (Fact Review)">
              <n-form-item label="服务商 (Provider)">
                <n-radio-group v-model:value="formData.fact_review_model_provider" @update:value="() => formData.fact_review_model = ''">
                  <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
                  <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
                </n-radio-group>
              </n-form-item>

              <n-form-item label="API Key">
                <n-input v-model:value="formData.fact_review_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
              </n-form-item>

              <n-form-item label="Base URL (留空则使用官方地址)">
                <n-input v-model:value="formData.fact_review_model_base_url" placeholder="如 https://api.openai.com/v1" />
              </n-form-item>

              <n-button type="info" dashed block @click="handleVerify('fact_review')" :loading="verifyingFactReview" class="mb-4">
                🔗 获取模型列表
              </n-button>

              <n-form-item label="选择模型">
                <n-space vertical>
                  <n-select v-model:value="formData.fact_review_model" :options="paged('fact_review', factReviewModelOptions)" tag filterable />
                  <n-pagination
                    v-if="pageCount(factReviewModelOptions) > 1"
                    :page="pages.fact_review"
                    @update:page="(p: number) => (pages.fact_review = p)"
                    :page-count="pageCount(factReviewModelOptions)"
                    size="small"
                  />
                </n-space>
              </n-form-item>
            </n-card>

            <n-card size="small" class="mb-4" title="🎭 题材审查官模型 (Genre Review)">
              <n-form-item label="服务商 (Provider)">
                <n-radio-group v-model:value="formData.genre_review_model_provider" @update:value="() => formData.genre_review_model = ''">
                  <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
                  <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
                </n-radio-group>
              </n-form-item>

              <n-form-item label="API Key">
                <n-input v-model:value="formData.genre_review_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
              </n-form-item>

              <n-form-item label="Base URL (留空则使用官方地址)">
                <n-input v-model:value="formData.genre_review_model_base_url" placeholder="如 https://api.openai.com/v1" />
              </n-form-item>

              <n-button type="info" dashed block @click="handleVerify('genre_review')" :loading="verifyingGenreReview" class="mb-4">
                🔗 获取模型列表
              </n-button>

              <n-form-item label="选择模型">
                <n-space vertical>
                  <n-select v-model:value="formData.genre_review_model" :options="paged('genre_review', genreReviewModelOptions)" tag filterable />
                  <n-pagination
                    v-if="pageCount(genreReviewModelOptions) > 1"
                    :page="pages.genre_review"
                    @update:page="(p: number) => (pages.genre_review = p)"
                    :page-count="pageCount(genreReviewModelOptions)"
                    size="small"
                  />
                </n-space>
              </n-form-item>
            </n-card>

            <n-card size="small" class="mb-4" title="📖 读者体验官模型 (Reader Review)">
              <n-form-item label="服务商 (Provider)">
                <n-radio-group v-model:value="formData.reader_review_model_provider" @update:value="() => formData.reader_review_model = ''">
                  <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
                  <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
                </n-radio-group>
              </n-form-item>

              <n-form-item label="API Key">
                <n-input v-model:value="formData.reader_review_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
              </n-form-item>

              <n-form-item label="Base URL (留空则使用官方地址)">
                <n-input v-model:value="formData.reader_review_model_base_url" placeholder="如 https://api.openai.com/v1" />
              </n-form-item>

              <n-button type="info" dashed block @click="handleVerify('reader_review')" :loading="verifyingReaderReview" class="mb-4">
                🔗 获取模型列表
              </n-button>

              <n-form-item label="选择模型">
                <n-space vertical>
                  <n-select v-model:value="formData.reader_review_model" :options="paged('reader_review', readerReviewModelOptions)" tag filterable />
                  <n-pagination
                    v-if="pageCount(readerReviewModelOptions) > 1"
                    :page="pages.reader_review"
                    @update:page="(p: number) => (pages.reader_review = p)"
                    :page-count="pageCount(readerReviewModelOptions)"
                    size="small"
                  />
                </n-space>
              </n-form-item>
            </n-card>
          </n-collapse-item>
        </n-collapse>
      </template>

      <n-space justify="end" class="mt-4">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" @click="handleSave" :loading="saving">保存配置</n-button>
      </n-space>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { getLLMConfig, saveLLMConfig, verifyAndFetchModels, fetchModelsByRole, type LLMConfig } from '../../api/system'

const visible = ref(false)
const message = useMessage()
const verifyingDefault = ref(false)
const verifyingCheap = ref(false)
const verifyingKnowledge = ref(false)
const verifyingResearch = ref(false)
const verifyingFactReview = ref(false)
const verifyingGenreReview = ref(false)
const verifyingReaderReview = ref(false)
const saving = ref(false)
const isUnifiedMode = ref(true)

const formData = ref<LLMConfig>({
  provider: 'openai',
  default_model_provider: 'openai',
  default_model_api_key: '',
  default_model_base_url: '',
  default_model: '',
  cheap_model_provider: 'openai',
  cheap_model_api_key: '',
  cheap_model_base_url: '',
  cheap_model: '',
  knowledge_model_provider: 'openai',
  knowledge_model_api_key: '',
  knowledge_model_base_url: '',
  knowledge_model: '',
  research_model_provider: 'openai',
  research_model_api_key: '',
  research_model_base_url: '',
  research_model: '',
  fact_review_model_provider: 'openai',
  fact_review_model_api_key: '',
  fact_review_model_base_url: '',
  fact_review_model: '',
  genre_review_model_provider: 'openai',
  genre_review_model_api_key: '',
  genre_review_model_base_url: '',
  genre_review_model: '',
  reader_review_model_provider: 'openai',
  reader_review_model_api_key: '',
  reader_review_model_base_url: '',
  reader_review_model: '',
})

const defaultModelOptions = ref<{label: string, value: string}[]>([])
const cheapModelOptions = ref<{label: string, value: string}[]>([])
const knowledgeModelOptions = ref<{label: string, value: string}[]>([])
const researchModelOptions = ref<{label: string, value: string}[]>([])
const factReviewModelOptions = ref<{label: string, value: string}[]>([])
const genreReviewModelOptions = ref<{label: string, value: string}[]>([])
const readerReviewModelOptions = ref<{label: string, value: string}[]>([])

const pageSize = 50
const pages = ref<Record<string, number>>({
  default: 1,
  cheap: 1,
  knowledge: 1,
  research: 1,
  fact_review: 1,
  genre_review: 1,
  reader_review: 1,
})

const pageCount = (opts: {label: string, value: string}[]) => {
  return Math.max(1, Math.ceil((opts?.length || 0) / pageSize))
}

const paged = (role: string, opts: {label: string, value: string}[]) => {
  const p = pages.value[role] || 1
  return opts.slice((p - 1) * pageSize, p * pageSize)
}

const syncProviders = () => {
  formData.value.default_model = ''
  formData.value.cheap_model = ''
  formData.value.knowledge_model = ''
  formData.value.research_model = ''
}

const loadData = async () => {
  try {
    const res = await getLLMConfig()
    if (res) {
      // res is already the data object returned by axios interceptor
      formData.value = { ...formData.value, ...res }
      
      // 初始化下拉框展示
      if (formData.value.default_model) {
        defaultModelOptions.value = [{ label: formData.value.default_model, value: formData.value.default_model }]
      }
      if (formData.value.cheap_model) {
        cheapModelOptions.value = [{ label: formData.value.cheap_model, value: formData.value.cheap_model }]
      }
      if (formData.value.knowledge_model) {
        knowledgeModelOptions.value = [{ label: formData.value.knowledge_model, value: formData.value.knowledge_model }]
      }
      if (formData.value.research_model) {
        researchModelOptions.value = [{ label: formData.value.research_model, value: formData.value.research_model }]
      }
      if (formData.value.fact_review_model) {
        factReviewModelOptions.value = [{ label: formData.value.fact_review_model, value: formData.value.fact_review_model }]
      }
      if (formData.value.genre_review_model) {
        genreReviewModelOptions.value = [{ label: formData.value.genre_review_model, value: formData.value.genre_review_model }]
      }
      if (formData.value.reader_review_model) {
        readerReviewModelOptions.value = [{ label: formData.value.reader_review_model, value: formData.value.reader_review_model }]
      }

      // 推断是否属于统一模式（四个配置的值完全一样）
      if (
        formData.value.default_model_provider === formData.value.cheap_model_provider &&
        formData.value.default_model_api_key === formData.value.cheap_model_api_key &&
        formData.value.default_model_base_url === formData.value.cheap_model_base_url &&
        formData.value.default_model_provider === formData.value.knowledge_model_provider &&
        formData.value.default_model_api_key === formData.value.knowledge_model_api_key &&
        formData.value.default_model_base_url === formData.value.knowledge_model_base_url &&
        formData.value.default_model_provider === formData.value.research_model_provider &&
        formData.value.default_model_api_key === formData.value.research_model_api_key &&
        formData.value.default_model_base_url === formData.value.research_model_base_url
      ) {
        isUnifiedMode.value = true
      } else {
        isUnifiedMode.value = false
      }
    }
  } catch (e) {
    console.error('Failed to load LLM config', e)
  }
}

const handleVerify = async (role: 'default' | 'cheap' | 'knowledge' | 'research' | 'fact_review' | 'genre_review' | 'reader_review') => {
  const p = formData.value.default_model_provider
  const key = formData.value.default_model_api_key
  const base = formData.value.default_model_base_url

  let p_target = p
  let key_target = key
  let base_target = base

  if (role === 'cheap') {
    p_target = formData.value.cheap_model_provider
    key_target = formData.value.cheap_model_api_key
    base_target = formData.value.cheap_model_base_url
  } else if (role === 'knowledge') {
    p_target = formData.value.knowledge_model_provider
    key_target = formData.value.knowledge_model_api_key
    base_target = formData.value.knowledge_model_base_url
  } else if (role === 'research') {
    p_target = formData.value.research_model_provider
    key_target = formData.value.research_model_api_key
    base_target = formData.value.research_model_base_url
  } else if (role === 'fact_review') {
    p_target = formData.value.fact_review_model_provider
    key_target = formData.value.fact_review_model_api_key
    base_target = formData.value.fact_review_model_base_url
  } else if (role === 'genre_review') {
    p_target = formData.value.genre_review_model_provider
    key_target = formData.value.genre_review_model_api_key
    base_target = formData.value.genre_review_model_base_url
  } else if (role === 'reader_review') {
    p_target = formData.value.reader_review_model_provider
    key_target = formData.value.reader_review_model_api_key
    base_target = formData.value.reader_review_model_base_url
  }

  const targetKey = key_target
  if (!targetKey) {
    message.warning('请先输入完整且有效的 API Key')
    return
  }

  if (role === 'default') verifyingDefault.value = true
  else if (role === 'cheap') verifyingCheap.value = true
  else if (role === 'knowledge') verifyingKnowledge.value = true
  else if (role === 'research') verifyingResearch.value = true
  else if (role === 'fact_review') verifyingFactReview.value = true
  else if (role === 'genre_review') verifyingGenreReview.value = true
  else verifyingReaderReview.value = true

  try {
    const targetProvider = p_target
    const targetBase = base_target

    const shouldUseBackend = targetKey.includes('***') || targetKey.startsWith('sk-...')
    const res = shouldUseBackend ? await fetchModelsByRole(role) : await verifyAndFetchModels(targetProvider, targetKey, targetBase)
    // res is already the data object returned by axios interceptor
    if (res && res.models) {
      const opts = res.models.map((m: string) => ({ label: m, value: m }))

      if (isUnifiedMode.value && (role === 'default' || role === 'cheap' || role === 'knowledge' || role === 'research')) {
        defaultModelOptions.value = opts
        cheapModelOptions.value = opts
        knowledgeModelOptions.value = opts
        researchModelOptions.value = opts
      } else {
        if (role === 'default') defaultModelOptions.value = opts
        else if (role === 'cheap') cheapModelOptions.value = opts
        else if (role === 'knowledge') knowledgeModelOptions.value = opts
        else if (role === 'research') researchModelOptions.value = opts
        else if (role === 'fact_review') factReviewModelOptions.value = opts
        else if (role === 'genre_review') genreReviewModelOptions.value = opts
        else readerReviewModelOptions.value = opts
      }

      message.success(`成功获取 ${res.models.length} 个模型`)
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '连接失败，请检查端点和秘钥')
  } finally {
    if (role === 'default') verifyingDefault.value = false
    else if (role === 'cheap') verifyingCheap.value = false
    else if (role === 'knowledge') verifyingKnowledge.value = false
    else if (role === 'research') verifyingResearch.value = false
    else if (role === 'fact_review') verifyingFactReview.value = false
    else if (role === 'genre_review') verifyingGenreReview.value = false
    else verifyingReaderReview.value = false
  }
}

const handleSave = async () => {
  saving.value = true

  // 如果是统一模式，保存前把 default 的配置强行复制给其他三个
  if (isUnifiedMode.value) {
    formData.value.cheap_model_provider = formData.value.default_model_provider
    formData.value.cheap_model_api_key = formData.value.default_model_api_key
    formData.value.cheap_model_base_url = formData.value.default_model_base_url
    
    formData.value.knowledge_model_provider = formData.value.default_model_provider
    formData.value.knowledge_model_api_key = formData.value.default_model_api_key
    formData.value.knowledge_model_base_url = formData.value.default_model_base_url

    formData.value.research_model_provider = formData.value.default_model_provider
    formData.value.research_model_api_key = formData.value.default_model_api_key
    formData.value.research_model_base_url = formData.value.default_model_base_url
  }
  
  try {
    await saveLLMConfig(formData.value)
    message.success('配置保存成功，系统已切换路由通道')
    visible.value = false
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

const open = () => {
  visible.value = true
  loadData()
}

defineExpose({ open })
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }
.mt-4 { margin-top: 16px; }
.text-xs { font-size: 12px; }
</style>
