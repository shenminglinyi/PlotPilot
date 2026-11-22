<template>
  <div class="em">
    <header class="em-head">
      <div class="em-head-copy">
        <h4>模型引擎</h4>
        <p>多角色端点配置；统一或独立 API Key。保存后立即切换路由通道。</p>
      </div>
      <n-button type="primary" size="small" :loading="saving" @click="handleSave">保存配置</n-button>
    </header>

    <section class="em-mode" :class="{ 'em-mode--unified': isUnifiedMode }">
      <div class="em-mode-copy">
        <span class="em-mode-badge">{{ isUnifiedMode ? '统一端点' : '独立端点' }}</span>
        <p v-if="isUnifiedMode">所有场景共用一组 Base URL、API Key 与模型 ID。</p>
        <p v-else>主力 / 经济 / 知识图谱可分别配置端点与密钥。</p>
      </div>
      <n-switch v-model:value="isUnifiedMode" size="medium">
        <template #checked>统一</template>
        <template #unchecked>独立</template>
      </n-switch>
    </section>

    <div v-if="!isUnifiedMode" class="em-role-tabs">
      <button
        v-for="tab in independentTabs"
        :key="tab.key"
        type="button"
        class="em-role-tab"
        :class="{ active: activeRole === tab.key }"
        @click="activeRole = tab.key"
      >
        <strong>{{ tab.label }}</strong>
        <span>{{ tab.hint }}</span>
      </button>
    </div>

    <div v-if="visibleUnresolvedNotice" class="em-unresolved-banner" role="alert">
      <span class="em-unresolved-copy">{{ visibleUnresolvedNotice }}</span>
      <n-button
        v-if="canConfirmUnifySecondary"
        size="tiny"
        secondary
        @click="confirmUnifySecondaryBindings"
      >
        归并至主力档案
      </n-button>
    </div>

    <div class="em-body">
      <article
        v-show="isUnifiedMode || activeRole === 'main'"
        class="em-role-card em-role-card--main"
      >
        <div class="em-role-head">
          <span class="em-role-title">主力模型</span>
          <span class="em-role-tag">写作 · 分析 · 规划</span>
        </div>
        <endpoint-grid
          v-model:provider="formData.default_model_provider"
          v-model:api-key="formData.default_model_api_key"
          v-model:base-url="formData.default_model_base_url"
          v-model:model="formData.default_model"
          base-url-placeholder="例如 https://api.openai.com/v1 或兼容网关"
          model-placeholder="网关文档中的主模型 ID"
        />
        <inference-collapse
          v-model:temperature="formData.default_temperature"
          v-model:max-tokens="formData.default_max_tokens"
          v-model:timeout-seconds="formData.default_timeout_seconds"
        />
      </article>

      <article
        v-show="!isUnifiedMode && activeRole === 'cheap'"
        class="em-role-card em-role-card--cheap"
      >
        <div class="em-role-head">
          <span class="em-role-title">经济模型</span>
          <span class="em-role-tag">批量 · 嵌入</span>
        </div>
        <endpoint-grid
          v-model:provider="formData.cheap_model_provider"
          v-model:api-key="formData.cheap_model_api_key"
          v-model:base-url="formData.cheap_model_base_url"
          v-model:model="formData.cheap_model"
          base-url-placeholder="留空则跟随主力模型"
          model-placeholder="轻量 / 低成本模型 ID"
        />
        <inference-collapse
          v-model:temperature="formData.cheap_temperature"
          v-model:max-tokens="formData.cheap_max_tokens"
          v-model:timeout-seconds="formData.cheap_timeout_seconds"
        />
      </article>

      <article
        v-show="!isUnifiedMode && activeRole === 'kg'"
        class="em-role-card em-role-card--kg"
      >
        <div class="em-role-head">
          <span class="em-role-title">知识图谱</span>
          <span class="em-role-tag">三元组抽取</span>
        </div>
        <endpoint-grid
          v-model:provider="formData.knowledge_model_provider"
          v-model:api-key="formData.knowledge_model_api_key"
          v-model:base-url="formData.knowledge_model_base_url"
          v-model:model="formData.knowledge_model"
          base-url-placeholder="留空则跟随主力模型"
          model-placeholder="需较强指令遵循与结构化输出"
        />
        <inference-collapse
          v-model:temperature="formData.knowledge_temperature"
          v-model:max-tokens="formData.knowledge_max_tokens"
          v-model:timeout-seconds="formData.knowledge_timeout_seconds"
        />
      </article>
    </div>

    <p class="em-foot-note">密钥仅存于本地配置，不会写入作品数据。修改后请点击「保存配置」生效。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  MASKED_SECRET_SENTINEL,
  llmControlApi,
  type LLMControlPanelData,
  type LLMProfile,
  type LLMProtocol,
  type LLMRoleKey,
} from '@/api/llmControl'
import { DEFAULT_MAX_OUTPUT_TOKENS } from '@/constants/llm'
import EndpointGrid from './EngineMatrixEndpointGrid.vue'
import InferenceCollapse from './EngineMatrixInferenceCollapse.vue'

const message = useMessage()
const saving = ref(false)
const isUnifiedMode = ref(true)
const activeRole = ref<LLMRoleKey>('main')

const independentTabs = [
  { key: 'main' as const, label: '主力', hint: '写作' },
  { key: 'cheap' as const, label: '经济', hint: '批量' },
  { key: 'kg' as const, label: '图谱', hint: '抽取' },
]

const ROLE_MAIN = '主力模型'
const ROLE_CHEAP = '经济模型'
const ROLE_KG = '知识图谱模型'

const boundProfileIds = reactive<Partial<Record<LLMRoleKey, string>>>({})
const unresolvedBindings = reactive<Partial<Record<LLMRoleKey, string>>>({})
const confirmedUnifiedMissing = reactive<{ cheap: string; kg: string }>({
  cheap: '',
  kg: '',
})

function resetUnifiedMissingConfirmation() {
  confirmedUnifiedMissing.cheap = ''
  confirmedUnifiedMissing.kg = ''
}

watch(isUnifiedMode, () => {
  resetUnifiedMissingConfirmation()
})

interface RoleProfileResolution {
  profile: LLMProfile | undefined
  unresolvedBoundId: string | null
}

function canonicalizeSnapshotProfile(p: LLMProfile): LLMProfile {
  const mode = p.auth_mode ?? 'api_key'
  const apiKey =
    mode === 'api_key' && p.has_secret && (!p.api_key || !p.api_key.trim())
      ? MASKED_SECRET_SENTINEL
      : p.api_key
  return {
    ...p,
    api_key: apiKey,
    extra_headers: { ...(p.extra_headers ?? {}) },
    extra_query: { ...(p.extra_query ?? {}) },
    extra_body: { ...(p.extra_body ?? {}) },
  }
}

const unconfirmedUnifiedSecondary = computed(() => {
  if (!isUnifiedMode.value) return false
  const cheapUnconfirmed = Boolean(
    unresolvedBindings.cheap && confirmedUnifiedMissing.cheap !== unresolvedBindings.cheap,
  )
  const kgUnconfirmed = Boolean(
    unresolvedBindings.kg && confirmedUnifiedMissing.kg !== unresolvedBindings.kg,
  )
  return cheapUnconfirmed || kgUnconfirmed
})

const canConfirmUnifySecondary = computed(
  () => isUnifiedMode.value && unconfirmedUnifiedSecondary.value && !unresolvedBindings.main,
)

function confirmUnifySecondaryBindings() {
  confirmedUnifiedMissing.cheap = unresolvedBindings.cheap ?? ''
  confirmedUnifiedMissing.kg = unresolvedBindings.kg ?? ''
  message.info('已确认：保存统一配置时将把失效次级角色显式归并至当前主力档案')
}

const visibleUnresolvedNotice = computed(() => {
  const missingParts: string[] = []
  if (unresolvedBindings.main) {
    missingParts.push(`主力模型（缺失档案 ${unresolvedBindings.main}）`)
  }
  if (!isUnifiedMode.value) {
    if (unresolvedBindings.cheap) {
      missingParts.push(`经济模型（缺失档案 ${unresolvedBindings.cheap}）`)
    }
    if (unresolvedBindings.kg) {
      missingParts.push(`知识图谱（缺失档案 ${unresolvedBindings.kg}）`)
    }
  } else {
    if (unresolvedBindings.cheap && confirmedUnifiedMissing.cheap !== unresolvedBindings.cheap) {
      missingParts.push(`经济模型（缺失档案 ${unresolvedBindings.cheap}）`)
    }
    if (unresolvedBindings.kg && confirmedUnifiedMissing.kg !== unresolvedBindings.kg) {
      missingParts.push(`知识图谱（缺失档案 ${unresolvedBindings.kg}）`)
    }
  }
  if (!missingParts.length) return ''
  if (isUnifiedMode.value && unconfirmedUnifiedSecondary.value) {
    return `检测到显式角色绑定指向不存在的档案：${missingParts.join('、')}。为防止统一模式静默丢弃绑定后误匹配同名旧档案，请点击「归并至主力档案」确认显式重绑，或切至独立端点补全后再保存。`
  }
  return `检测到显式角色绑定指向不存在的档案：${missingParts.join('、')}。系统已阻止自动覆盖其他同名档案；请补全对应角色模型与密钥，或前往模型控制台重新绑定后再保存。`
})

interface ModelRoleConfig {
  default_model_provider: string
  default_model_api_key: string
  default_model_base_url: string
  default_model: string
  default_temperature: number
  default_max_tokens: number
  default_timeout_seconds: number
  cheap_model_provider: string
  cheap_model_api_key: string
  cheap_model_base_url: string
  cheap_model: string
  cheap_temperature: number
  cheap_max_tokens: number
  cheap_timeout_seconds: number
  knowledge_model_provider: string
  knowledge_model_api_key: string
  knowledge_model_base_url: string
  knowledge_model: string
  knowledge_temperature: number
  knowledge_max_tokens: number
  knowledge_timeout_seconds: number
}

const formData = reactive<ModelRoleConfig>({
  default_model_provider: 'openai',
  default_model_api_key: '',
  default_model_base_url: '',
  default_model: '',
  default_temperature: 0.7,
  default_max_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
  default_timeout_seconds: 300,
  cheap_model_provider: 'openai',
  cheap_model_api_key: '',
  cheap_model_base_url: '',
  cheap_model: '',
  cheap_temperature: 0.5,
  cheap_max_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
  cheap_timeout_seconds: 300,
  knowledge_model_provider: 'openai',
  knowledge_model_api_key: '',
  knowledge_model_base_url: '',
  knowledge_model: '',
  knowledge_temperature: 0.3,
  knowledge_max_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
  knowledge_timeout_seconds: 300,
})

function resolveRoleProfileFromConfig(
  profiles: LLMProfile[],
  activeId: string | null,
  roleBindings: Partial<Record<LLMRoleKey, string>> | undefined,
  role: LLMRoleKey,
  fallbackId?: string,
): RoleProfileResolution {
  const rawBound = roleBindings?.[role]
  const boundId = typeof rawBound === 'string' ? rawBound.trim() : ''
  if (boundId) {
    const bound = profiles.find((p) => p.id === boundId)
    return {
      profile: bound,
      unresolvedBoundId: bound ? null : boundId,
    }
  }
  if (fallbackId) {
    const fallback = profiles.find((p) => p.id === fallbackId)
    if (fallback) {
      return { profile: fallback, unresolvedBoundId: null }
    }
  }
  if (role === 'main') {
    return {
      profile:
        (activeId ? profiles.find((p) => p.id === activeId) : undefined)
        || profiles.find((p) => p.name === ROLE_MAIN)
        || profiles[0],
      unresolvedBoundId: null,
    }
  }
  if (role === 'cheap') {
    return {
      profile:
        profiles.find((p) => p.name === ROLE_CHEAP)
        || profiles.find(
          (p) => p.name.includes('经济') && (p.name.includes('模型') || p.name.toLowerCase().includes('cheap')),
        ),
      unresolvedBoundId: null,
    }
  }
  return {
    profile:
      profiles.find((p) => p.name === ROLE_KG)
      || profiles.find((p) => p.name.includes('知识') && p.name.includes('图谱')),
    unresolvedBoundId: null,
  }
}

function applyProfileToForm(prefix: 'default' | 'cheap' | 'knowledge', p: LLMProfile | undefined) {
  if (prefix === 'default') {
    formData.default_model_provider = p?.protocol ?? 'openai'
    formData.default_model_api_key = p?.api_key ?? ''
    formData.default_model_base_url = p?.base_url ?? ''
    formData.default_model = p?.model ?? ''
    formData.default_temperature = p?.temperature ?? 0.7
    formData.default_max_tokens = p?.max_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
    formData.default_timeout_seconds = p?.timeout_seconds ?? 300
    return
  }
  if (prefix === 'cheap') {
    formData.cheap_model_provider = p?.protocol ?? 'openai'
    formData.cheap_model_api_key = p?.api_key ?? ''
    formData.cheap_model_base_url = p?.base_url ?? ''
    formData.cheap_model = p?.model ?? ''
    formData.cheap_temperature = p?.temperature ?? 0.5
    formData.cheap_max_tokens = p?.max_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
    formData.cheap_timeout_seconds = p?.timeout_seconds ?? 300
    return
  }
  formData.knowledge_model_provider = p?.protocol ?? 'openai'
  formData.knowledge_model_api_key = p?.api_key ?? ''
  formData.knowledge_model_base_url = p?.base_url ?? ''
  formData.knowledge_model = p?.model ?? ''
  formData.knowledge_temperature = p?.temperature ?? 0.3
  formData.knowledge_max_tokens = p?.max_tokens ?? DEFAULT_MAX_OUTPUT_TOKENS
  formData.knowledge_timeout_seconds = p?.timeout_seconds ?? 300
}

async function loadData() {
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()
    const profiles = data.config.profiles.map(canonicalizeSnapshotProfile)
    const bindings = data.config.role_bindings
    const mainRes = resolveRoleProfileFromConfig(profiles, data.config.active_profile_id, bindings, 'main')
    const cheapRes = resolveRoleProfileFromConfig(profiles, data.config.active_profile_id, bindings, 'cheap')
    const kgRes = resolveRoleProfileFromConfig(profiles, data.config.active_profile_id, bindings, 'kg')

    boundProfileIds.main = mainRes.profile?.id
    boundProfileIds.cheap = cheapRes.profile?.id
    boundProfileIds.kg = kgRes.profile?.id

    unresolvedBindings.main = mainRes.unresolvedBoundId ?? undefined
    unresolvedBindings.cheap = cheapRes.unresolvedBoundId ?? undefined
    unresolvedBindings.kg = kgRes.unresolvedBoundId ?? undefined
    resetUnifiedMissingConfirmation()

    applyProfileToForm('default', mainRes.profile)
    applyProfileToForm('cheap', cheapRes.profile)
    applyProfileToForm('knowledge', kgRes.profile)
    isUnifiedMode.value = (data.config.endpoint_mode ?? 'unified') !== 'independent'
  } catch {
    /* 使用默认值 */
  }
}

function buildProfilePayload(
  existing: LLMProfile | undefined,
  idFallback: string,
  defaultName: string,
  provider: string,
  key: string,
  url: string,
  model: string,
  temperature: number,
  maxTokens: number,
  timeoutSeconds: number,
  forceCustomName = false,
): LLMProfile {
  const trimmedKey = key.trim()
  const hasReplacementKey = Boolean(trimmedKey && key !== MASKED_SECRET_SENTINEL)
  const resolvedName = forceCustomName ? defaultName : (existing?.name || defaultName)
  const baseFields = {
    id: idFallback,
    name: resolvedName,
    protocol: provider as LLMProtocol,
    base_url: url,
    model,
    temperature,
    max_tokens: maxTokens,
    timeout_seconds: Math.round(timeoutSeconds),
    extra_headers: existing?.extra_headers ?? {},
    extra_query: existing?.extra_query ?? {},
    extra_body: existing?.extra_body ?? {},
    notes: existing?.notes ?? '',
    preset_key: existing?.preset_key ?? 'custom-openai-compatible',
    use_legacy_chat_completions: existing?.use_legacy_chat_completions ?? false,
  }

  if (existing?.auth_mode === 'oauth' && !hasReplacementKey) {
    return {
      ...baseFields,
      api_key: '',
      auth_mode: 'oauth',
      oauth_provider: existing.oauth_provider ?? '',
      oauth_session_id: existing.oauth_session_id ?? '',
      has_secret: existing.has_secret ?? Boolean(existing.oauth_session_id),
    }
  }

  if (existing?.auth_mode === 'local_gateway' && !hasReplacementKey) {
    return {
      ...baseFields,
      api_key: '',
      auth_mode: 'local_gateway',
      oauth_provider: '',
      oauth_session_id: '',
      has_secret: false,
    }
  }

  return {
    ...baseFields,
    api_key: key,
    auth_mode: 'api_key',
    oauth_provider: '',
    oauth_session_id: '',
    has_secret: key === MASKED_SECRET_SENTINEL ? true : Boolean(trimmedKey),
  }
}

const roleKeyFlag = computed(() => (isUnifiedMode.value ? 'uni' : 'ind'))

function matchesExistingProfileState(
  target: LLMProfile,
  provider: string,
  key: string,
  url: string,
  model: string,
  temperature: number,
  maxTokens: number,
  timeoutSeconds: number,
): boolean {
  const sameCore =
    target.protocol === provider
    && target.base_url === url
    && target.model === model
    && target.temperature === temperature
    && target.max_tokens === maxTokens
    && target.timeout_seconds === Math.round(timeoutSeconds)
  if (!sameCore) return false
  if (target.auth_mode === 'oauth' || target.auth_mode === 'local_gateway') {
    return !key.trim() || key === MASKED_SECRET_SENTINEL
  }
  return target.api_key === key
}

async function handleSave() {
  saving.value = true
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()
    const sourceProfiles: LLMProfile[] = data.config.profiles.map(canonicalizeSnapshotProfile)
    const profiles: LLMProfile[] = data.config.profiles.map(canonicalizeSnapshotProfile)
    const existingBindings = data.config.role_bindings ?? {}

    const mainRes = resolveRoleProfileFromConfig(
      sourceProfiles,
      data.config.active_profile_id,
      existingBindings,
      'main',
      boundProfileIds.main,
    )
    const cheapRes = resolveRoleProfileFromConfig(
      sourceProfiles,
      data.config.active_profile_id,
      existingBindings,
      'cheap',
      boundProfileIds.cheap,
    )
    const kgRes = resolveRoleProfileFromConfig(
      sourceProfiles,
      data.config.active_profile_id,
      existingBindings,
      'kg',
      boundProfileIds.kg,
    )

    unresolvedBindings.main = mainRes.unresolvedBoundId ?? undefined
    unresolvedBindings.cheap = cheapRes.unresolvedBoundId ?? undefined
    unresolvedBindings.kg = kgRes.unresolvedBoundId ?? undefined

    let mainId = mainRes.profile?.id || 'main-default'
    if (mainRes.unresolvedBoundId) {
      const hasMainReplacement = Boolean(
        formData.default_model.trim()
        && formData.default_model_api_key.trim()
        && formData.default_model_api_key !== MASKED_SECRET_SENTINEL,
      )
      if (!hasMainReplacement) {
        message.warning(
          `主力模型绑定的档案（${mainRes.unresolvedBoundId}）不存在，请补全主力模型与密钥或前往模型控制台重新绑定后再保存`,
        )
        return
      }
      mainId = `main-${roleKeyFlag.value}-${Date.now()}`
    }

    const mainProfile = buildProfilePayload(
      mainRes.profile,
      mainId,
      ROLE_MAIN,
      formData.default_model_provider,
      formData.default_model_api_key,
      formData.default_model_base_url,
      formData.default_model,
      formData.default_temperature,
      formData.default_max_tokens,
      formData.default_timeout_seconds,
      Boolean(mainRes.unresolvedBoundId),
    )

    const idx0 = profiles.findIndex((p) => p.id === mainProfile.id)
    if (idx0 >= 0) {
      profiles[idx0] = mainProfile
    } else {
      profiles.unshift(mainProfile)
    }

    const roleBindings: Partial<Record<LLMRoleKey, string>> = {
      main: mainProfile.id,
    }
    const usedRoleProfileIds = new Set<string>([mainProfile.id])

    if (!isUnifiedMode.value) {
      const upsertSecondaryRole = (
        role: 'cheap' | 'kg',
        res: RoleProfileResolution,
        defaultName: string,
        idSeed: string,
        provider: string,
        key: string,
        url: string,
        model: string,
        temperature: number,
        maxTokens: number,
        timeoutSeconds: number,
      ): boolean => {
        if (res.unresolvedBoundId) {
          const hasExplicitReplacement = Boolean(
            model.trim() && key.trim() && key !== MASKED_SECRET_SENTINEL,
          )
          if (!hasExplicitReplacement) {
            message.warning(
              `角色「${defaultName}」绑定的档案（${res.unresolvedBoundId}）不存在，请补全模型与密钥或前往模型控制台重新绑定后再保存`,
            )
            return false
          }
          const recoveredId = `${idSeed}-${roleKeyFlag.value}-${Date.now()}-${role}`
          const recovered = buildProfilePayload(
            undefined,
            recoveredId,
            defaultName,
            provider,
            key,
            url,
            model,
            temperature,
            maxTokens,
            timeoutSeconds,
            true,
          )
          profiles.push(recovered)
          roleBindings[role] = recovered.id
          usedRoleProfileIds.add(recovered.id)
          return true
        }

        const originalExisting = res.profile

        if (!originalExisting) {
          const hasUserInput = Boolean(
            model.trim() || url.trim() || (key.trim() && key !== MASKED_SECRET_SENTINEL),
          )
          if (!hasUserInput) {
            return true
          }
          const newId = `${idSeed}-${roleKeyFlag.value}-${Date.now()}-${role}`
          const created = buildProfilePayload(
            undefined,
            newId,
            defaultName,
            provider,
            key === MASKED_SECRET_SENTINEL ? '' : key,
            url,
            model,
            temperature,
            maxTokens,
            timeoutSeconds,
            true,
          )
          profiles.push(created)
          roleBindings[role] = created.id
          usedRoleProfileIds.add(created.id)
          return true
        }

        if (usedRoleProfileIds.has(originalExisting.id)) {
          const sharedNow = profiles.find((p) => p.id === originalExisting.id)
          const sameAuthIdentity = Boolean(
            sharedNow
            && (sharedNow.auth_mode ?? 'api_key') === (originalExisting.auth_mode ?? 'api_key')
            && (sharedNow.oauth_provider ?? '') === (originalExisting.oauth_provider ?? '')
            && (sharedNow.oauth_session_id ?? '') === (originalExisting.oauth_session_id ?? ''),
          )
          if (
            sharedNow
            && sameAuthIdentity
            && matchesExistingProfileState(
              sharedNow,
              provider,
              key,
              url,
              model,
              temperature,
              maxTokens,
              timeoutSeconds,
            )
          ) {
            roleBindings[role] = sharedNow.id
            return true
          }
          const origAuth = originalExisting.auth_mode ?? 'api_key'
          const hasTypedKey = Boolean(key.trim() && key !== MASKED_SECRET_SENTINEL)
          if (
            origAuth === 'api_key'
            && !hasTypedKey
            && (key === MASKED_SECRET_SENTINEL || originalExisting.has_secret)
          ) {
            message.warning(`角色「${defaultName}」原与其它角色共用密钥档案，拆分为独立配置时请重新输入该角色 API Key`)
            return false
          }
          const forkedId = `${idSeed}-${roleKeyFlag.value}-${Date.now()}-${role}`
          const forked = buildProfilePayload(
            originalExisting,
            forkedId,
            defaultName,
            provider,
            key,
            url,
            model,
            temperature,
            maxTokens,
            timeoutSeconds,
            true,
          )
          profiles.push(forked)
          roleBindings[role] = forked.id
          usedRoleProfileIds.add(forked.id)
          return true
        }

        const updated = buildProfilePayload(
          originalExisting,
          originalExisting.id,
          defaultName,
          provider,
          key,
          url,
          model,
          temperature,
          maxTokens,
          timeoutSeconds,
        )
        const existingIdx = profiles.findIndex((p) => p.id === originalExisting.id)
        if (existingIdx >= 0) {
          profiles[existingIdx] = updated
        } else {
          profiles.push(updated)
        }
        roleBindings[role] = updated.id
        usedRoleProfileIds.add(updated.id)
        return true
      }

      const cheapOk = upsertSecondaryRole(
        'cheap',
        cheapRes,
        ROLE_CHEAP,
        'cheap',
        formData.cheap_model_provider,
        formData.cheap_model_api_key,
        formData.cheap_model_base_url,
        formData.cheap_model,
        formData.cheap_temperature,
        formData.cheap_max_tokens,
        formData.cheap_timeout_seconds,
      )
      if (!cheapOk) return

      const kgOk = upsertSecondaryRole(
        'kg',
        kgRes,
        ROLE_KG,
        'kg',
        formData.knowledge_model_provider,
        formData.knowledge_model_api_key,
        formData.knowledge_model_base_url,
        formData.knowledge_model,
        formData.knowledge_temperature,
        formData.knowledge_max_tokens,
        formData.knowledge_timeout_seconds,
      )
      if (!kgOk) return
    } else {
      const unconfirmedCheap = Boolean(
        cheapRes.unresolvedBoundId && confirmedUnifiedMissing.cheap !== cheapRes.unresolvedBoundId,
      )
      const unconfirmedKg = Boolean(
        kgRes.unresolvedBoundId && confirmedUnifiedMissing.kg !== kgRes.unresolvedBoundId,
      )
      if (unconfirmedCheap || unconfirmedKg) {
        message.warning(
          '检测到经济或知识图谱角色的显式绑定档案缺失，请先点击提示栏「归并至主力档案」确认显式重绑，或切至独立端点补全后再保存',
        )
        return
      }
      if (cheapRes.unresolvedBoundId) {
        roleBindings.cheap = mainProfile.id
      } else if (existingBindings.cheap && profiles.some((p) => p.id === existingBindings.cheap)) {
        roleBindings.cheap = existingBindings.cheap
      }
      if (kgRes.unresolvedBoundId) {
        roleBindings.kg = mainProfile.id
      } else if (existingBindings.kg && profiles.some((p) => p.id === existingBindings.kg)) {
        roleBindings.kg = existingBindings.kg
      }
    }

    const newConfig = {
      ...data.config,
      version: 1,
      endpoint_mode: (isUnifiedMode.value ? 'unified' : 'independent') as 'unified' | 'independent',
      role_bindings: roleBindings,
      active_profile_id: mainProfile.id,
      profiles,
    }

    await llmControlApi.saveConfig(newConfig)
    message.success('配置已保存，系统已切换路由通道')
    await loadData()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<style scoped>
.em {
  max-width: 760px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.em-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.em-head-copy h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.em-head-copy p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-muted);
  max-width: 520px;
}

.em-mode {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
}

.em-mode--unified {
  border-color: color-mix(in srgb, var(--color-brand) 35%, var(--app-border));
  background: color-mix(in srgb, var(--color-brand-light, rgba(37, 99, 235, 0.08)) 55%, var(--app-surface));
}

.em-mode-copy {
  flex: 1;
  min-width: 0;
}

.em-mode-badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: var(--app-border);
  color: var(--app-text-muted);
}

.em-mode--unified .em-mode-badge {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.em-mode-copy p {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-muted);
}

.em-role-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.em-role-tab {
  display: grid;
  gap: 2px;
  padding: 8px 6px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  cursor: pointer;
  text-align: center;
  transition: border-color 0.15s, background 0.15s;
}

.em-role-tab:hover {
  border-color: color-mix(in srgb, var(--color-brand) 28%, var(--app-border));
}

.em-role-tab.active {
  border-color: var(--color-brand-border);
  background: var(--color-brand-light);
}

.em-role-tab strong {
  font-size: 12px;
  color: var(--app-text-primary);
}

.em-role-tab span {
  font-size: 12px;
  color: var(--app-text-muted);
}

.em-body {
  max-height: min(68vh, 640px);
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
}

.em-role-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  border-left-width: 3px;
  background: var(--app-surface);
}

.em-role-card--main { border-left-color: var(--color-brand); }
.em-role-card--cheap { border-left-color: var(--color-warning); }
.em-role-card--kg { border-left-color: var(--color-info, #2b5b73); }

.em-role-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.em-role-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.em-role-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--app-surface-subtle);
  color: var(--app-text-muted);
}

.em-unresolved-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-radius: 8px;
  border-left: 3px solid var(--color-warning, #b45309);
  background: var(--app-surface-subtle, #ebeae6);
  color: var(--app-text-primary, #161615);
  font-size: 13px;
  line-height: 1.55;
}

.em-unresolved-copy {
  flex: 1;
  min-width: 220px;
}

.em-foot-note {
  margin: 0;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}

@media (max-width: 560px) {
  .em-head {
    flex-direction: column;
    align-items: stretch;
  }

  .em-mode {
    flex-direction: column;
  }
}
</style>
