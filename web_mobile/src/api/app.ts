import { request } from '@/utils/http';

export function getInitSettings() {
  return request<any>({ url: '/api/init/settings/', method: 'get' });
}
