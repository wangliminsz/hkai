import { request } from '/@/utils/service';
import { PageQuery, AddReq, DelReq, EditReq, InfoReq } from '@fast-crud/fast-crud';

export const apiPrefix = '/api/tenant/tenant/';

export function GetList(query: PageQuery) {
	return request({
		url: apiPrefix,
		method: 'get',
		params: query,
	});
}

export function GetObj(id: InfoReq) {
	return request({
		url: apiPrefix + id,
		method: 'get',
	});
}

export function AddObj(obj: AddReq) {
	return request({
		url: apiPrefix,
		method: 'post',
		data: obj,
	});
}

export function UpdateObj(obj: EditReq) {
	return request({
		url: apiPrefix + obj.id + '/',
		method: 'put',
		data: obj,
	});
}

export function DelObj(id: DelReq) {
	return request({
		url: apiPrefix + id + '/',
		method: 'delete',
		data: { id },
	});
}

/**
 * 获取渠道下拉选项(用户管理绑定渠道时使用)
 */
export function getTenantOptions() {
	return request({
		url: apiPrefix + 'options/',
		method: 'get',
	});
}

/**
 * 批量延期: 所有渠道到期时间 +1 年(超管)
 */
export function BatchExtend() {
	return request({
		url: apiPrefix + 'batch_extend/',
		method: 'post',
		timeout: 120000,
	});
}

/**
 * 飞书群通知 webhook(超管): 读取当前链接
 */
export function GetFeishuWebhook() {
	return request({
		url: apiPrefix + 'feishu_webhook/',
		method: 'get',
	});
}

/**
 * 飞书群通知 webhook(超管): 保存链接(留空=停用通知)
 */
export function SaveFeishuWebhook(data: { webhook_url: string }) {
	return request({
		url: apiPrefix + 'feishu_webhook/',
		method: 'post',
		data,
	});
}

/**
 * 超管手动同步某渠道全部已开启日历的房源到 Google 日历(配好服务账号后一键补写)
 */
export function SyncTenantCalendar(id: number) {
	return request({
		url: apiPrefix + id + '/sync_calendar/',
		method: 'post',
		timeout: 120000,
	});
}
