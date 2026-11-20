import { request } from '@/utils/http';

export function getCaptcha() {
  return request<any>({ url: '/api/captcha/', method: 'get' });
}

export function login(data: { username: string; password: string; captcha?: string; captchaKey?: string | number }) {
  return request<any>({ url: '/api/login/', method: 'post', data });
}

export function getUserInfo() {
  return request<any>({ url: '/api/system/user/user_info/', method: 'get' });
}

export function loginChangePassword(data: { password: string; password_regain: string }) {
  return request<any>({ url: '/api/system/user/login_change_password/', method: 'post', data });
}

export function updateLanguage(language: string) {
  return request<any>({ url: '/api/system/user/update_language/', method: 'put', data: { language } });
}

export function sendResetEmail(email: string) {
  return request<any>({ url: '/api/system/user_reset/send/', method: 'post', data: { email } });
}

export function confirmReset(token: string, password: string) {
  return request<any>({ url: '/api/system/user_reset/confirm/', method: 'post', data: { token, password } });
}
