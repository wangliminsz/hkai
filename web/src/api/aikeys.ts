import { request } from '/@/utils/service';

const base = '/api/aikeys';

export function listAiKeys(params: any = {}) {
	return request({ url: `${base}/keys/`, method: 'get', params });
}

export function createAiKey(data: any) {
	return request({ url: `${base}/keys/`, method: 'post', data });
}

export function updateAiKey(id: number, data: any) {
	return request({ url: `${base}/keys/${id}/`, method: 'patch', data });
}

export function deleteAiKey(id: number) {
	return request({ url: `${base}/keys/${id}/`, method: 'delete' });
}

export function testAiKey(id: number) {
	return request({ url: `${base}/keys/${id}/test/`, method: 'post' });
}

export function getAiCredits(params: any = {}) {
	return request({ url: `${base}/credits/`, method: 'get', params });
}

export function getAiOverview() {
	return request({ url: `${base}/overview/`, method: 'get' });
}

export function getAiKeySettings() {
	return request({ url: `${base}/settings/`, method: 'get' });
}

export function updateAiKeySettings(data: any) {
	return request({ url: `${base}/settings/`, method: 'patch', data });
}
