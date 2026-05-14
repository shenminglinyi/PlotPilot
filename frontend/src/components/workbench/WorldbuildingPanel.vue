<template>
  <div class="worldbuilding-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">世界观构建</h3>
          <n-tag size="small" round :bordered="false">Worldbuilding</n-tag>
        </div>
        <p class="panel-lead">
          基于专业小说家的<strong>5维度框架</strong>，构建自洽、生动且充满张力的世界。
        </p>
      </div>
      <n-space class="header-actions" :size="8" align="center">
        <n-button size="small" type="primary" :loading="saving" @click="save">
          保存
        </n-button>
      </n-space>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <div class="worldbuilding-form">
          <!-- 1. 核心法则与底层逻辑 -->
          <n-card size="small" class="wb-card" :bordered="true">
            <template #header>
              <div class="card-header">
                <span class="card-icon">⚙️</span>
                <div>
                  <div class="card-title">核心法则与底层逻辑</div>
                  <div class="card-desc">世界的基石 - 力量体系、物理规律、魔法/科技机制</div>
                </div>
              </div>
            </template>

            <n-space vertical :size="12">
              <div class="field-group">
                <label class="field-label">力量体系/科技树</label>
                <n-input
                  v-model:value="formData.core_rules.power_system"
                  type="textarea"
                  placeholder="魔法的来源？需要付出什么代价？科技水平发展到哪一步？"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">物理规律</label>
                <n-input
                  v-model:value="formData.core_rules.physics_rules"
                  type="textarea"
                  placeholder="重力、时间流逝、日夜交替是否与现实不同？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">魔法/科技机制</label>
                <n-input
                  v-model:value="formData.core_rules.magic_tech"
                  type="textarea"
                  placeholder="详细的运作机制和限制"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>
            </n-space>
          </n-card>

          <!-- 2. 地理与生态环境 -->
          <n-card size="small" class="wb-card" :bordered="true">
            <template #header>
              <div class="card-header">
                <span class="card-icon">🌍</span>
                <div>
                  <div class="card-title">地理与生态环境</div>
                  <div class="card-desc">地理决定论 - 地形、气候、资源、生态链</div>
                </div>
              </div>
            </template>

            <n-space vertical :size="12">
              <div class="field-group">
                <label class="field-label">地形</label>
                <n-input
                  v-model:value="formData.geography.terrain"
                  type="textarea"
                  placeholder="极寒冰原、无尽沙漠、漂浮群岛？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">气候</label>
                <n-input
                  v-model:value="formData.geography.climate"
                  type="textarea"
                  placeholder="气候特征和季节变化"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">资源分布</label>
                <n-input
                  v-model:value="formData.geography.resources"
                  type="textarea"
                  placeholder="水源、矿产、稀有动植物的分布"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">生态链</label>
                <n-input
                  v-model:value="formData.geography.ecology"
                  type="textarea"
                  placeholder="独特的生物圈，对人类是威胁还是利用对象？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>
            </n-space>
          </n-card>

          <!-- 3. 社会结构与权力分配 -->
          <n-card size="small" class="wb-card" :bordered="true">
            <template #header>
              <div class="card-header">
                <span class="card-icon">👥</span>
                <div>
                  <div class="card-title">社会结构与权力分配</div>
                  <div class="card-desc">张力来源 - 政治、经济、阶级</div>
                </div>
              </div>
            </template>

            <n-space vertical :size="12">
              <div class="field-group">
                <label class="field-label">政治体制</label>
                <n-input
                  v-model:value="formData.society.politics"
                  type="textarea"
                  placeholder="君主专制、议会民主、神权统治、寡头企业？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">经济模式</label>
                <n-input
                  v-model:value="formData.society.economy"
                  type="textarea"
                  placeholder="货币体系、主要产业、财富分配"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">阶级系统</label>
                <n-input
                  v-model:value="formData.society.class_system"
                  type="textarea"
                  placeholder="社会分层、阶层流动性、底层困境"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>
            </n-space>
          </n-card>

          <!-- 4. 历史、信仰与文化 -->
          <n-card size="small" class="wb-card" :bordered="true">
            <template #header>
              <div class="card-header">
                <span class="card-icon">📜</span>
                <div>
                  <div class="card-title">历史、信仰与文化</div>
                  <div class="card-desc">厚重感 - 历史事件、宗教、禁忌</div>
                </div>
              </div>
            </template>

            <n-space vertical :size="12">
              <div class="field-group">
                <label class="field-label">关键历史事件</label>
                <n-input
                  v-model:value="formData.culture.history"
                  type="textarea"
                  placeholder="大灾变、圣战、革命 - 塑造现在格局的过去"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">宗教信仰</label>
                <n-input
                  v-model:value="formData.culture.religion"
                  type="textarea"
                  placeholder="信仰什么？如何影响道德观、节日和日常行为？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">文化禁忌</label>
                <n-input
                  v-model:value="formData.culture.taboos"
                  type="textarea"
                  placeholder="刻板印象、社会禁忌、不可触碰的底线"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>
            </n-space>
          </n-card>

          <!-- 5. 沉浸感细节 -->
          <n-card size="small" class="wb-card" :bordered="true">
            <template #header>
              <div class="card-header">
                <span class="card-icon">✨</span>
                <div>
                  <div class="card-title">沉浸感细节</div>
                  <div class="card-desc">血肉 - 衣食住行、俚语、娱乐</div>
                </div>
              </div>
            </template>

            <n-space vertical :size="12">
              <div class="field-group">
                <label class="field-label">衣食住行</label>
                <n-input
                  v-model:value="formData.daily_life.food_clothing"
                  type="textarea"
                  placeholder="平时吃什么？穿什么？住哪里？用什么交通工具？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">俚语与口音</label>
                <n-input
                  v-model:value="formData.daily_life.language_slang"
                  type="textarea"
                  placeholder="特有的词汇、黑话、方言"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>

              <div class="field-group">
                <label class="field-label">娱乐方式</label>
                <n-input
                  v-model:value="formData.daily_life.entertainment"
                  type="textarea"
                  placeholder="闲暇时怎么打发时间？"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                />
              </div>
            </n-space>
          </n-card>

          <!-- 冰山理论提示 -->
          <n-alert type="info" :bordered="false" class="iceberg-tip">
            <template #icon>
              <span style="font-size: 18px">💡</span>
            </template>
            <strong>冰山理论：</strong>你可能设定了 100% 的世界观，但在正文中只需展示 10%。
            不要在开篇进行说明文式的"设定倾倒"，而是让主角在行动中自然触碰这些规则。
          </n-alert>
        </div>
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { worldbuildingApi } from '@/api/worldbuilding'

interface Props {
  slug: string
}

const props = defineProps<Props>()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)

const formData = ref({
  core_rules: {
    power_system: '',
    physics_rules: '',
    magic_tech: ''
  },
  geography: {
    terrain: '',
    climate: '',
    resources: '',
    ecology: ''
  },
  society: {
    politics: '',
    economy: '',
    class_system: ''
  },
  culture: {
    history: '',
    religion: '',
    taboos: ''
  },
  daily_life: {
    food_clothing: '',
    language_slang: '',
    entertainment: ''
  }
})

const loadWorldbuilding = async () => {
  loading.value = true
  try {
    const data = await worldbuildingApi.getWorldbuilding(props.slug)
    formData.value = {
      core_rules: data.core_rules || formData.value.core_rules,
      geography: data.geography || formData.value.geography,
      society: data.society || formData.value.society,
      culture: data.culture || formData.value.culture,
      daily_life: data.daily_life || formData.value.daily_life
    }
  } catch (error: any) {
    if (error.response?.status === 404) {
      message.warning('世界观尚未创建，首次保存时将自动创建')
    } else {
      message.error(error.response?.data?.detail || '加载世界观失败')
    }
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    await worldbuildingApi.updateWorldbuilding(props.slug, formData.value)
    message.success('世界观已保存')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.slug, (slug) => {
  if (slug) loadWorldbuilding()
})

onMounted(() => {
  loadWorldbuilding()
})
</script>

<style scoped>
.worldbuilding-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--plotpilot-panel-muted);
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.header-main {
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-1);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-3);
}

.header-actions {
  flex-shrink: 0;
}

.panel-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.worldbuilding-form {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wb-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.card-icon {
  font-size: 24px;
  line-height: 1;
  flex-shrink: 0;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color-1);
  margin-bottom: 4px;
}

.card-desc {
  font-size: 12px;
  color: var(--text-color-3);
  line-height: 1.4;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color-2);
}

.iceberg-tip {
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
