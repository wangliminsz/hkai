import { request } from '/@/utils/service';

const base = '/api/proposal/admin/portals/';

// 保险公司门户列表(超管)
export function listPortals() {
	return request({ url: base, method: 'get' });
}

export function createPortal(data: any) {
	return request({ url: base, method: 'post', data });
}

export function updatePortal(id: number, data: any) {
	return request({ url: `${base}${id}/`, method: 'put', data });
}

export function deletePortal(id: number) {
	return request({ url: `${base}${id}/`, method: 'delete' });
}
