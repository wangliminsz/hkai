<template>
  <div class="page page--tab home">
    <header class="top">
      <div class="top-left">
        <p class="hello">{{ greeting }}，</p>
        <h1 class="name">{{ auth.displayName }}</h1>
        <p class="sub">
          {{ dateText }}
          <span v-if="auth.user?.tenant_name"> · {{ auth.user.tenant_name }}</span>
        </p>
      </div>
      <button class="avatar" type="button" @click="router.push('/profile')">
        <span>{{ initials }}</span>
      </button>
    </header>

    <section class="hero">
      <div class="hero-glow"></div>
      <div class="hero-body">
        <p class="hero-kicker">HONGKONG HK · MOBILE</p>
        <h2 class="hero-title">港险 AI 智慧系统</h2>
      </div>
    </section>

    <div class="section-title">
      <span>功能</span>
      <span class="faint small">{{ features.length }} 项可用</span>
    </div>

    <section class="grid">
      <button
        v-for="f in features"
        :key="f.key"
        type="button"
        class="feature"
        @click="openFeature(f)"
      >
        <span class="feature-icon" :class="`feature-icon--${f.color}`">
          <van-icon :name="f.icon" />
        </span>
        <span class="feature-body">
          <span class="feature-title">{{ f.title }}</span>
          <span class="feature-desc">{{ f.desc }}</span>
        </span>
        <van-icon name="arrow" class="feature-arrow" />
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

interface Feature {
  key: string;
  title: string;
  desc: string;
  icon: string;
  color: string;
  path?: string;
}

const auth = useAuthStore();
const router = useRouter();

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return '凌晨好';
  if (h < 12) return '早上好';
  if (h < 18) return '下午好';
  return '晚上好';
});

const dateText = computed(() => {
  const d = new Date();
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · 星期${week}`;
});

const initials = computed(() => {
  const name = auth.displayName || 'U';
  return name.slice(0, 1).toUpperCase();
});

const features = computed<Feature[]>(() => {
  const list: Feature[] = [
    { key: 'rag', title: 'AI 知识库', desc: '产品问答 · 术语大白话', icon: 'chat-o', color: 'blue', path: '/rag' },
  ];
  if (auth.docaiAllowed) {
    list.push({ key: 'docai', title: 'AI 文件分析', desc: 'PDF / 图片 → 邮件报告', icon: 'records', color: 'teal', path: '/docai' });
  }
  if (auth.isInternal) {
    list.push({ key: 'proposal', title: '计划书生成', desc: '内部用户 · 自动出 PDF', icon: 'notes-o', color: 'amber', path: '/proposal' });
  }
  list.push({ key: 'cards', title: '保险图文卡', desc: '计划书 → 图文卡片', icon: 'photo-o', color: 'violet', path: '/cards' });
  list.push({ key: 'profile', title: '个人中心', desc: '账号资料与密码', icon: 'user-o', color: 'slate', path: '/profile' });
  return list;
});

function openFeature(f: Feature) {
  if (f.path) router.push(f.path);
}

onMounted(() => {
  if (!auth.docaiChecked) auth.fetchDocaiAccess();
});
</script>

<style scoped>
.home {
  padding-top: calc(20px + env(safe-area-inset-top));
}

.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}
.hello {
  margin: 0;
  font-size: 13px;
  color: var(--app-muted);
}
.name {
  margin: 2px 0 4px;
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text-strong);
  letter-spacing: 0.2px;
}
.sub {
  margin: 0;
  font-size: 12px;
  color: var(--app-faint);
}
.avatar {
  width: 46px;
  height: 46px;
  border-radius: 16px;
  border: 1px solid rgba(74, 158, 255, 0.35);
  background: linear-gradient(145deg, #2a4a7a, #1d2a40);
  color: #cfe3ff;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}

.hero {
  position: relative;
  overflow: hidden;
  border-radius: 22px;
  padding: 18px;
  background: linear-gradient(135deg, #20395c 0%, #182638 55%, #191a22 100%);
  border: 1px solid rgba(110, 160, 230, 0.22);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.35);
}
.hero-glow {
  position: absolute;
  width: 190px;
  height: 190px;
  right: -60px;
  top: -80px;
  border-radius: 50%;
  background: rgba(74, 158, 255, 0.32);
  filter: blur(46px);
}
.hero-body {
  position: relative;
  z-index: 1;
}
.hero-kicker {
  margin: 0 0 8px;
  font-size: 10.5px;
  letter-spacing: 2px;
  color: #8fb6e8;
}
.hero-title {
  margin: 0;
  font-size: 23px;
  font-weight: 700;
  color: #f2f7ff;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 22px 2px 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-strong);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.feature {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  min-height: 120px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid var(--app-border);
  background: var(--app-card);
  text-align: left;
  cursor: pointer;
  transition: transform 0.14s ease, border-color 0.14s ease;
}
.feature:active {
  transform: scale(0.98);
  border-color: var(--app-border-strong);
}
.feature-icon {
  width: 40px;
  height: 40px;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.feature-icon--blue { background: rgba(74, 158, 255, 0.16); color: #6fb4ff; }
.feature-icon--teal { background: rgba(46, 196, 182, 0.16); color: #4fd6c8; }
.feature-icon--violet { background: rgba(150, 110, 255, 0.16); color: #b39bff; }
.feature-icon--amber { background: rgba(240, 168, 59, 0.16); color: #f4c173; }
.feature-icon--green { background: rgba(53, 196, 124, 0.16); color: #6fe0a5; }
.feature-icon--cyan { background: rgba(60, 190, 230, 0.16); color: #6fd6f2; }
.feature-icon--pink { background: rgba(255, 110, 180, 0.16); color: #ff9ecb; }
.feature-icon--orange { background: rgba(255, 140, 70, 0.16); color: #ffb184; }
.feature-icon--slate { background: rgba(160, 170, 190, 0.14); color: #bcc6d8; }

.feature-body {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.feature-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text-strong);
}
.feature-desc {
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-faint);
}
.feature-arrow {
  position: absolute;
  top: 14px;
  right: 12px;
  color: var(--app-faint);
  font-size: 13px;
}
</style>
