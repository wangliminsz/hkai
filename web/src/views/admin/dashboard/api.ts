import { request } from '/@/utils/service';

// 概览 Dashboard 统计
export interface DashboardStat {
	tenant_total: number;
	tenant_trial: number;
	tenant_paid: number;
	tenant_active: number;
	bot_total: number;
	bot_active: number;
	msg_total: number;
}

export function getDashboardStat() {
	return request({
		url: '/api/tenant/admin/dashboard/',
		method: 'get',
	});
}

// 环境配置概览(超管): 常用 .env 值(密钥已脱敏)
export interface EnvConfigGroup {
	group: string;
	items: { key: string; label: string; value: string }[];
}
export function getEnvConfig() {
	return request({
		url: '/api/tenant/admin/env/',
		method: 'get',
	});
}

// 渠道下拉选项
export function getTenantOptions() {
	return request({
		url: '/api/tenant/tenant/options/',
		method: 'get',
	});
}

// 每日提醒发送时间(运行时配置)
export function getNotifySchedule() {
	return request({
		url: '/api/notify/schedule/',
		method: 'get',
	});
}

export function updateNotifySchedule(hour: number, minute = 0, dedup?: boolean) {
	return request({
		url: '/api/notify/schedule/',
		method: 'post',
		data: { hour, minute, ...(typeof dedup === 'boolean' ? { dedup } : {}) },
	});
}

// 提醒消息模板(运行时配置, 空串=恢复内置默认)
export function updateNotifyMessageTemplates(rentTemplate?: string, maturityTemplate?: string) {
	const data: Record<string, string> = {};
	if (typeof rentTemplate === 'string') data.rent_template = rentTemplate;
	if (typeof maturityTemplate === 'string') data.maturity_template = maturityTemplate;
	return request({
		url: '/api/notify/schedule/',
		method: 'post',
		data,
	});
}

// AI 助手模型配置(可切换, 已存库)
export function getAIConfig() {
	return request({
		url: '/api/property/ai/config/',
		method: 'get',
	});
}

export function updateAIConfig(obj: any) {
	return request({
		url: '/api/property/ai/config/',
		method: 'put',
		data: obj,
	});
}

// Qveris API 额度(基金分析用, 来自 PocketBase qveris_keys)
export interface QverisKey {
	id: string;
	key_env: string;
	login_name: string;
	masked_key: string;
	remain_credit: number;
}
export interface QverisCredits {
	fetched_at: string;
	count: number;
	total: number;
	lowest: number | null;
	items: QverisKey[];
}
export function getQverisCredits(refresh = false) {
	return request({
		url: '/api/funds/qveris-credits/',
		method: 'get',
		params: refresh ? { refresh: 1 } : {},
	});
}

// AI 文件分析权限开关
export function getDocAiSettings() {
	return request({ url: '/api/docai/settings/', method: 'get' });
}
export function updateDocAiSettings(data: any) {
	return request({ url: '/api/docai/settings/', method: 'put', data });
}
