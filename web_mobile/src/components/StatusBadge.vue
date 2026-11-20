<template>
  <span class="status" :class="cls">{{ text }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ status?: string; label?: string }>();

const MAP: Record<string, { text: string; cls: string }> = {
  queued: { text: '排队中', cls: 'status--warn' },
  running: { text: '处理中', cls: 'status--run' },
  needs_human: { text: '需人工', cls: 'status--warn' },
  succeeded: { text: '已完成', cls: 'status--ok' },
  failed: { text: '失败', cls: 'status--err' },
};

const text = computed(() => props.label || MAP[props.status || '']?.text || props.status || '—');
const cls = computed(() => MAP[props.status || '']?.cls || '');
</script>
