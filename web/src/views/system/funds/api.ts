import { request } from '/@/utils/service';

const base = '/api/funds/groups/';

export function listFundGroups() {
	return request({ url: base, method: 'get' });
}

export function createFundGroup(data: any) {
	return request({ url: base, method: 'post', data });
}

export function updateFundGroup(id: number, data: any) {
	return request({ url: `${base}${id}/`, method: 'put', data });
}

export function deleteFundGroup(id: number) {
	return request({ url: `${base}${id}/`, method: 'delete' });
}
