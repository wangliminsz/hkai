<template>
  <div class="page--with-nav">
    <AppNav title="个人资料" back-to="/profile" />

    <section class="card">
      <van-cell-group :border="false" class="form-group">
        <van-field v-model="form.name" label="姓名" placeholder="请输入姓名" maxlength="40" />
        <van-field v-model="form.email" label="邮箱" placeholder="name@example.com" type="email" />
        <van-field v-model="form.mobile" label="手机" placeholder="选填" type="tel" maxlength="50" />
        <van-field
          v-model="genderLabel"
          label="性别"
          placeholder="请选择"
          readonly
          is-link
          @click="genderPicker = true"
        />
      </van-cell-group>

      <van-cell-group :border="false" class="readonly">
        <van-cell title="账号" :value="auth.user?.username || '—'" />
        <van-cell title="渠道" :value="auth.user?.tenant_name || '—'" />
        <van-cell title="部门" :value="auth.user?.dept_info?.dept_name || '—'" />
      </van-cell-group>

      <p v-if="error" class="err-text">{{ error }}</p>

      <van-button
        block
        round
        type="primary"
        size="large"
        class="save"
        :loading="saving"
        loading-text="保存中…"
        @click="save"
      >
        保存
      </van-button>
    </section>

    <van-popup v-model:show="genderPicker" position="bottom" round>
      <van-picker
        :columns="genderColumns"
        @cancel="genderPicker = false"
        @confirm="onGenderConfirm"
      />
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showToast } from 'vant';
import AppNav from '@/components/AppNav.vue';
import { useAuthStore } from '@/stores/auth';
import { updateUserInfo } from '@/api/user';

const auth = useAuthStore();
const router = useRouter();

const form = reactive({ name: '', email: '', mobile: '', gender: 0 });
const genderPicker = ref(false);
const saving = ref(false);
const error = ref('');

const genderColumns = [
  { text: '未知', value: 0 },
  { text: '男', value: 1 },
  { text: '女', value: 2 },
];

const genderLabel = ref('未知');

function syncGenderLabel() {
  const found = genderColumns.find((g) => g.value === Number(form.gender));
  genderLabel.value = found?.text || '未知';
}

function onGenderConfirm({ selectedOptions }: any) {
  form.gender = selectedOptions?.[0]?.value ?? 0;
  syncGenderLabel();
  genderPicker.value = false;
}

function fill() {
  const u = auth.user || {};
  form.name = u.name || '';
  form.email = u.email || '';
  form.mobile = u.mobile || '';
  form.gender = Number(u.gender ?? 0);
  syncGenderLabel();
}

async function save() {
  if (saving.value) return;
  error.value = '';
  if (!form.name.trim()) {
    error.value = '请填写姓名';
    return;
  }
  if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    error.value = '邮箱格式不正确';
    return;
  }
  saving.value = true;
  try {
    await updateUserInfo({
      name: form.name.trim(),
      email: form.email.trim(),
      mobile: form.mobile.trim(),
      gender: Number(form.gender),
    });
    await auth.fetchUser(true);
    showToast({ type: 'success', message: '资料已更新' });
    router.replace('/profile');
  } catch (e: any) {
    error.value = e?.message || '保存失败';
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    await auth.fetchUser(true);
  } catch {
    /* keep cached */
  }
  fill();
});
</script>

<style scoped>
.form-group,
.readonly {
  background: var(--app-card-2);
  border: 1px solid var(--app-border);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 12px;
}
.form-group :deep(.van-field),
.readonly :deep(.van-cell) {
  background: transparent;
}
.form-group :deep(.van-field__label),
.readonly :deep(.van-cell__title) {
  color: var(--app-muted);
}
.readonly :deep(.van-cell__value) {
  color: var(--app-text);
}
.save {
  margin-top: 8px;
  height: 48px;
}
</style>
