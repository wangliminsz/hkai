<template>
  <div class="page page--tab profile">
    <section class="profile-head">
      <div class="avatar">{{ initials }}</div>
      <div class="meta">
        <h1>{{ auth.displayName }}</h1>
        <p class="username">@{{ auth.user?.username || '—' }}</p>
        <div class="tags">
          <span v-for="r in roles" :key="r.id || r.name" class="chip">{{ r.name }}</span>
          <span v-if="auth.user?.tenant_name" class="chip chip--active">{{ auth.user.tenant_name }}</span>
        </div>
      </div>
    </section>

    <section class="info-strip">
      <div class="info-item">
        <span class="k">邮箱</span>
        <span class="v">{{ auth.user?.email || '未设置' }}</span>
      </div>
      <div class="info-item">
        <span class="k">手机</span>
        <span class="v">{{ auth.user?.mobile || '未设置' }}</span>
      </div>
      <div class="info-item">
        <span class="k">部门</span>
        <span class="v">{{ auth.user?.dept_info?.dept_name || '—' }}</span>
      </div>
    </section>

    <van-cell-group inset class="menu">
      <van-cell title="个人资料" label="姓名、邮箱、手机与性别" icon="contact-o" is-link to="/profile/edit" />
      <van-cell title="修改密码" icon="shield-o" is-link to="/change-password" />
      <van-cell title="AI 知识库" icon="chat-o" is-link to="/rag" />
      <van-cell title="电脑版工作台" label="组织架构 / 飞书群推送等请在电脑端使用" icon="wap-home-o" is-link @click="openDesktop" />
      <van-cell title="关于" icon="info-o" :value="`v${version}`" is-link @click="aboutVisible = true" />
    </van-cell-group>

    <van-cell-group inset class="menu">
      <van-cell title="退出登录" icon="revoke" class="logout" @click="confirmLogout" />
    </van-cell-group>

    <footer class="foot">
      <p>{{ app.title }} · 移动版</p>
      <p class="faint">© 2026-2028 {{ app.title }}</p>
    </footer>

    <van-dialog v-model:show="aboutVisible" title="关于" :show-confirm-button="true" confirm-button-text="知道了">
      <div class="about">
        <p><strong>{{ app.title }}</strong> 移动版</p>
        <p>版本 v{{ version }}</p>
        <p class="faint">港险 AI 智慧系统 · 手机端工作台</p>
      </div>
    </van-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showConfirmDialog, showToast } from 'vant';
import { useAppStore } from '@/stores/app';
import { useAuthStore } from '@/stores/auth';

const app = useAppStore();
const auth = useAuthStore();
const router = useRouter();

const aboutVisible = ref(false);
const version = '1.0.0';
const DESKTOP_URL = (import.meta.env.VITE_DESKTOP_URL as string) || 'https://hkai.favor100.site';

const initials = computed(() => (auth.displayName || 'U').slice(0, 1).toUpperCase());
const roles = computed(() => auth.user?.role_info || []);

function openDesktop() {
  window.open(DESKTOP_URL, '_blank');
}

async function confirmLogout() {
  try {
    await showConfirmDialog({
      title: '退出登录',
      message: '确定要退出当前账号吗？',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    });
    auth.clear();
    showToast('已退出登录');
    router.replace('/login');
  } catch {
    /* cancelled */
  }
}
</script>

<style scoped>
.profile {
  padding-top: calc(22px + env(safe-area-inset-top));
}

.profile-head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 18px;
  border-radius: 22px;
  border: 1px solid rgba(74, 158, 255, 0.18);
  background: linear-gradient(135deg, #1e3354 0%, #1a2233 60%, #1b1b20 100%);
  margin-bottom: 14px;
}
.avatar {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 700;
  color: #d8e9ff;
  background: linear-gradient(145deg, #3b6db3, #223450);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.35);
}
.meta {
  min-width: 0;
}
.meta h1 {
  margin: 0;
  font-size: 21px;
  font-weight: 700;
  color: var(--app-text-strong);
}
.username {
  margin: 3px 0 8px;
  font-size: 12.5px;
  color: #93a7c2;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.info-strip {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1px;
  background: var(--app-border);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 16px;
}
.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: var(--app-card);
}
.info-item .k {
  font-size: 12.5px;
  color: var(--app-muted);
}
.info-item .v {
  font-size: 12.5px;
  color: var(--app-text);
  max-width: 65%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu {
  margin: 0 0 14px;
}
.menu :deep(.van-cell) {
  background: transparent;
}
.menu :deep(.van-cell-group) {
  background: transparent;
}
:deep(.van-cell-group--inset) {
  background: var(--app-card);
  border: 1px solid var(--app-border);
}
.logout :deep(.van-cell__title) {
  color: #ff7b7b;
}

.foot {
  margin-top: 26px;
  text-align: center;
  font-size: 12px;
  color: var(--app-muted);
}
.foot p {
  margin: 4px 0;
}

.about {
  padding: 18px 20px 22px;
  text-align: center;
  color: var(--app-text);
  font-size: 13px;
}
.about p {
  margin: 6px 0;
}
</style>
