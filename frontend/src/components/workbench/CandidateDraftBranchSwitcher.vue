<template>
  <n-space :size="6" align="center" wrap>
    <n-tag size="small" round :type="activeBranchName ? 'info' : 'default'">
      {{ activeBranchName ? `分支 · ${activeBranchName}` : '分支 · 全部' }}
    </n-tag>
    <n-button size="tiny" quaternary @click="setBranch('main')">
      主线
    </n-button>
    <n-button size="tiny" quaternary @click="setBranch('')">
      全部
    </n-button>
    <n-input
      v-model:value="inputValue"
      size="small"
      clearable
      placeholder="输入分支名"
      :style="{ width }"
      @keydown.enter.prevent="applyInput"
      @blur="applyInput"
    />
  </n-space>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useCandidateDraftBranchStore } from '../../stores/candidateDraftBranchStore'

const props = withDefaults(defineProps<{
  slug: string
  width?: string
}>(), {
  width: '180px',
})

const branchStore = useCandidateDraftBranchStore()

const activeBranchName = computed(() => branchStore.getActiveBranch(props.slug))
const inputValue = ref(activeBranchName.value)

watch(
  () => props.slug,
  () => {
    inputValue.value = branchStore.getActiveBranch(props.slug)
  },
  { immediate: true },
)

watch(activeBranchName, (value) => {
  if (inputValue.value !== value) {
    inputValue.value = value
  }
})

function setBranch(value: string) {
  branchStore.setActiveBranch(props.slug, value)
}

function applyInput() {
  branchStore.setActiveBranch(props.slug, inputValue.value.trim())
}
</script>
