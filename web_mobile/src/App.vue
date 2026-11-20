<template>
  <div class="app-shell">
    <router-view v-slot="{ Component }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>

    <van-tabbar
      v-if="showTabbar"
      route
      fixed
      safe-area-inset-bottom
      class="app-tabbar"
      active-color="#5aa9ff"
      inactive-color="#8b8f96"
    >
      <van-tabbar-item to="/home" replace icon="wap-home-o">首页</van-tabbar-item>
      <van-tabbar-item to="/rag" replace icon="chat-o">AI 问答</van-tabbar-item>
      <van-tabbar-item to="/profile" replace icon="user-o">我的</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const showTabbar = computed(() => !!route.meta.tab);
</script>
