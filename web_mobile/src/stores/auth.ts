import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { storage } from '@/utils/storage';
import { getUserInfo } from '@/api/auth';
import { getDocAiAccess } from '@/api/docai';

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(storage.getToken());
  const user = ref<any>(storage.getUser());
  const docaiAllowed = ref(false);
  const docaiChecked = ref(false);
  const loadingUser = ref(false);
  const validated = ref(false);

  const isLoggedIn = computed(() => !!token.value);
  const roleKeys = computed<string[]>(() =>
    (user.value?.role_info || []).map((r: any) => r?.key).filter(Boolean)
  );
  const isInternal = computed(() => roleKeys.value.includes('internal') || !!user.value?.is_superuser);
  const isTenantManager = computed(() => roleKeys.value.includes('tenant_manager'));
  const isSuperuser = computed(() => !!user.value?.is_superuser);
  const hasTenant = computed(() => !!user.value?.tenant_id);
  const displayName = computed(() => user.value?.name || user.value?.username || '用户');
  const needsPasswordChange = computed(() => (user.value?.pwd_change_count || 0) === 0);

  function setToken(value: string) {
    token.value = value || '';
    storage.setToken(token.value);
  }

  function setUser(value: any) {
    user.value = value || null;
    storage.setUser(user.value);
  }

  async function fetchUser(force = false) {
    if (!token.value) return null;
    if (user.value && validated.value && !force) return user.value;
    loadingUser.value = true;
    try {
      const res = await getUserInfo();
      setUser(res?.data || null);
      validated.value = true;
      return user.value;
    } finally {
      loadingUser.value = false;
    }
  }

  async function fetchDocaiAccess(force = false) {
    if (docaiChecked.value && !force) return docaiAllowed.value;
    try {
      const res = await getDocAiAccess();
      docaiAllowed.value = !!res?.data?.allowed;
    } catch {
      docaiAllowed.value = false;
    } finally {
      docaiChecked.value = true;
    }
    return docaiAllowed.value;
  }

  function clear() {
    token.value = '';
    user.value = null;
    docaiAllowed.value = false;
    docaiChecked.value = false;
    validated.value = false;
    storage.clearAuth();
  }

  return {
    token,
    user,
    isLoggedIn,
    roleKeys,
    isInternal,
    isTenantManager,
    isSuperuser,
    hasTenant,
    displayName,
    needsPasswordChange,
    docaiAllowed,
    docaiChecked,
    loadingUser,
    setToken,
    setUser,
    fetchUser,
    fetchDocaiAccess,
    clear,
  };
});
