<template>
  <div class="empty-box">
    <van-icon :name="icon" size="34" style="opacity: 0.5" />
    <div style="margin-top: 8px">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ text?: string; icon?: string }>(), {
  text: '暂无数据',
  icon: 'notes-o',
});
</script>
