<script setup lang="ts">
/**
 * BrandSeal — 「墨枢」朱底白文方印，品牌唯一签名元素。
 * 用于品牌时刻：首页头部、侧栏品牌区、设置「关于」、启动页（index.html 内联了一份同款）。
 * 印面用 --color-seal（朱砂），随主题微调；刻字恒为纸色，不随主题反转。
 */
withDefaults(defineProps<{ size?: number }>(), { size: 40 })
</script>

<template>
  <svg
    class="brand-seal"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    role="img"
    aria-label="墨枢印"
  >
    <rect width="48" height="48" rx="9" fill="var(--color-seal, #b13a2a)" />
    <rect
      x="2.5"
      y="2.5"
      width="43"
      height="43"
      rx="7"
      fill="none"
      stroke="rgba(245, 239, 226, 0.4)"
      stroke-width="1.6"
    />
    <text x="24" y="22.5" text-anchor="middle" font-size="16" font-weight="900" fill="#f5efe2" class="seal-char">墨</text>
    <text x="24" y="40.5" text-anchor="middle" font-size="16" font-weight="900" fill="#f5efe2" class="seal-char">枢</text>
  </svg>
</template>

<style scoped>
.brand-seal {
  display: block;
  flex: none;
}
.seal-char {
  font-family: var(--font-display, 'Noto Serif SC', serif);
}
</style>
