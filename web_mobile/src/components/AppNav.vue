<template>
  <van-nav-bar
    fixed
    placeholder
    :title="title"
    :right-text="rightText"
    :left-arrow="showBack"
    @click-left="goBack"
    @click-right="emit('right')"
  >
    <template v-if="$slots.right" #right>
      <slot name="right" />
    </template>
  </van-nav-bar>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';

const props = withDefaults(
  defineProps<{
    title: string;
    showBack?: boolean;
    backTo?: string;
    rightText?: string;
  }>(),
  { showBack: true, backTo: '', rightText: '' }
);

const emit = defineEmits<{ (e: 'right'): void }>();
const router = useRouter();

function goBack() {
  if (props.backTo) {
    router.replace(props.backTo);
    return;
  }
  if (window.history.length > 1) router.back();
  else router.replace('/home');
}
</script>
