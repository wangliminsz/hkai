import { computed } from 'vue';
import { defineStore } from 'pinia';
import { SystemConfigStore } from './systemConfig';
import { APP_FAVICON, APP_LOGO, APP_TITLE } from '/@/config/brand';

/**
 * 运行时品牌(名称 + Logo + Favicon)。
 * 数据源: system_config login.site_title / login.site_logo / login.site_favicon（超管页可改）。
 * 未配置时回退到构建时 env 默认值。
 */
export const useBrandStore = defineStore('Brand', () => {
	const systemConfigStore = SystemConfigStore();

	const title = computed(() => {
		const value = String(systemConfigStore.systemConfig?.['login.site_title'] ?? '').trim();
		return value || APP_TITLE;
	});

	const logo = computed(() => {
		const value = String(systemConfigStore.systemConfig?.['login.site_logo'] ?? '').trim();
		return value || APP_LOGO;
	});

	const favicon = computed(() => {
		const value = String(systemConfigStore.systemConfig?.['login.site_favicon'] ?? '').trim();
		return value || APP_FAVICON;
	});

	const defaultTitle = APP_TITLE;
	const defaultLogo = APP_LOGO;
	const defaultFavicon = APP_FAVICON;

	/** 保存后立即应用，无需刷新页面 */
	const apply = (data: { title?: string; logo?: string; favicon?: string } = {}) => {
		if (!systemConfigStore.systemConfig) systemConfigStore.systemConfig = {};
		systemConfigStore.systemConfig['login.site_title'] = data.title ?? '';
		systemConfigStore.systemConfig['login.site_logo'] = data.logo ?? '';
		systemConfigStore.systemConfig['login.site_favicon'] = data.favicon ?? '';
	};

	/** 从后端重新拉取 system_config（公开接口） */
	const refresh = () => systemConfigStore.getSystemConfigs();

	return { title, logo, favicon, defaultTitle, defaultLogo, defaultFavicon, apply, refresh };
});
