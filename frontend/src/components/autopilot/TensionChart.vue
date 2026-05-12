<template>
  <n-card title="📈 张力心电图" size="small" :bordered="true">
    <template #header-extra>
      <n-text
        v-if="loading && tensionData.length > 0"
        depth="3"
        style="font-size: 10px; margin-right: 6px"
      >
        同步中…
      </n-text>
      <n-tag v-if="curveStats?.is_flat" type="error" size="small">
        📉 曲线过于平缓
      </n-tag>
      <n-tag v-else-if="hasLowTension" type="warning" size="small">
        ⚠️ 检测到低张力章节
      </n-tag>
      <n-button v-if="tensionData.length > 0" size="tiny" quaternary @click="loadTensionData">↻</n-button>
    </template>

    <!-- 仅首轮无数据时占满卡片；有数据时保留图表 DOM，避免反复卸载导致「刚出来就没了」 -->
    <div v-if="showInitialLoading" class="chart-container chart-loading">
      <n-spin size="small" />
      <span class="chart-loading-text">加载张力曲线…</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!evaluatedData.length" class="chart-container chart-empty">
      <n-empty description="暂无张力数据" size="small">
        <template #icon><span style="font-size:36px">📈</span></template>
        <template #extra>
          <n-text depth="3" style="font-size:11px">写作章节后自动生成张力评分</n-text>
        </template>
      </n-empty>
    </div>

    <!-- 图表 -->
    <div v-else ref="chartRef" class="chart-container" />

    <!-- 曲线平缓警告（优先级最高） -->
    <n-alert
      v-if="curveStats?.is_flat && evaluatedData.length >= 3"
      type="error"
      :show-icon="false"
      style="margin-top: 8px; font-size: 12px"
    >
      📉 张力方差仅 {{ curveStats.variance.toFixed(2) }}，曲线过于平缓！
      评分可能需要校准，或写作引擎需注入更多冲突。
    </n-alert>

    <!-- 连续低张力警告 -->
    <n-alert
      v-else-if="curveStats && curveStats.consecutive_low >= 2"
      type="warning"
      :show-icon="false"
      style="margin-top: 8px; font-size: 12px"
    >
      ⚠️ 连续 {{ curveStats.consecutive_low }} 章低张力（&lt;4.0）· 读者可能正在流失，建议尽快制造冲突
    </n-alert>

    <!-- 低张力警告 -->
    <n-alert
      v-else-if="hasLowTension && evaluatedData.length > 0"
      type="warning"
      :show-icon="false"
      style="margin-top: 8px; font-size: 12px"
    >
      第 {{ lowTensionChapters.join('、') }} 章张力偏低 · 建议插入缓冲章或调整剧情节奏
    </n-alert>

    <!-- 未评估提示 -->
    <n-alert
      v-if="curveStats && curveStats.unevaluated_count > 0"
      type="info"
      :show-icon="false"
      style="margin-top: 4px; font-size: 11px"
    >
      ℹ️ {{ curveStats.unevaluated_count }} 章尚未完成张力评估（图中以虚线标记）
    </n-alert>

    <!-- 底部统计 -->
    <div v-if="evaluatedData.length > 0" class="chart-stats">
      <n-space :size="12" align="center">
        <n-text depth="3" style="font-size:10px">
          {{ evaluatedData.length }} 章 · 均值 {{ avgTension.toFixed(1) }} · 峰值 {{ maxTension.toFixed(1) }}
        </n-text>
        <n-divider vertical style="margin:0" />
        <n-text
          :style="{ fontSize: '10px', color: getTensionColor(avgTension) }"
        >
          {{ getTensionLabel(avgTension) }}
        </n-text>
        <n-divider vertical style="margin:0" />
        <n-text depth="3" style="font-size:10px">
          方差 {{ curveStats?.variance.toFixed(2) ?? '—' }}
        </n-text>
      </n-space>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { monitorApi } from '../../api/monitor'
import type { TensionCurveStats } from '../../api/monitor'
import { isRequestCanceled } from '../../utils/requestCancel'

interface TensionData {
  chapter_number: number
  tension_score: number  // 0-10 刻度
  title?: string
  evaluated: boolean     // 是否已完成真实评估
}

const props = defineProps<{
  novelId: string
  threshold?: number
  refreshKey?: number
}>()

const emit = defineEmits<{
  'chapter-click': [chapterNumber: number]
  'low-tension-alert': [chapters: number[]]
}>()

const chartRef = ref<HTMLElement | null>(null)
const tensionData = ref<TensionData[]>([])
const curveStats = ref<TensionCurveStats | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

let chartInstance: echarts.ECharts | null = null
/** 监听卡片/分栏拖拽导致的容器宽高变化（不会触发 window resize） */
let chartResizeObserver: ResizeObserver | null = null

function teardownChartResizeObserver() {
  chartResizeObserver?.disconnect()
  chartResizeObserver = null
}

function setupChartResizeObserver() {
  teardownChartResizeObserver()
  const el = chartRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  chartResizeObserver = new ResizeObserver(() => {
    requestAnimationFrame(() => chartInstance?.resize())
  })
  chartResizeObserver.observe(el)
}

/** 容器尚未布局完成时延迟渲染；封顶避免无限 setTimeout（隐藏标签页 / 折叠面板） */
let renderDimensionAttempts = 0
const RENDER_DIMENSION_ATTEMPTS_MAX = 40

/** 新拉取开始前取消上一轮，避免后端忙时并发堆积；取消不算错误，不清空已有曲线 */
let tensionLoadAbort: AbortController | null = null
const TENSION_FETCH_TIMEOUT_MS = 60_000

// 张力警戒线
const tensionThreshold = computed(() => props.threshold ?? 5.0)

/** 有缓存数据时刷新不再接管整个卡片，避免 loading 触发的 v-if 拆掉图表容器 */
const showInitialLoading = computed(
  () => loading.value && tensionData.value.length === 0,
)

// 只包含已评估章节的数据
const evaluatedData = computed(() =>
  tensionData.value.filter(d => d.evaluated)
)

// 是否有低张力章节（仅已评估）
const hasLowTension = computed(() =>
  evaluatedData.value.some(d => d.tension_score < tensionThreshold.value)
)

// 低张力章节列表
const lowTensionChapters = computed(() =>
  evaluatedData.value
    .filter(d => d.tension_score < tensionThreshold.value)
    .map(d => d.chapter_number)
)

// 统计（仅已评估章节）
const avgTension = computed(() => {
  if (!evaluatedData.value.length) return 0
  const sum = evaluatedData.value.reduce((s, d) => s + d.tension_score, 0)
  return sum / evaluatedData.value.length
})

const maxTension = computed(() => {
  if (!evaluatedData.value.length) return 0
  return Math.max(...evaluatedData.value.map(d => d.tension_score))
})

// ==================== 加载 ====================
async function loadTensionData() {
  if (tensionLoadAbort) {
    tensionLoadAbort.abort()
  }
  const ac = new AbortController()
  tensionLoadAbort = ac

  loading.value = true
  error.value = null
  renderDimensionAttempts = 0
  const timeoutId = window.setTimeout(() => ac.abort(), TENSION_FETCH_TIMEOUT_MS)
  try {
    const data = await monitorApi.getTensionCurve(props.novelId, {
      signal: ac.signal,
      timeout: TENSION_FETCH_TIMEOUT_MS,
    })
    if (ac.signal.aborted) {
      return
    }

    tensionData.value = (data.points || []).map((p) => ({
      chapter_number: p.chapter,
      tension_score: p.tension,
      title: p.title,
      evaluated: p.evaluated !== false,  // 默认为 true
    }))

    // 保存后端统计信息
    curveStats.value = data.stats ?? null

    if (lowTensionChapters.value.length > 0) {
      emit('low-tension-alert', lowTensionChapters.value)
    }

    // 等 DOM 更新后再渲染图表（解决第五章后不显示的关键）
    await nextTick()
    // 再等一帧确保容器尺寸已计算
    setTimeout(() => renderChart(), 50)
  } catch (err: unknown) {
    if (isRequestCanceled(err)) {
      return
    }
    console.error('[TensionChart] Failed to load:', err)
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    window.clearTimeout(timeoutId)
    if (tensionLoadAbort === ac) {
      tensionLoadAbort = null
    }
    loading.value = false
  }
}

// ==================== 渲染 ====================
function renderChart() {
  if (!chartRef.value || tensionData.value.length === 0) return

  // 确保 DOM 可见且有尺寸
  const rect = chartRef.value.getBoundingClientRect()
  if (rect.width < 10 || rect.height < 10) {
    renderDimensionAttempts += 1
    if (renderDimensionAttempts <= RENDER_DIMENSION_ATTEMPTS_MAX) {
      setTimeout(() => renderChart(), 200)
    } else {
      console.warn('[TensionChart] 容器尺寸长期为 0，停止重试（请展开所在面板或切换可见标签）')
    }
    return
  }
  renderDimensionAttempts = 0

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const chapterNumbers = tensionData.value.map((d) => d.chapter_number)
  const tensionScores = tensionData.value.map((d) => d.tension_score)

  // 未评估章节用虚线连接，已评估用实线
  const evaluatedFlags = tensionData.value.map((d) => d.evaluated)

  const option: echarts.EChartsOption = {
    grid: {
      left: 36,
      right: 16,
      top: 24,
      bottom: 28,
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      data: chapterNumbers,
      name: '章节',
      nameLocation: 'middle',
      nameGap: 22,
      nameTextStyle: { color: '#888', fontSize: 10 },
      axisLine: { lineStyle: { color: '#444' } },
      axisTick: { show: true, lineStyle: { color: '#555' } },
      axisLabel: {
        color: '#999',
        fontSize: 10,
        interval: chapterNumbers.length > 15 ? 'auto' : 0,
        rotate: chapterNumbers.length > 20 ? 45 : 0,
      },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      name: '张力',
      min: 0,
      max: 10,
      interval: 2,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#888', fontSize: 10 },
      splitLine: { lineStyle: { color: '#333', type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        data: tensionScores.map((val, idx) => ({
          value: val,
          itemStyle: {
            color: evaluatedFlags[idx] ? getTensionColor(val) : '#999',
            borderColor: evaluatedFlags[idx] ? '#fff' : '#999',
            borderWidth: evaluatedFlags[idx] ? 2 : 1,
          },
        })),
        smooth: 0.4,
        symbol: 'circle',
        symbolSize: (_value: unknown, params: any) => {
          const idx = params.dataIndex
          const isLast = idx === tensionScores.length - 1
          const isEval = evaluatedFlags[idx]
          if (!isEval) return 3  // 未评估用小圆点
          return isLast ? 8 : 5
        },
        lineStyle: {
          width: 2.5,
          color: '#18a058',
          type: 'solid',
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(24, 160, 88, 0.25)' },
            { offset: 1, color: 'rgba(24, 160, 88, 0.02)' },
          ]),
        },
        markLine: {
          silent: true,
          symbol: 'none',
          label: {
            formatter: '警戒线',
            position: 'end',
            color: '#f0a020',
            fontSize: 10,
          },
          lineStyle: { color: '#f0a020', type: 'dashed', width: 1.5 },
          data: [{ yAxis: tensionThreshold.value }],
        },
        markPoint: {
          symbol: 'pin',
          symbolSize: 36,
          label: { fontSize: 9, color: '#fff' },
          data: [
            { type: 'max', name: '最高', itemStyle: { color: '#d03050' } },
            { type: 'min', name: '最低', itemStyle: { color: '#666' } },
          ],
        },
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      borderColor: '#444',
      textStyle: { color: '#fff', fontSize: 12 },
      confine: true,
      formatter: (params: any) => {
        const pt = params[0]
        const chNum = pt.name
        const tension = pt.value as number
        const idx = pt.dataIndex
        const isEval = evaluatedFlags[idx]
        const ch = tensionData.value.find((d) => d.chapter_number === Number(chNum))

        let html = `<div style="padding:4px 8px"><b>第 ${chNum} 章</b>`
        if (ch?.title) html += `<br/><span style="color:#aaa;font-size:11px">${ch.title}</span>`

        if (!isEval) {
          html += `<br/><span style="color:#999">⏳ 尚未评估</span>`
        } else {
          html += `<br/><span style="color:${getTensionColor(tension)}">▲ ${tension.toFixed(1)}</span>`
          html += ` <span style="color:#666">${getTensionLabel(tension)}</span>`
          if (tension < tensionThreshold.value) html += `<br/><span style="color:#f0a020">⚠️ 低于警戒</span>`
        }
        html += `</div>`
        return html
      },
    },
    animationDuration: 600,
    animationEasing: 'cubicOut',
  }

  chartInstance.setOption(option, true)
  setupChartResizeObserver()
  chartInstance.resize()

  // 点击事件
  chartInstance.off('click')
  chartInstance.on('click', (params: any) => {
    if (params.componentType === 'series') {
      emit('chapter-click', Number(params.name))
    }
  })
}

function getTensionColor(t: number): string {
  if (t >= 8) return '#d03050'
  if (t >= 6) return '#f0a020'
  if (t >= 4) return '#18a058'
  return '#36ad6a'
}

function getTensionLabel(t: number): string {
  if (t >= 8) return '🔥 高潮'
  if (t >= 6) return '⚡ 冲突'
  if (t >= 4) return '🌊 暗流'
  return '💤 平缓'
}

function handleResize() {
  chartInstance?.resize()
}

// ==================== 监听 ====================
watch(() => props.novelId, () => void loadTensionData())

// 🔥 刷新信号变化时重新加载（由 Dashboard 的 SSE 事件驱动）
watch(() => props.refreshKey, (newKey) => {
  if (newKey && newKey > 0) void loadTensionData()
})

// 数据变化时重新渲染（防抖）
let resizeTimer: ReturnType<typeof setTimeout> | null = null
watch(tensionData, () => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    renderChart()
    resizeTimer = null
  }, 100)
})

// ==================== 生命周期 ====================
onMounted(() => {
  void loadTensionData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  tensionLoadAbort?.abort()
  tensionLoadAbort = null
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  teardownChartResizeObserver()
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 200px;
  position: relative;
}

.chart-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 6px;
}

.chart-loading-text {
  font-size: 11px;
  color: var(--text-color-3);
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 0;
}

.chart-stats {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--n-border-color, rgba(0,0,0,0.08));
}
</style>
