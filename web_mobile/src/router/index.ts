import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useAppStore } from '@/stores/app';

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/views/ChangePassword.vue'),
    meta: { title: '修改密码' },
  },
  {
    path: '/home',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { tab: true, title: '工作台' },
  },
  {
    path: '/rag',
    name: 'rag',
    component: () => import('@/views/Rag.vue'),
    meta: { tab: true, title: 'AI 知识库' },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/Profile.vue'),
    meta: { tab: true, title: '个人中心' },
  },
  {
    path: '/profile/edit',
    name: 'profile-edit',
    component: () => import('@/views/ProfileEdit.vue'),
    meta: { title: '个人资料' },
  },
  {
    path: '/cards',
    name: 'cards',
    component: () => import('@/views/Cards.vue'),
    meta: { title: '保险图文卡' },
  },
  {
    path: '/docai',
    name: 'docai',
    component: () => import('@/views/DocAi.vue'),
    meta: { title: 'AI 文件分析' },
  },
  {
    path: '/proposal',
    name: 'proposal',
    component: () => import('@/views/Proposal.vue'),
    meta: { title: '计划书生成', internal: true },
  },
  {
    path: '/desktop',
    name: 'desktop',
    component: () => import('@/views/DesktopOnly.vue'),
    meta: { title: '电脑版功能' },
  },
  { path: '/', redirect: '/home' },
  { path: '/:pathMatch(.*)*', redirect: '/home' },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

let brandReady = false;

router.beforeEach(async (to) => {
  const app = useAppStore();
  if (!brandReady) {
    brandReady = true;
    await app.refresh();
  }

  const auth = useAuthStore();

  if (to.meta.public) {
    if (to.path === '/login' && auth.isLoggedIn) {
      try {
        await auth.fetchUser();
        if (auth.needsPasswordChange) return '/change-password';
        return '/home';
      } catch {
        auth.clear();
        return true;
      }
    }
    return true;
  }

  if (!auth.token) {
    return { path: '/login', query: { redirect: to.fullPath } };
  }

  try {
    await auth.fetchUser();
  } catch {
    auth.clear();
    return { path: '/login', query: { redirect: to.fullPath } };
  }

  if (auth.needsPasswordChange && to.path !== '/change-password') {
    return '/change-password';
  }

  if (to.meta.internal && !auth.isInternal) {
    return '/home';
  }

  return true;
});

router.afterEach((to) => {
  const app = useAppStore();
  const base = app.title || 'Hongkong HK';
  document.title = to.meta.title ? `${to.meta.title} · ${base}` : base;
});

export default router;
