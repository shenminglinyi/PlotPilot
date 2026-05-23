<template>
  <footer class="brand-footer" aria-label="产品与团队信息">
    <span class="brand-footer__name">{{ BRAND.productName }}</span>
    <span class="brand-footer__sep">·</span>
    <span class="brand-footer__sub">{{ BRAND.chineseName }}</span>
    <span class="brand-footer__text">{{ BRAND.credit }}</span>
    <a
      class="brand-footer__link"
      :href="BRAND.douyinUrl"
      target="_blank"
      rel="noopener noreferrer"
    >
      {{ BRAND.douyinLabel }}
    </a>
    <span class="brand-footer__text">{{ BRAND.liveSchedule }}</span>
  </footer>
</template>

<script setup lang="ts">
import { BRAND } from '@/constants/brand'
</script>

<style scoped>
.brand-footer {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 28px 20px 32px;
  margin-top: 40px;
  border-top: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}

.brand-footer__name {
  font-weight: 700;
  color: var(--color-gold);
  letter-spacing: 0.03em;
}

.brand-footer__sep {
  opacity: 0.4;
}

.brand-footer__sub {
  font-weight: 600;
  color: var(--color-gold-light);
  opacity: 0.8;
}

.brand-footer__text {
  color: var(--app-text-muted);
}

.brand-footer__link {
  color: var(--color-gold);
  text-decoration: none;
  font-weight: 600;
  border-bottom: 1px dashed var(--color-gold-border);
  transition: all 0.2s ease;
  white-space: nowrap;
}

.brand-footer__link:hover {
  color: var(--color-gold-light);
  border-bottom-style: solid;
  box-shadow: 0 0 8px var(--color-glow-gold);
}
</style>
