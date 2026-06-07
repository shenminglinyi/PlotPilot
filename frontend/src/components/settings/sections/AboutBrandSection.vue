<template>
  <section class="about-brand">
    <div class="brand-panel">
      <div class="brand-mark" aria-hidden="true">墨</div>
      <div class="brand-main">
        <div class="brand-kicker">{{ BRAND.descriptor }}</div>
        <h2 class="brand-title">{{ BRAND.displayName }}</h2>
        <p class="brand-line">{{ BRAND.credit }}</p>
      </div>
    </div>

    <div class="info-grid">
      <div class="info-item">
        <span class="info-label">产品定位</span>
        <span class="info-value">{{ BRAND.chineseName }} · {{ BRAND.tagline }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">开发团队</span>
        <span class="info-value">{{ BRAND.team }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">直播时间</span>
        <span class="info-value">{{ BRAND.liveSchedule }}</span>
      </div>
      <a
        class="info-item info-item--link"
        :href="BRAND.douyinUrl"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span class="info-label">抖音</span>
        <span class="info-value">{{ BRAND.douyinLabel }}</span>
      </a>
    </div>
  </section>
</template>

<script setup lang="ts">
import { BRAND } from '@/constants/brand'
</script>

<style scoped>
.about-brand {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.brand-panel {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 1rem;
  align-items: center;
  padding: 1.125rem;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background:
    linear-gradient(90deg, var(--color-brand-light), transparent 62%),
    var(--app-surface);
}

.brand-mark {
  width: 3.25rem;
  height: 3.25rem;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  font-size: 1.5rem;
  font-weight: 800;
}

.brand-main {
  min-width: 0;
}

.brand-kicker {
  font-size: var(--font-size-xs);
  color: var(--app-text-muted);
  margin-bottom: 0.25rem;
}

.brand-title {
  margin: 0;
  font-size: 1.35rem;
  line-height: 1.25;
  color: var(--app-text-primary);
}

.brand-line {
  margin: 0.375rem 0 0;
  color: var(--app-text-secondary);
  line-height: 1.55;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.info-item {
  min-width: 0;
  padding: 0.875rem;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  color: inherit;
  text-decoration: none;
}

.info-item--link {
  transition: border-color 0.2s ease, background 0.2s ease;
}

.info-item--link:hover {
  border-color: var(--color-brand);
  background: var(--color-brand-light);
}

.info-label,
.info-value {
  display: block;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--app-text-muted);
  margin-bottom: 0.375rem;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--app-text-primary);
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .brand-panel,
  .info-grid {
    grid-template-columns: 1fr;
  }

  .brand-mark {
    width: 2.75rem;
    height: 2.75rem;
  }
}
</style>
