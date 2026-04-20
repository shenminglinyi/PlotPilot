<template>
  <div class="snapshot-panel">
    <n-alert type="info" :show-icon="true" title="版本快照（语义快照）" style="margin-bottom: 12px">
      <ul class="snap-bullets">
        <li><strong>写</strong>：规划下一卷前自动触发；作者在挂起审阅时手动「创建世界线」；不做正文深拷贝，仅存指针与 bible/ledger 状态摘要。</li>
        <li><strong>读</strong>：仅在你触发 Rollback 时加载，通过重置外键指针瞬间回到历史节点。</li>
      </ul>
    </n-alert>

    <n-card title="分支示意（接入 API 后替换为真实节点）" size="small" :bordered="true" style="margin-bottom: 12px">
      <div class="branch-graph" aria-hidden="true">
        <div class="branch-col">
          <div class="branch-dot branch-dot--auto" title="系统自动" />
          <n-text depth="3" style="font-size: 11px">[Auto] 第一卷完</n-text>
        </div>
        <div class="branch-line" />
        <div class="branch-col">
          <div class="branch-dot branch-dot--manual" title="手动节点" />
          <n-text depth="3" style="font-size: 11px">[Manual] 关键抉择前</n-text>
        </div>
        <div class="branch-line branch-line--dashed" />
        <div class="branch-col">
          <div class="branch-dot branch-dot--head" />
          <n-text depth="3" style="font-size: 11px">HEAD · 当前</n-text>
        </div>
      </div>
      <n-text depth="3" style="font-size: 11px; display: block; margin-top: 10px">
        悬浮节点将显示字数、存活角色数等元数据（待 novel_snapshots 表与列表接口）。
      </n-text>
    </n-card>

    <n-text v-if="slug" depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
      书目：{{ slug }}
    </n-text>

    <n-space vertical :size="10">
      <n-button type="error" secondary size="small" disabled title="待 rollback API">
        一键回滚（未接入）
      </n-button>
      <n-empty description="后端快照列表 / 创建 / rollback 接入后在此展示">
        <template #icon>
          <span style="font-size: 42px">📸</span>
        </template>
        <template #extra>
          <n-text depth="3" style="font-size: 12px; max-width: 300px; text-align: center">
            规划表：NovelSnapshots（type、chapter_pointers_json、bible_state_json、ledger_state_json）。
          </n-text>
        </template>
      </n-empty>
    </n-space>
  </div>
</template>

<script setup lang="ts">
defineProps<{ slug: string }>()
</script>

<style scoped>
.snapshot-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 20px;
}

.snap-bullets {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 12px;
  line-height: 1.55;
}

.branch-graph {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  padding: 8px 0;
}

.branch-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 88px;
}

.branch-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--n-border-color);
}

.branch-dot--auto {
  background: #2080f0;
  border-color: #2080f0;
}

.branch-dot--manual {
  background: #a855f7;
  border-color: #a855f7;
}

.branch-dot--head {
  background: #18a058;
  border-color: #18a058;
}

.branch-line {
  flex: 1;
  min-width: 24px;
  height: 2px;
  background: var(--n-border-color);
  margin-bottom: 22px;
  max-width: 48px;
}

.branch-line--dashed {
  height: 0;
  border-top: 2px dashed var(--n-border-color);
  background: none;
}
</style>
