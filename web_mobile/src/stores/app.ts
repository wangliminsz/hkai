import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getInitSettings } from '@/api/app';
import { resolveAsset } from '@/utils/url';

const FALLBACK_TITLE = import.meta.env.VITE_APP_TITLE || 'Hongkong HK';
const FALLBACK_LOGO = import.meta.env.VITE_APP_LOGO || '/db_trans.png';
const FALLBACK_FAVICON = import.meta.env.VITE_APP_FAVICON || '/favicon.ico';

function applyFavicon(href: string) {
  if (!href) return;
  let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.href = /^data:/i.test(href) ? href : `${href}${href.includes('?') ? '&' : '?'}v=${Date.now()}`;
}

export const useAppStore = defineStore('app', () => {
  const settings = ref<Record<string, any>>({});
  const loaded = ref(false);
  const loading = ref(false);

  const title = computed<string>(() => settings.value['login.site_title'] || FALLBACK_TITLE);
  const rawLogo = computed<string>(() => settings.value['login.site_logo'] || FALLBACK_LOGO);
  const logo = computed<string>(() => resolveAsset(rawLogo.value));
  const rawFavicon = computed<string>(() => settings.value['login.site_favicon'] || FALLBACK_FAVICON);
  const signInText = computed<string>(
    () => settings.value['login.sign_in_text'] || import.meta.env.VITE_SIGN_IN_TEXT || '港险 AI 智慧系统'
  );

  async function refresh(force = false) {
    if (loaded.value && !force) return settings.value;
    if (loading.value) return settings.value;
    loading.value = true;
    try {
      const res = await getInitSettings();
      settings.value = res?.data || {};
      loaded.value = true;
      document.title = title.value;
      applyFavicon(resolveAsset(rawFavicon.value));
    } catch {
      /* keep fallbacks */
    } finally {
      loading.value = false;
    }
    return settings.value;
  }

  return { settings, loaded, loading, title, logo, rawLogo, rawFavicon, signInText, refresh };
});
