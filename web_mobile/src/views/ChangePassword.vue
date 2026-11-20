<template>
  <div :class="isFirst ? 'first-page' : 'page--with-nav'" class="cp-page">
    <AppNav v-if="!isFirst" title="修改密码" back-to="/profile" />

    <div v-if="isFirst" class="first-head">
      <img :src="app.logo" class="logo" alt="logo" />
      <h1>首次登录 · 修改密码</h1>
      <p>为了账号安全，请先设置一个新的登录密码。</p>
    </div>

    <section class="card form-card">
      <div class="field-block">
        <label>{{ isFirst ? '新密码' : '当前密码' }}</label>
        <van-field
          v-model="oldPassword"
          class="soft-field"
          :type="show1 ? 'text' : 'password'"
          :placeholder="isFirst ? '8-30 位，需包含字母和数字' : '请输入当前密码'"
          left-icon="lock"
          :right-icon="show1 ? 'eye-o' : 'closed-eye'"
          @click-right-icon="show1 = !show1"
        />
      </div>

      <div v-if="!isFirst" class="field-block">
        <label>新密码</label>
        <van-field
          v-model="newPassword"
          class="soft-field"
          :type="show2 ? 'text' : 'password'"
          placeholder="8-30 位，需包含字母和数字"
          left-icon="shield-o"
          :right-icon="show2 ? 'eye-o' : 'closed-eye'"
          @click-right-icon="show2 = !show2"
        />
      </div>

      <div class="field-block">
        <label>{{ isFirst ? '确认新密码' : '确认密码' }}</label>
        <van-field
          v-model="confirmPassword"
          class="soft-field"
          :type="show2 ? 'text' : 'password'"
          placeholder="请再次输入新密码"
          left-icon="shield-o"
          :right-icon="show2 ? 'eye-o' : 'closed-eye'"
          @click-right-icon="show2 = !show2"
          @keyup.enter="submit"
        />
      </div>

      <p v-if="error" class="err-text">{{ error }}</p>

      <van-button
        block
        round
        type="primary"
        size="large"
        class="submit"
        :loading="loading"
        loading-text="提交中…"
        @click="submit"
      >
        确认修改
      </van-button>

      <div v-if="isFirst" class="first-foot">
        <span @click="logout">退出登录，换个账号</span>
      </div>
    </section>

    <p v-if="isFirst" class="tip">登录后你也可以在「我的 → 修改密码」中再次修改密码。</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showToast } from 'vant';
import AppNav from '@/components/AppNav.vue';
import { useAppStore } from '@/stores/app';
import { useAuthStore } from '@/stores/auth';
import { loginChangePassword } from '@/api/auth';
import { changePassword } from '@/api/user';
import { md5 } from '@/utils/md5';

const app = useAppStore();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const isFirst = ref(auth.needsPasswordChange || route.query.first === '1');

const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const show1 = ref(false);
const show2 = ref(false);
const loading = ref(false);
const error = ref('');

const PWD_RE = /^(?=.*[0-9])(?=.*[a-zA-Z]).{8,30}$/;

function logout() {
  auth.clear();
  router.replace('/login');
}

async function submit() {
  if (loading.value) return;
  error.value = '';

  const pwd = isFirst.value ? oldPassword.value : newPassword.value;
  const confirm = confirmPassword.value;

  if (!isFirst.value && !oldPassword.value) {
    error.value = '请输入当前密码';
    return;
  }
  if (!pwd) {
    error.value = '请输入新密码';
    return;
  }
  if (!PWD_RE.test(pwd)) {
    error.value = '密码需为 8-30 位，且同时包含字母和数字';
    return;
  }
  if (!confirm) {
    error.value = '请再次输入新密码';
    return;
  }
  if (confirm !== pwd) {
    error.value = '两次输入的新密码不一致';
    return;
  }

  loading.value = true;
  try {
    if (isFirst.value) {
      await loginChangePassword({ password: md5(pwd), password_regain: md5(confirm) });
      await auth.fetchUser(true);
      showToast({ type: 'success', message: '密码已更新' });
      router.replace('/home');
    } else {
      await changePassword({
        oldPassword: oldPassword.value,
        newPassword: pwd,
        newPassword2: confirm,
      });
      showToast({ type: 'success', message: '密码已更新，请重新登录' });
      auth.clear();
      setTimeout(() => router.replace('/login'), 600);
    }
  } catch (e: any) {
    error.value = e?.message || '修改失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.cp-page {
  min-height: 100dvh;
  background: var(--app-bg);
}

.first-page {
  padding: calc(40px + env(safe-area-inset-top)) 18px 28px;
  display: flex;
  flex-direction: column;
  background: radial-gradient(120% 70% at 50% -10%, #1b2a44 0%, #141419 50%, #101013 100%);
}

.first-head {
  text-align: center;
  margin-bottom: 22px;
}
.first-head .logo {
  width: 150px;
  display: block;
  margin: 0 auto 18px;
}
.first-head h1 {
  margin: 0;
  font-size: 22px;
  color: #f4f7fb;
  font-weight: 700;
}
.first-head p {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: #8ea2bd;
  line-height: 1.6;
}

.form-card {
  padding: 20px 16px 18px;
}

.field-block {
  margin-bottom: 16px;
}
.field-block label {
  display: block;
  margin: 0 0 8px 4px;
  font-size: 12.5px;
  color: var(--app-muted);
}
.soft-field {
  background: var(--app-card-2);
  border: 1px solid var(--app-border-strong);
  border-radius: 14px;
  padding: 12px;
}
.soft-field:focus-within {
  border-color: rgba(74, 158, 255, 0.65);
  box-shadow: 0 0 0 3px rgba(74, 158, 255, 0.12);
}
.submit {
  margin-top: 8px;
  height: 48px;
}
.first-foot {
  margin-top: 16px;
  text-align: center;
  font-size: 12.5px;
  color: var(--app-faint);
}
.first-foot span {
  cursor: pointer;
}
.tip {
  margin: 18px 8px 0;
  text-align: center;
  font-size: 11.5px;
  color: var(--app-faint);
  line-height: 1.6;
}
</style>
