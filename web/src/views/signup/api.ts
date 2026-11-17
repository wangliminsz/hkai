import { request } from '/@/utils/service';

// 渠道自助注册: 发送邮箱验证邮件
export function SendSignup(data: { email: string; company: string; contact_phone?: string; password: string; referral_code?: string }) {
	return request({
		url: '/api/tenant/signup/send/',
		method: 'post',
		data,
	});
}

// 邮箱验证(验证后进入待审核状态, 等待后台开通)
export function VerifySignup(token: string) {
	return request({
		url: '/api/tenant/signup/verify/',
		method: 'post',
		data: { token },
	});
}
