<template>
  <div class="login">
    <div class="glow glow--a"></div>
    <div class="glow glow--b"></div>

    <header class="brand">
      <img :src="app.logo" class="brand-logo" alt="logo" />
      <h1 class="brand-title">{{ app.signInText }}</h1>
      <p class="brand-sub">{{ app.title }} · 移动版</p>
    </header>

    <section class="form-card">
      <div class="field-block">
        <label>账号</label>
        <van-field
          v-model="username"
          class="soft-field"
          placeholder="用户名 / 邮箱 / 手机号"
          left-icon="user-o"
          clearable
          autocomplete="username"
          @keyup.enter="submit"
        />
      </div>

      <div class="field-block">
        <label>密码</label>
        <van-field
          v-model="password"
          class="soft-field"
          :type="showPassword ? 'text' : 'password'"
          placeholder="请输入密码"
          left-icon="lock"
          :right-icon="showPassword ? 'eye-o' : 'closed-eye'"
          autocomplete="current-password"
          @click-right-icon="showPassword = !showPassword"
          @keyup.enter="submit"
        />
      </div>

      <div v-if="captchaImg" class="field-block">
        <label>验证码</label>
        <div class="captcha-row">
          <van-field
            v-model="captcha"
            class="soft-field"
            placeholder="请输入右侧验证码"
            left-icon="shield-o"
            maxlength="6"
            @keyup.enter="submit"
          />
          <button class="captcha-img" type="button" @click="loadCaptcha">
            <img :src="captchaImg" alt="captcha" />
          </button>
        </div>
      </div>

      <van-button
        block
        round
        type="primary"
        size="large"
        class="submit"
        :loading="loading"
        loading-text="登录中…"
        @click="submit"
      >
        登 录
      </van-button>

      <div class="links">
        <span @click="goDesktop">忘记密码？</span>
        <span @click="goDesktop">使用电脑版</span>
      </div>
    </section>

    <footer class="foot">© 2026-2028 {{ app.title }} · All rights reserved</footer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showToast } from 'vant';
import { useAppStore } from '@/stores/app';
import { useAuthStore } from '@/stores/auth';
import { getCaptcha, login } from '@/api/auth';
import { md5 } from '@/utils/md5';

const app = useAppStore();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const username = ref('');
const password = ref('');
const captcha = ref('');
const captchaKey = ref<string | number>('');
const captchaImg = ref('');
const showPassword = ref(false);
const loading = ref(false);

const DESKTOP_URL = (import.meta.env.VITE_DESKTOP_URL as string) || 'https://hkai.favor100.site';

async function loadCaptcha() {
  try {
    const res = await getCaptcha();
    const data = res?.data || {};
    if (data.image_base) {
      captchaImg.value = data.image_base;
      captchaKey.value = data.key;
      captcha.value = '';
    } else {
      captchaImg.value = '';
    }
  } catch {
    captchaImg.value = '';
  }
}

function goDesktop() {
  window.open(DESKTOP_URL, '_blank');
}

async function submit() {
  if (loading.value) return;
  const name = username.value.trim();
  if (!name) return showToast('请输入账号');
  if (!password.value) return showToast('请输入密码');
  if (captchaImg.value && !captcha.value.trim()) return showToast('请输入验证码');

  loading.value = true;
  try {
    const payload: any = { username: name, password: md5(password.value) };
    if (captchaImg.value) {
      payload.captcha = captcha.value.trim();
      payload.captchaKey = captchaKey.value;
    }
    const res = await login(payload);
    const data = res?.data || {};
    if (!data.access) throw new Error('登录返回异常，请稍后重试');

    auth.setToken(data.access);
    await auth.fetchUser(true);

    if (auth.needsPasswordChange) {
      router.replace('/change-password');
      return;
    }

    showToast({ type: 'success', message: '登录成功' });
    const redirect = (route.query.redirect as string) || '';
    router.replace(redirect && redirect !== '/login' ? redirect : '/home');
  } catch (e: any) {
    showToast(e?.message || '登录失败');
    await loadCaptcha();
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  app.refresh();
  await loadCaptcha();
});
</script>

<style scoped>
.login {
  position: relative;
  min-height: 100dvh;
  padding: calc(52px + env(safe-area-inset-top)) 22px 28px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: radial-gradient(120% 80% at 50% -10%, #1b2a44 0%, #141419 48%, #101013 100%);
}

.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.55;
  pointer-events: none;
}
.glow--a {
  width: 240px;
  height: 240px;
  top: -90px;
  right: -60px;
  background: rgba(74, 158, 255, 0.45);
}
.glow--b {
  width: 260px;
  height: 260px;
  bottom: -120px;
  left: -90px;
  background: rgba(120, 90, 255, 0.22);
}

.brand {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 8px 0 26px;
}
.brand-logo {
  width: 172px;
  height: auto;
  margin: 0 auto 18px;
  display: block;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.45));
}
.brand-title {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #f4f7fb;
}
.brand-sub {
  margin: 8px 0 0;
  font-size: 12.5px;
  letter-spacing: 1px;
  color: #8ea2bd;
}

.form-card {
  position: relative;
  z-index: 1;
  background: rgba(28, 28, 33, 0.86);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 22px;
  padding: 22px 18px 18px;
  backdrop-filter: blur(18px);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
}

.field-block {
  margin-bottom: 16px;
}
.field-block label {
  display: block;
  margin: 0 0 8px 4px;
  font-size: 12.5px;
  color: #9aa3af;
}

.soft-field {
  --van-field-input-text-color: #eef2f7;
  background: #202027;
  border: 1px solid #2e2e37;
  border-radius: 14px;
  padding: 12px 12px;
}
.soft-field:focus-within {
  border-color: rgba(74, 158, 255, 0.65);
  box-shadow: 0 0 0 3px rgba(74, 158, 255, 0.12);
}

.captcha-row {
  display: flex;
  gap: 10px;
  align-items: stretch;
}
.captcha-row .soft-field {
  flex: 1;
}
.captcha-img {
  flex: 0 0 116px;
  padding: 0;
  border: 1px solid #2e2e37;
  border-radius: 14px;
  overflow: hidden;
  background: #202027;
  cursor: pointer;
}
.captcha-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.submit {
  margin-top: 6px;
  height: 50px;
  font-size: 16px;
  letter-spacing: 4px;
}

.links {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  padding: 0 4px;
  font-size: 12.5px;
  color: #7f8b9b;
}
.links span {
  cursor: pointer;
}

.foot {
  position: relative;
  z-index: 1;
  margin-top: auto;
  padding-top: 24px;
  text-align: center;
  font-size: 11.5px;
  color: #5f6673;
}
</style>
