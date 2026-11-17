import { createI18n } from 'vue-i18n';
import { APP_TITLE } from '/@/config/brand';
import pinia from '/@/stores/index';
import { storeToRefs } from 'pinia';
import { useThemeConfig } from '/@/stores/themeConfig';

// element plus 自带国际化
import enLocale from 'element-plus/es/locale/lang/en';
import zhcnLocale from 'element-plus/es/locale/lang/zh-cn';
import zhtwLocale from 'element-plus/es/locale/lang/zh-tw';
import thLocale from 'element-plus/es/locale/lang/th';

// fast-crud 国际化在 settings.ts 中按需合并(避免首屏加载 fast-crud)

// 定义变量内容
const messages = {};
const element = { en: enLocale, 'zh-cn': zhcnLocale, 'zh-tw': zhtwLocale, th: thLocale };
const itemize: Record<string, any[]> = { en: [], 'zh-cn': [], 'zh-tw': [], th: [] };
const modules: Record<string, any> = import.meta.glob('./**/*.ts', { eager: true });

// 对自动引入的 modules 进行分类 en、zh-cn、zh-tw
// glob 返回路径如: ./pages/login/zh-cn.ts
// 提取语言代码: 按 / 分割，取最后一段去掉 .ts
for (const path in modules) {
	const withoutExt = path.replace(/^\.\//, '').replace(/\.ts$/, '');
	const segs = withoutExt.split('/');
	const lang = segs[segs.length - 1];
	if (itemize[lang]) {
		itemize[lang].push(modules[path].default);
	}
}

// 合并数组对象（深度合并 — 深层 key 冲突时后一个文件的 value 覆盖前一个的 value）
function isObject(val: unknown): val is Record<string, any> {
	return val !== null && typeof val === 'object' && !Array.isArray(val);
}

function deepMerge(target: Record<string, any>, ...sources: Record<string, any>[]): Record<string, any> {
	for (const source of sources) {
		for (const key in source) {
			if (isObject(target[key]) && isObject(source[key])) {
				deepMerge(target[key], source[key]);
			} else {
				target[key] = source[key];
			}
		}
	}
	return target;
}

function mergeArrObj(list: any[], key: string) {
	let obj: Record<string, any> = {};
	list[key].forEach((i: Record<string, any>) => {
		deepMerge(obj, i);
	});
	return obj;
}

for (const key in itemize) {
	messages[key] = {
		name: key,
		el: element[key].el,
		...mergeArrObj(itemize, key),
	};
}

function replaceBrand(node: Record<string, any> | any[]): void {
	if (Array.isArray(node)) {
		node.forEach((item, i) => {
			if (typeof item === 'string') node[i] = item.replaceAll('proNotify', APP_TITLE);
			else if (item && typeof item === 'object') replaceBrand(item);
		});
		return;
	}
	for (const k in node) {
		const v = node[k];
		if (typeof v === 'string') node[k] = v.replaceAll('proNotify', APP_TITLE);
		else if (v && typeof v === 'object') replaceBrand(v);
	}
}

for (const key in messages) replaceBrand(messages[key]);

// 读取 pinia 默认语言
const stores = useThemeConfig(pinia);
const { themeConfig } = storeToRefs(stores);

// 导出语言国际化
export const i18n = createI18n({
	legacy: false,
	silentTranslationWarn: false,
	missingWarn: true,
	silentFallbackWarn: false,
	fallbackWarn: false,
	locale: themeConfig.value.globalI18n,
	fallbackLocale: ['en', 'zh-cn', 'zh-tw'],
	messages,
});