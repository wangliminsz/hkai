import { request } from '@/utils/http';

export function updateUserInfo(data: any) {
  return request<any>({ url: '/api/system/user/update_user_info/', method: 'put', data });
}

export function changePassword(data: { oldPassword: string; newPassword: string; newPassword2: string }) {
  return request<any>({ url: '/api/system/user/change_password/', method: 'put', data });
}
