<template>
  <span class="status-badge" :style="{ color: meta.color }">
    <span class="dot" :style="dotStyle" />
    {{ text }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
})

const STATUS_MAP = {
  pending: { text: 'pending 待执行', color: '#9DA7B3', solid: false },
  running: { text: 'running 执行中', color: '#3FB950', solid: false },
  paused_manual: { text: 'paused 已暂停', color: '#9DA7B3', solid: false },
  await_gate: { text: 'await_gate 待确认主域', color: '#D29922', solid: false },
  blocked: { text: 'blocked 待过码', color: '#D29922', solid: false },
  failed: { text: 'failed 失败', color: '#F85149', solid: false },
  done: { text: 'done 已完成', color: '#0D1117', solid: true },
  candidate: { text: 'candidate 待甄别', color: '#D29922', solid: false },
  confirmed: { text: 'confirmed 已确认', color: '#3FB950', solid: false },
  rejected: { text: 'rejected 已驳回', color: '#F85149', solid: false },
  parsed: { text: 'parsed 已解析', color: '#3FB950', solid: false },
  skipped: { text: 'skipped 已跳过', color: '#9DA7B3', solid: false },
}

const meta = computed(() => STATUS_MAP[props.status] || {
  text: props.status || '-',
  color: '#9DA7B3',
  solid: false,
})

const dotStyle = computed(() => ({
  backgroundColor: meta.value.solid ? '#3FB950' : meta.value.color,
  boxShadow: props.status === 'running' ? '0 0 6px #3FB950' : 'none',
  border: meta.value.solid ? '1px solid #3FB950' : 'none',
}))

const text = computed(() => meta.value.text)
</script>
