import { request } from '/@/utils/service';

export function getFundSchedule(weekday?: number) {
	return request({ url: '/api/funds/schedule/', method: 'get', params: weekday === undefined ? {} : { weekday } });
}

export function listFundBroadcasts() {
	return request({ url: '/api/funds/broadcasts/', method: 'get' });
}

export function createFundBroadcast(data: any = {}) {
	return request({ url: '/api/funds/broadcasts/', method: 'post', data });
}

export function getFundBroadcast(id: number) {
	return request({ url: `/api/funds/broadcasts/${id}/`, method: 'get' });
}

// Qveris API 额度(基金分析用, 来自 PocketBase qveris_keys)
export function getQverisCredits(refresh = false) {
	return request({
		url: '/api/funds/qveris-credits/',
		method: 'get',
		params: refresh ? { refresh: 1 } : {},
	});
}

// 单基金深度分析(QVeris)
export function createFundAnalysis(data: any = {}) {
	return request({ url: '/api/funds/analysis/', method: 'post', data });
}
export function listFundAnalysis() {
	return request({ url: '/api/funds/analysis/', method: 'get' });
}
