<template>
  <article class="stat-card" :class="{ loading: loading }">
    <div class="stat-icon-wrap">
      <span v-if="icon" class="stat-icon">{{ icon }}</span>
    </div>
    <div class="stat-content">
      <span class="stat-title">{{ title }}</span>
      <div class="stat-value-wrap">
        <n-skeleton v-if="loading" :width="80" :height="28" />
        <template v-else>
          <span class="stat-value">{{ formattedValue }}</span>
          <span v-if="unit" class="stat-unit">{{ unit }}</span>
        </template>
      </div>
    </div>
    <div v-if="trend && !loading" class="stat-trend" :class="`trend-${trend.direction}`">
      <span class="trend-arrow">{{ trend.direction === 'up' ? '↑' : '↓' }}</span>
      <span class="trend-value">{{ trendValue }}%</span>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NSkeleton } from 'naive-ui'

interface TrendData {
  value: number
  direction: 'up' | 'down'
}

interface Props {
  title: string
  value: number | string
  icon?: string
  trend?: TrendData
  loading?: boolean
  unit?: string
}

const props = defineProps<Props>()

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString()
  }
  return props.value
})

const trendValue = computed(() => props.trend ? Math.abs(props.trend.value) : 0)
</script>

<style scoped>
.stat-card {
  background: var(--app-surface);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  box-shadow: var(--app-shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.04));
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--app-border, transparent);
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: linear-gradient(180deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-pressed, #7c3aed) 100%);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.stat-card:hover {
  box-shadow: var(--app-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.06));
  transform: translateY(-1px);
}

.stat-card:hover::before {
  opacity: 1;
}

.stat-card.loading {
  opacity: 0.7;
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--app-surface-subtle) 0%, var(--app-border) 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon {
  font-size: 20px;
  line-height: 1;
}

.stat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stat-title {
  font-size: 12px;
  color: var(--app-text-muted, #64748b);
  font-weight: 500;
  letter-spacing: 0.01em;
}

.stat-value-wrap {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-value {
  font-size: 26px;
  font-weight: 800;
  color: var(--app-text-primary, #1e293b);
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.stat-unit {
  font-size: 12px;
  color: var(--app-text-secondary, #94a3b8);
  font-weight: 500;
}

.stat-trend {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}

.stat-trend.trend-up {
  background: var(--color-success-light, rgba(16, 185, 129, 0.1));
  color: var(--color-success, #10b981);
}

.stat-trend.trend-down {
  background: var(--color-danger-light, rgba(239, 68, 68, 0.1));
  color: var(--color-danger, #ef4444);
}

.trend-arrow {
  font-size: 10px;
}

.trend-value {
  letter-spacing: -0.01em;
}
</style>
