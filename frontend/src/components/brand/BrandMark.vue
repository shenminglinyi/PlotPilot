<template>
  <!-- 墨枢品牌印记：蓝青渐变纸飞机——「启航的数据增长」，呼应「作者的领航员」。
       深蓝→青蓝渐变在浅底自稳；深底由调用方 drop-shadow 描白边托底。
       图片为品牌资产，不随主题换肤。 -->
  <img
    :src="logoUrl"
    :width="size"
    :height="size"
    role="img"
    aria-label="墨枢"
    class="brand-mark"
    alt=""
    draggable="false"
  />
</template>

<script setup lang="ts">
import logoUrl from '@/assets/brand-logo.png'

withDefaults(defineProps<{ size?: number }>(), { size: 48 })
</script>

<style scoped>
.brand-mark {
  display: block;
  flex-shrink: 0;
  /* 深色背景上给纸飞机一道细白边，防止深蓝端隐没 */
  filter: drop-shadow(0 0 1px rgba(255, 255, 255, 0.28));
}
</style>
