<template>
  <div class="page--with-nav">
    <AppNav :title="feature || '电脑版功能'" back-to="/home" />

    <section class="card desktop-card">
      <div class="icon-wrap">
        <van-icon name="wap-home-o" size="34" />
      </div>
      <h1>{{ feature || '此功能' }}暂未提供移动版</h1>
      <p>为了获得完整的操作体验（表格、批量管理、复杂表单等），请前往电脑版工作台使用。</p>

      <van-button block round type="primary" size="large" class="btn" @click="openDesktop">
        打开电脑版
      </van-button>
      <van-button block round plain size="large" class="btn" @click="router.replace('/home')">
        返回首页
      </van-button>

      <p class="url faint">{{ desktopUrl }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppNav from '@/components/AppNav.vue';

const route = useRoute();
const router = useRouter();
const feature = computed(() => String(route.query.feature || ''));
const desktopUrl = (import.meta.env.VITE_DESKTOP_URL as string) || 'https://hkai.favor100.site';

function openDesktop() {
  window.open(desktopUrl, '_blank');
}
</script>

<style scoped>
.desktop-card {
  margin-top: 18px;
  padding: 30px 20px 24px;
  text-align: center;
}
.icon-wrap {
  width: 68px;
  height: 68px;
  margin: 0 auto 18px;
  border-radius: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7fbaff;
  background: rgba(74, 158, 255, 0.14);
  border: 1px solid rgba(74, 158, 255, 0.28);
}
h1 {
  margin: 0 0 10px;
  font-size: 19px;
  color: var(--app-text-strong);
}
p {
  margin: 0 auto 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--app-muted);
  max-width: 320px;
}
.btn {
  margin-top: 10px;
  height: 46px;
}
.url {
  margin: 18px 0 0;
  font-size: 11.5px;
  word-break: break-all;
}
</style>
