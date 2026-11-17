import { request } from '/@/utils/service';

// 内部用户(超管)
export function listUsers(keyword = '') {
	return request({ url: '/api/proposal/admin/internal-users/', method: 'get', params: { keyword } });
}

export function setInternal(user_id: number, internal: boolean) {
	return request({ url: '/api/proposal/admin/internal-users/', method: 'post', data: { user_id, internal } });
}
