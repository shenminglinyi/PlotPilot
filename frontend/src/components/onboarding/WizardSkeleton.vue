<!-- 书设置向导骨架屏 - 在LLM生成数据期间显示 -->
<template>
  <div class="wizard-skeleton">
    <!-- 世界观维度骨架 -->
    <template v-if="type === 'worldbuilding'">
      <div
        v-for="dim in dimensions"
        :key="dim.key"
        class="skeleton-dimension"
        :class="{
          'skeleton-dimension--done': completedDimensions.has(dim.key),
          'skeleton-dimension--active': activeDimension === dim.key && !completedDimensions.has(dim.key),
        }"
      >
        <div class="skeleton-dimension__header">
          <div class="skeleton-dot" :class="{ 'skeleton-dot--active': activeDimension === dim.key && !completedDimensions.has(dim.key), 'skeleton-dot--done': completedDimensions.has(dim.key) }">
            <span v-if="completedDimensions.has(dim.key)" class="skeleton-dot__check">✓</span>
            <span v-else-if="activeDimension === dim.key" class="skeleton-dot__pulse"></span>
          </div>
          <span class="skeleton-dimension__title">{{ dim.label }}</span>
          <n-tag v-if="completedDimensions.has(dim.key)" size="tiny" type="success">已生成</n-tag>
          <n-tag v-else-if="activeDimension === dim.key" size="tiny" type="info">
            <template #icon>
              <span class="loading-dots">生成中</span>
            </template>
          </n-tag>
          <n-tag v-else size="tiny" type="default">等待中</n-tag>
        </div>
        <!-- 生成中：显示 slot 内容（流式文本预览或字段卡片） -->
        <div v-if="activeDimension === dim.key && !completedDimensions.has(dim.key)" class="skeleton-dimension__body">
          <slot :name="dim.key" />
        </div>
        <!-- 已完成：显示完整字段数据 -->
        <div v-else-if="completedDimensions.has(dim.key)" class="skeleton-dimension__content">
          <slot :name="dim.key" />
        </div>
      </div>
    </template>

    <!-- 人物骨架 -->
    <template v-else-if="type === 'characters'">
      <div class="skeleton-characters">
        <div
          v-for="i in 3"
          :key="i"
          class="skeleton-character"
          :class="{ 'skeleton-character--done': i <= completedCount }"
        >
          <div class="skeleton-character__avatar">
            <span v-if="i <= completedCount" class="skeleton-dot__check">✓</span>
            <span v-else class="skeleton-dot__pulse"></span>
          </div>
          <div class="skeleton-character__info">
            <div class="skeleton-bar skeleton-bar--name" :class="{ 'skeleton-bar--shimmer': i > completedCount }"></div>
            <div class="skeleton-bar skeleton-bar--desc" :class="{ 'skeleton-bar--shimmer': i > completedCount }"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- 地图骨架 -->
    <template v-else-if="type === 'locations'">
      <div class="skeleton-locations">
        <div class="skeleton-map">
          <div class="skeleton-map__placeholder">
            <div class="skeleton-dot__pulse skeleton-map__pulse"></div>
            <span>地图生成中...</span>
          </div>
        </div>
        <div class="skeleton-locations__list">
          <div
            v-for="i in 4"
            :key="i"
            class="skeleton-location"
            :class="{ 'skeleton-location--done': i <= completedCount }"
          >
            <div class="skeleton-bar skeleton-bar--loc-name" :class="{ 'skeleton-bar--shimmer': i > completedCount }"></div>
            <div class="skeleton-bar skeleton-bar--loc-desc" :class="{ 'skeleton-bar--shimmer': i > completedCount }"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- 故事线骨架 -->
    <template v-else-if="type === 'storyline'">
      <div class="skeleton-storyline">
        <div v-for="i in 3" :key="i" class="skeleton-storyline__card">
          <div class="skeleton-bar skeleton-bar--plot-title"></div>
          <div class="skeleton-bar skeleton-bar--plot-line"></div>
          <div class="skeleton-bar skeleton-bar--plot-line skeleton-bar--short"></div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    /** 骨架屏类型 */
    type: 'worldbuilding' | 'characters' | 'locations' | 'storyline'
    /** 世界观：当前正在生成的维度 key */
    activeDimension?: string
    /** 世界观：已完成的维度 key 集合 */
    completedDimensions?: Set<string>
    /** 人物/地点：已完成的数量 */
    completedCount?: number
  }>(),
  {
    activeDimension: '',
    completedDimensions: () => new Set<string>(),
    completedCount: 0,
  }
)

const dimensions = [
  { key: 'core_rules', label: '核心法则' },
  { key: 'geography', label: '地理生态' },
  { key: 'society', label: '社会结构' },
  { key: 'culture', label: '历史文化' },
  { key: 'daily_life', label: '沉浸感细节' },
]
</script>

<style scoped>
.wizard-skeleton {
  width: 100%;
}

/* 世界观维度 */
.skeleton-dimension {
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 8px;
  background: var(--n-color-modal);
  border: 1px solid var(--n-border-color);
  transition: all 0.3s ease;
}

.skeleton-dimension--done {
  border-color: #18a05840;
  background: #18a05808;
}

.skeleton-dimension--active {
  border-color: #2080f040;
  background: #2080f006;
}

.skeleton-dimension__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.skeleton-dimension__title {
  font-weight: 500;
  font-size: 14px;
  flex: 1;
}

.skeleton-dimension__body {
  margin-top: 8px;
  padding-left: 26px;
}

.skeleton-dimension__content {
  margin-top: 8px;
  padding-left: 26px;
}

/* 圆点指示器 */
.skeleton-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid #ddd;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.skeleton-dot--active {
  border-color: #2080f0;
  background: #2080f020;
}

.skeleton-dot--done {
  border-color: #18a058;
  background: #18a058;
}

.skeleton-dot__check {
  color: white;
  font-size: 10px;
  font-weight: bold;
}

.skeleton-dot__pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2080f0;
  animation: pulse-glow 1.2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* 骨架条 */
.skeleton-bar {
  height: 14px;
  border-radius: 4px;
  margin-bottom: 8px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
}

.skeleton-bar--shimmer {
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-bar--long { width: 90%; }
.skeleton-bar--medium { width: 70%; }
.skeleton-bar--short { width: 50%; }
.skeleton-bar--name { width: 40%; height: 16px; }
.skeleton-bar--desc { width: 80%; height: 12px; margin-top: 6px; }
.skeleton-bar--loc-name { width: 35%; height: 14px; }
.skeleton-bar--loc-desc { width: 75%; height: 12px; margin-top: 4px; }
.skeleton-bar--plot-title { width: 50%; height: 18px; margin-bottom: 10px; }
.skeleton-bar--plot-line { width: 85%; height: 12px; margin-bottom: 6px; }

/* 人物骨架 */
.skeleton-characters {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-character {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  transition: all 0.3s ease;
}

.skeleton-character--done {
  border-color: #18a05840;
  background: #18a05808;
}

.skeleton-character__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skeleton-character__info {
  flex: 1;
}

/* 地图骨架 */
.skeleton-map {
  height: 200px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  margin-bottom: 12px;
  overflow: hidden;
}

.skeleton-map__placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #999;
  font-size: 14px;
}

.skeleton-map__pulse {
  width: 24px;
  height: 24px;
}

.skeleton-locations__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-location {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  transition: all 0.3s ease;
}

.skeleton-location--done {
  border-color: #18a05840;
  background: #18a05808;
}

/* 故事线骨架 */
.skeleton-storyline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-storyline__card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  animation: shimmer-card 1.5s ease-in-out infinite;
  background-size: 200% 100%;
  background-image: linear-gradient(90deg, var(--n-color-modal) 25%, rgba(32, 128, 240, 0.04) 50%, var(--n-color-modal) 75%);
}

@keyframes shimmer-card {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 加载文字动画 */
.loading-dots::after {
  content: '';
  animation: dots 1.2s steps(3, end) infinite;
}

@keyframes dots {
  0% { content: ''; }
  33% { content: '.'; }
  66% { content: '..'; }
  100% { content: '...'; }
}
</style>
