<template>
  <div class="anti-ai-dashboard">
    <!-- 顶部概览 -->
    <div class="dashboard-header">
      <div class="header-info">
        <h3 class="dashboard-title">🛡️ Anti-AI 防御系统</h3>
        <p class="dashboard-subtitle">七层纵深防御体系 · 让 AI 写出来的文字不再像 AI</p>
      </div>
      <div class="header-actions">
        <n-button size="small" type="primary" secondary @click="showTutorial = true">
          📖 使用教程
        </n-button>
      </div>
    </div>

    <!-- 子标签页 -->
    <div class="sub-tabs">
      <div
        v-for="tab in subTabs"
        :key="tab.key"
        class="sub-tab"
        :class="{ 'is-active': activeSubTab === tab.key }"
        @click="activeSubTab = tab.key"
      >
        {{ tab.icon }} {{ tab.label }}
      </div>
    </div>

    <!-- ═══════════════════════════════════
         概览面板
         ═══════════════════════════════════ -->
    <template v-if="activeSubTab === 'overview'">
      <!-- 七层防御状态 -->
      <div class="layers-grid">
        <div
          v-for="layer in defenseLayers"
          :key="layer.key"
          class="layer-card"
          :class="{ 'is-active': layer.active }"
          :style="{ '--layer-color': layer.color }"
        >
          <div class="layer-icon">{{ layer.icon }}</div>
          <div class="layer-info">
            <div class="layer-name">{{ layer.name }}</div>
            <div class="layer-desc">{{ layer.desc }}</div>
          </div>
          <div class="layer-status">
            <n-tag :type="layer.active ? 'success' : 'default'" size="tiny" :bordered="false">
              {{ layer.active ? '运行中' : '未激活' }}
            </n-tag>
          </div>
        </div>
      </div>

      <!-- 系统统计 -->
      <div v-if="antiAIStats" class="stats-section">
        <h4 class="section-title">📊 系统统计</h4>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-number">{{ antiAIStats.total_prompts }}</div>
            <div class="stat-desc">总提示词数</div>
          </div>
          <div class="stat-card">
            <div class="stat-number accent">{{ antiAIStats.anti_ai_prompts }}</div>
            <div class="stat-desc">Anti-AI 提示词</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ antiAIStats.cliche_patterns }}</div>
            <div class="stat-desc">俗套检测模式</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ antiAIStats.categories_count }}</div>
            <div class="stat-desc">分类数</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ═══════════════════════════════════
         快速扫描面板
         ═══════════════════════════════════ -->
    <template v-if="activeSubTab === 'scan'">
      <div class="scan-section">
        <p class="section-desc">粘贴一段文本，检测其中的 AI 味模式</p>
        <n-input
          v-model:value="scanInput"
          type="textarea"
          :autosize="{ minRows: 5, maxRows: 14 }"
          placeholder="在此粘贴要检测的文本…"
          class="scan-input"
        />
        <div class="scan-actions">
          <n-button
            type="primary"
            :loading="scanning"
            :disabled="!scanInput.trim()"
            @click="handleScan"
          >
            开始扫描
          </n-button>
          <n-button v-if="scanInput.trim()" quaternary @click="scanInput = ''">
            清空
          </n-button>
        </div>

        <!-- 扫描结果 -->
        <div v-if="scanResult" class="scan-result">
          <div class="result-header">
            <div class="result-assessment" :style="{ color: assessmentColor }">
              {{ scanResult.overall_assessment }}
            </div>
            <div class="result-score">
              严重性分数：<strong>{{ scanResult.severity_score }}</strong>/100
            </div>
          </div>

          <div class="result-stats">
            <div class="stat-item">
              <span class="stat-value critical">{{ scanResult.critical_hits }}</span>
              <span class="stat-label">严重</span>
            </div>
            <div class="stat-item">
              <span class="stat-value warning">{{ scanResult.warning_hits - scanResult.critical_hits > 0 ? scanResult.warning_hits - scanResult.critical_hits : scanResult.total_hits - scanResult.critical_hits }}</span>
              <span class="stat-label">警告</span>
            </div>
            <div class="stat-item">
              <span class="stat-value">{{ scanResult.total_hits }}</span>
              <span class="stat-label">总命中</span>
            </div>
          </div>

          <!-- 分类分布 -->
          <div v-if="Object.keys(scanResult.category_distribution).length" class="category-dist">
            <h5 class="sub-title">分类分布</h5>
            <div class="dist-bars">
              <div
                v-for="(count, cat) in scanResult.category_distribution"
                :key="cat"
                class="dist-row"
              >
                <span class="dist-cat">{{ cat }}</span>
                <div class="dist-bar-bg">
                  <div
                    class="dist-bar-fill"
                    :style="{ width: `${(count / scanResult.total_hits) * 100}%` }"
                  ></div>
                </div>
                <span class="dist-count">{{ count }}</span>
              </div>
            </div>
          </div>

          <!-- 改进建议 -->
          <div v-if="scanResult.improvement_suggestions && scanResult.improvement_suggestions.length" class="suggestions">
            <h5 class="sub-title">💡 改进建议</h5>
            <div
              v-for="(sug, idx) in scanResult.improvement_suggestions"
              :key="idx"
              class="suggestion-item"
            >
              {{ sug }}
            </div>
          </div>

          <!-- 修改建议 -->
          <div v-if="scanResult.recommendations && scanResult.recommendations.length" class="recommendations">
            <h5 class="sub-title">⚠️ 修改建议</h5>
            <div
              v-for="(rec, idx) in scanResult.recommendations"
              :key="idx"
              class="recommendation-item"
            >
              {{ rec }}
            </div>
          </div>

          <!-- 命中详情 -->
          <div v-if="scanResult.hits && scanResult.hits.length" class="hits-list">
            <h5 class="sub-title">命中详情 ({{ scanResult.hits.length }})</h5>
            <div
              v-for="(hit, idx) in scanResult.hits.slice(0, 30)"
              :key="idx"
              class="hit-item"
              :class="`severity-${hit.severity}`"
            >
              <n-tag :type="severityTagType(hit.severity)" size="tiny" :bordered="false">
                {{ hit.severity }}
              </n-tag>
              <span class="hit-pattern">{{ hit.pattern }}</span>
              <code class="hit-text">{{ hit.text }}</code>
              <span v-if="hit.replacement_hint" class="hit-hint">→ {{ hit.replacement_hint }}</span>
            </div>
            <div v-if="scanResult.hits.length > 30" class="more-hits">
              还有 {{ scanResult.hits.length - 30 }} 处命中…
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ═══════════════════════════════════
         规则面板
         ═══════════════════════════════════ -->
    <template v-if="activeSubTab === 'rules'">
      <div class="rules-section">
        <p class="section-desc">
          正向行为映射规则：将"禁止 X"重构为"当遇到场景 Y 时，必须执行 Z"，
          避免否定指令在 Transformer Self-Attention 中激活被禁止的 Token。
        </p>

        <div v-if="rulesLoading" class="loading-wrap">
          <n-spin size="small" />
        </div>

        <div v-else-if="rules.length" class="rules-list">
          <div
            v-for="rule in rules"
            :key="rule.key"
            class="rule-card"
          >
            <div class="rule-header">
              <n-tag :type="severityTagType(rule.severity)" size="tiny" :bordered="false">
                {{ rule.severity }}
              </n-tag>
              <span class="rule-anti">{{ rule.anti_pattern }}</span>
              <n-tag size="tiny" :bordered="false" type="info">{{ rule.category }}</n-tag>
            </div>
            <div class="rule-action">
              <span class="rule-label">✅ 正向动作：</span>
              {{ rule.positive_action }}
            </div>
          </div>
        </div>

        <n-empty v-else description="暂无规则数据" />
      </div>
    </template>

    <!-- ═══════════════════════════════════
         白名单面板
         ═══════════════════════════════════ -->
    <template v-if="activeSubTab === 'allowlist'">
      <div class="allowlist-section">
        <p class="section-desc">
          在战斗/悬疑/恐怖/告白等特定场景中，部分"AI味"模式是被允许的。
          白名单不等于滥用——即使在允许的场景中也有密度限制。
        </p>

        <div v-if="allowlistLoading" class="loading-wrap">
          <n-spin size="small" />
        </div>

        <div v-else-if="allowlistScenes.length" class="scenes-list">
          <div
            v-for="scene in allowlistScenes"
            :key="scene.scene_type"
            class="scene-card"
          >
            <div class="scene-header">
              <span class="scene-type-label">{{ getSceneLabel(scene.scene_type) }}</span>
              <code class="scene-key">{{ scene.scene_type }}</code>
              <n-tag size="tiny" :bordered="false" type="info">
                密度上限: {{ scene.max_density_per_1000 }}/千字
              </n-tag>
            </div>
            <p class="scene-desc">{{ scene.description }}</p>
            <div v-if="scene.allowed_categories.length" class="scene-categories">
              <span class="scene-label">豁免分类：</span>
              <n-tag
                v-for="cat in scene.allowed_categories"
                :key="cat"
                size="tiny"
                type="success"
                :bordered="false"
              >
                {{ cat }}
              </n-tag>
            </div>
            <div v-if="scene.allowed_patterns.length" class="scene-patterns">
              <span class="scene-label">豁免模式：</span>
              <n-tag
                v-for="pat in scene.allowed_patterns"
                :key="pat"
                size="tiny"
                :bordered="false"
              >
                {{ pat }}
              </n-tag>
            </div>
          </div>
        </div>

        <n-empty v-else description="暂无白名单数据" />
      </div>
    </template>

    <!-- 教程弹窗 -->
    <n-modal
      v-model:show="showTutorial"
      preset="card"
      title="📖 Anti-AI 防御系统使用教程"
      style="max-width: 720px"
      :bordered="true"
    >
      <div class="tutorial-content">
        <section class="tutorial-section">
          <h4>🎯 这是什么？</h4>
          <p>
            Anti-AI 防御系统是一套工程化的"去AI味"治理方案，从提示词重构到 Token 级拦截，
            建立七层纵深防御体系，让 AI 生成的文字不再有"AI味"。
          </p>
          <p>
            传统做法是在提示词中写"不要写X"，但这反而激活了 Transformer 中的 X Token。
            我们的正向行为映射策略把"禁止X"改为"当遇到Y时执行Z"，从根源上避免激活问题。
          </p>
        </section>

        <section class="tutorial-section">
          <h4>🏗️ 七层防御体系</h4>
          <div class="tutorial-layers">
            <div class="tl-item">
              <strong>L1 正向行为映射</strong>：把"禁止X"改为"当遇到Y时执行Z"，避免否定指令反而激活被禁止的模式。
            </div>
            <div class="tl-item">
              <strong>L2 核心协议 P1-P5</strong>：信息密度法则、感官优先法则、角色差异化法则、节奏法则、衔接法则。
            </div>
            <div class="tl-item">
              <strong>L3 场景化白名单</strong>：战斗场景允许生理描写，悬疑场景允许微表情，不同场景有不同豁免。
            </div>
            <div class="tl-item">
              <strong>L4 角色状态向量</strong>：声线指纹、紧张习惯、反应模式、信息边界——四维锚定角色一致性。
            </div>
            <div class="tl-item">
              <strong>L5 上下文配额</strong>：洋葱模型配额分配，Anti-AI 协议永远不被压缩。
            </div>
            <div class="tl-item">
              <strong>L6 Token 级拦截</strong>：AC 自动机流式扫描 + Logit Bias 抑制，实时拦截 AI 味输出。
            </div>
            <div class="tl-item">
              <strong>L7 章后审计</strong>：35+ 模式检测、指标趋势追踪、自适应学习新模式。
            </div>
          </div>
        </section>

        <section class="tutorial-section">
          <h4>🚀 如何使用？</h4>
          <ol class="tutorial-steps">
            <li>在提示词广场的 <strong>🛡️ Anti-AI 防御</strong> 分类中查看和编辑防御提示词</li>
            <li>使用<strong>快速扫描</strong>标签页检测文本中的 AI 味</li>
            <li>在<strong>规则</strong>标签页中查看正向行为映射规则</li>
            <li>在<strong>白名单</strong>标签页中了解各场景的豁免规则</li>
            <li>生成章节时，系统会自动注入 Anti-AI 行为协议到 T0 槽位</li>
            <li>章节生成后，系统会自动运行 Anti-AI 审计管线</li>
            <li>在 API 端点 <code>/api/v1/anti-ai/scan</code> 中可以程序化调用扫描</li>
          </ol>
        </section>

        <section class="tutorial-section">
          <h4>🔬 35+ 检测模式一览</h4>
          <p>系统内置 35+ 种 AI 味检测模式，覆盖以下分类：</p>
          <div class="pattern-categories">
            <div class="pc-item"><strong>微表情</strong>：嘴角上扬、眼里闪过、指尖泛白、一丝系列、下意识等</div>
            <div class="pc-item"><strong>声线</strong>：带语气前缀、声线变化、字字带X、不容置疑等</div>
            <div class="pc-item"><strong>比喻</strong>：仿佛/宛如/犹如、心湖涟漪、小动物比喻等</div>
            <div class="pc-item"><strong>生理性</strong>：生理性泪水/水雾、生理性前缀等</div>
            <div class="pc-item"><strong>情绪标签</strong>：直接情绪标签、心中波澜等</div>
            <div class="pc-item"><strong>句式</strong>：不是而是、破折号等</div>
            <div class="pc-item"><strong>俗套</strong>：面部大忌、身体大忌、四肢百骸等</div>
            <div class="pc-item"><strong>严禁词</strong>：死死等</div>
          </div>
        </section>

        <section class="tutorial-section">
          <h4>⚠️ 注意事项</h4>
          <ul class="tutorial-notes">
            <li>白名单不等于滥用——即使在允许的场景中，也有密度限制</li>
            <li>角色状态锁是防止"记忆漂移"的关键，请确保 Bible 中的角色信息完整</li>
            <li>AC 自动机对中文检测更准确，Logit Bias 仅用于英文 Token</li>
            <li>学习服务发现的新模式需要人工审核通过后才会生效</li>
            <li>正向行为映射的核心是"不要写禁止，要写替代"——让模型有明确的方向</li>
            <li>章节审计是全自动的，每次生成章节后自动运行，无需手动触发</li>
          </ul>
        </section>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NButton, NInput, NTag, NModal, NSpin, NEmpty, useMessage } from 'naive-ui'
import { scanChapter, getAntiAIStats, getRules, getAllowlistScenes } from '../../../api/anti-ai'
import type { ScanResult, AntiAIStats, AntiAIRule, AllowlistScene } from '../../../types/anti-ai'
import { ASSESSMENT_COLORS, SCENE_TYPE_LABELS } from '../../../types/anti-ai'

const message = useMessage()

// 子标签页
const subTabs = [
  { key: 'overview', icon: '🏠', label: '概览' },
  { key: 'scan', icon: '🔍', label: '快速扫描' },
  { key: 'rules', icon: '📋', label: '规则' },
  { key: 'allowlist', icon: '🎫', label: '白名单' },
]
const activeSubTab = ref('overview')

// 状态
const scanInput = ref('')
const scanning = ref(false)
const scanResult = ref<ScanResult | null>(null)
const antiAIStats = ref<AntiAIStats | null>(null)
const showTutorial = ref(false)

// 规则数据
const rules = ref<AntiAIRule[]>([])
const rulesLoading = ref(false)

// 白名单数据
const allowlistScenes = ref<AllowlistScene[]>([])
const allowlistLoading = ref(false)

// 七层防御定义
const defenseLayers = computed(() => {
  const layers = antiAIStats.value?.layers
  return [
    {
      key: 'L1',
      name: 'L1 正向行为映射',
      desc: '将否定指令转为确定性的动作映射',
      icon: '🧭',
      color: '#6366f1',
      active: true,
    },
    {
      key: 'L2',
      name: 'L2 核心协议 P1-P5',
      desc: '五大写作法则：密度/感官/差异/节奏/衔接',
      icon: '📋',
      color: '#8b5cf6',
      active: true,
    },
    {
      key: 'L3',
      name: 'L3 场景化白名单',
      desc: '不同场景的差异化模式豁免',
      icon: '🎫',
      color: '#a855f7',
      active: (layers?.L3_allowlist_scenes ?? 0) > 0,
    },
    {
      key: 'L4',
      name: 'L4 角色状态向量',
      desc: '声线指纹/紧张习惯/反应模式/信息边界',
      icon: '🎯',
      color: '#d946ef',
      active: layers?.L4_state_vector === 'active',
    },
    {
      key: 'L5',
      name: 'L5 上下文配额',
      desc: '洋葱模型配额分配，T0 永不压缩',
      icon: '🧅',
      color: '#ec4899',
      active: layers?.L5_context_quota === 'active',
    },
    {
      key: 'L6',
      name: 'L6 Token 级拦截',
      desc: 'AC自动机流式扫描 + Logit Bias 抑制',
      icon: '🔒',
      color: '#f43f5e',
      active: layers?.L6_token_guard === 'active',
    },
    {
      key: 'L7',
      name: 'L7 章后审计',
      desc: '35+模式检测 + 指标趋势 + 自适应学习',
      icon: '📊',
      color: '#ef4444',
      active: layers?.L7_audit === 'active',
    },
  ]
})

// 评估颜色
const assessmentColor = computed(() => {
  if (!scanResult.value) return '#6b7280'
  return ASSESSMENT_COLORS[scanResult.value.overall_assessment] || '#6b7280'
})

// 方法
async function handleScan() {
  if (!scanInput.value.trim()) return
  scanning.value = true
  try {
    scanResult.value = await scanChapter(scanInput.value)
  } catch (e: any) {
    message.error(e?.message || '扫描失败')
  } finally {
    scanning.value = false
  }
}

function severityTagType(severity: string) {
  switch (severity) {
    case 'critical': return 'error'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'default'
  }
}

function getSceneLabel(sceneType: string): string {
  return SCENE_TYPE_LABELS[sceneType] || sceneType
}

async function loadStats() {
  try {
    antiAIStats.value = await getAntiAIStats()
  } catch {
    // 静默失败
  }
}

async function loadRules() {
  rulesLoading.value = true
  try {
    rules.value = await getRules()
  } catch {
    // 静默失败
  } finally {
    rulesLoading.value = false
  }
}

async function loadAllowlist() {
  allowlistLoading.value = true
  try {
    allowlistScenes.value = await getAllowlistScenes()
  } catch {
    // 静默失败
  } finally {
    allowlistLoading.value = false
  }
}

onMounted(() => {
  loadStats()
  loadRules()
  loadAllowlist()
})
</script>

<style scoped>
.anti-ai-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* 顶部 */
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.dashboard-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text-primary);
}
.dashboard-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-text-muted);
}

/* 子标签 */
.sub-tabs {
  display: flex;
  gap: 0;
  border-bottom: 2px solid var(--app-border);
  flex-shrink: 0;
}
.sub-tab {
  font-size: 13px;
  font-weight: 500;
  padding: 8px 16px;
  cursor: pointer;
  color: var(--app-text-muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s ease;
  user-select: none;
}
.sub-tab:hover {
  color: var(--app-text-primary);
}
.sub-tab.is-active {
  color: var(--color-brand);
  border-bottom-color: var(--color-brand);
  font-weight: 600;
}

/* 七层防御 */
.layers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}
.layer-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  transition: all 0.2s ease;
}
.layer-card:hover {
  border-color: var(--layer-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.layer-card.is-active {
  border-left: 3px solid var(--layer-color);
}
.layer-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.layer-info {
  flex: 1;
  min-width: 0;
}
.layer-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}
.layer-desc {
  font-size: 11.5px;
  color: var(--app-text-muted);
  margin-top: 2px;
}
.layer-status {
  flex-shrink: 0;
}

/* 扫描区 */
.scan-section,
.rules-section,
.allowlist-section {
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-lg);
  padding: 18px;
  border: 1px solid var(--app-border);
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 6px;
}
.section-desc {
  font-size: 12.5px;
  color: var(--app-text-muted);
  margin: 0 0 14px;
  line-height: 1.6;
}
.scan-input :deep(textarea) {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  line-height: 1.6;
}
.scan-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

/* 扫描结果 */
.scan-result {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--app-border);
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.result-assessment {
  font-size: 24px;
  font-weight: 800;
}
.result-score {
  font-size: 14px;
  color: var(--app-text-secondary);
}

.result-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
}
.stat-value.critical { color: #dc2626; }
.stat-value.warning { color: #f59e0b; }
.stat-label {
  font-size: 12px;
  color: var(--app-text-muted);
}

/* 分类分布 */
.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 14px 0 8px;
}
.dist-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dist-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dist-cat {
  font-size: 12px;
  color: var(--app-text-secondary);
  width: 60px;
  text-align: right;
  flex-shrink: 0;
}
.dist-bar-bg {
  flex: 1;
  height: 8px;
  background: var(--app-surface);
  border-radius: 4px;
  overflow: hidden;
}
.dist-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-brand), var(--color-purple));
  border-radius: 4px;
  transition: width 0.3s ease;
  min-width: 4px;
}
.dist-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  width: 24px;
  flex-shrink: 0;
}

/* 建议 */
.suggestions,
.recommendations {
  margin-top: 4px;
}
.suggestion-item {
  font-size: 12.5px;
  color: var(--app-text-secondary);
  padding: 8px 12px;
  background: var(--app-surface);
  border-radius: var(--app-radius-sm);
  margin-bottom: 4px;
  border: 1px solid var(--app-border);
  border-left: 3px solid #22c55e;
}
.recommendation-item {
  font-size: 12.5px;
  color: var(--app-text-secondary);
  padding: 8px 12px;
  background: var(--app-surface);
  border-radius: var(--app-radius-sm);
  margin-bottom: 4px;
  border: 1px solid var(--app-border);
  border-left: 3px solid #f59e0b;
}

/* 命中详情 */
.hits-list {
  margin-top: 4px;
}
.hit-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: var(--app-radius-sm);
  margin-bottom: 3px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}
.hit-item.severity-critical {
  border-left: 3px solid #dc2626;
}
.hit-item.severity-warning {
  border-left: 3px solid #f59e0b;
}
.hit-pattern {
  color: var(--app-text-primary);
  font-weight: 500;
  flex-shrink: 0;
}
.hit-text {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--app-surface-subtle);
  padding: 1px 5px;
  border-radius: 3px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hit-hint {
  color: var(--color-brand);
  font-size: 11px;
  margin-left: auto;
  flex-shrink: 0;
}
.more-hits {
  font-size: 12px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 8px;
}

/* 系统统计 */
.stats-section {
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-lg);
  padding: 18px;
  border: 1px solid var(--app-border);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 10px;
  background: var(--app-surface);
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
}
.stat-number {
  font-size: 22px;
  font-weight: 800;
  color: var(--color-brand);
}
.stat-number.accent {
  color: #d946ef;
}
.stat-desc {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-top: 4px;
}

/* 规则列表 */
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rule-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  padding: 12px 14px;
  border-left: 3px solid var(--color-brand);
}
.rule-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.rule-anti {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}
.rule-action {
  font-size: 12.5px;
  color: var(--app-text-secondary);
  line-height: 1.5;
}
.rule-label {
  font-weight: 600;
  color: #22c55e;
}

/* 白名单场景 */
.scenes-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.scene-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  padding: 14px 16px;
}
.scene-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.scene-type-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
}
.scene-key {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--app-text-muted);
  background: var(--app-surface-subtle);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--app-border);
}
.scene-desc {
  font-size: 12.5px;
  color: var(--app-text-secondary);
  margin: 0 0 10px;
  line-height: 1.5;
}
.scene-categories,
.scene-patterns {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}
.scene-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-right: 4px;
}

/* 加载 */
.loading-wrap {
  display: flex;
  justify-content: center;
  padding: 24px;
}

/* 教程 */
.tutorial-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--app-text-secondary);
}
.tutorial-section {
  margin-bottom: 20px;
}
.tutorial-section h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 8px;
}
.tutorial-layers {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tl-item {
  padding: 8px 12px;
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-sm);
  border-left: 3px solid var(--color-brand);
  font-size: 13px;
}
.tutorial-steps {
  padding-left: 20px;
}
.tutorial-steps li {
  margin-bottom: 6px;
}
.tutorial-notes {
  padding-left: 20px;
}
.tutorial-notes li {
  margin-bottom: 4px;
  color: var(--app-text-muted);
}
.tutorial-content code {
  background: var(--app-surface-subtle);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  font-family: var(--font-mono);
}
.pattern-categories {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.pc-item {
  padding: 6px 10px;
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-sm);
  font-size: 12.5px;
  border-left: 2px solid var(--color-brand);
}
</style>
