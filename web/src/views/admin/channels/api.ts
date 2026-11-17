import { request } from '/@/utils/service';

const apiPrefix = '/api/tenant/tenant/';

// 待审核渠道: 已通过邮箱验证但尚未开通渠道的注册用户
export function GetPending() {
	return request({
		url: `${apiPrefix}pending/`,
		method: 'get',
	});
}

// 手动验证邮箱(超管): 激活账号 → 进入待审核
export function Verify(data: { user_id: number }) {
	return request({
		url: `${apiPrefix}verify/`,
		method: 'post',
		data,
	});
}

// 审核通过: 建渠道 + 绑定经理账号
export function Approve(data: { user_id: number }) {
	return request({
		url: `${apiPrefix}approve/`,
		method: 'post',
		data,
	});
}

// 审核拒绝: 停用该注册账号
export function Reject(data: { user_id: number; reason?: string }) {
	return request({
		url: `${apiPrefix}reject/`,
		method: 'post',
		data,
	});
}
