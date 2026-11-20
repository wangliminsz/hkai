import axios, { type AxiosRequestConfig } from 'axios';
import { storage } from './storage';

const RAW_BASE = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

const service = axios.create({
  baseURL: RAW_BASE || undefined,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
});

service.interceptors.request.use((config) => {
  const token = storage.getToken();
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `JWT ${token}`;
  }
  config.headers = config.headers || {};
  (config.headers as any)['Accept-Language'] = storage.getLang();
  return config;
});

function extractMsg(body: any): string {
  if (!body) return '';
  if (typeof body === 'string') return body.slice(0, 300);
  if (body.msg) return String(body.msg);
  if (body.message) return String(body.message);
  if (body.detail) return String(body.detail);
  for (const key of Object.keys(body)) {
    const v = (body as any)[key];
    if (typeof v === 'string' && v) return v;
    if (Array.isArray(v) && v.length) return String(v[0]);
    if (v && typeof v === 'object') {
      const nested = extractMsg(v);
      if (nested) return nested;
    }
  }
  return '';
}

function handleUnauthorized() {
  storage.clearAuth();
  if (!window.location.hash.startsWith('#/login')) {
    window.location.hash = '#/login';
  }
}

function unwrap(body: any) {
  if (body && typeof body.code !== 'undefined') {
    if (body.code === 2000 || body.code === 0) return body;
    if (body.code === 401 || body.code === 4001) {
      handleUnauthorized();
      throw new Error(body.msg || '登录已过期，请重新登录');
    }
    throw new Error(extractMsg(body) || '请求失败');
  }
  return body;
}

/** Request helper: resolves the parsed body on business success, throws Error otherwise. */
export async function request<T = any>(config: AxiosRequestConfig): Promise<T> {
  try {
    const res = await service(config);
    return unwrap(res.data) as T;
  } catch (e: any) {
    if (e?.response?.data && typeof e.response.data === 'object') {
      const body = e.response.data;
      if (typeof body.code !== 'undefined') {
        return unwrap(body) as T;
      }
      const msg = extractMsg(body);
      if (e.response.status === 401) handleUnauthorized();
      throw new Error(msg || `请求失败 (${e.response.status})`);
    }
    if (e?.message === 'Network Error') {
      throw new Error('网络连接失败，请检查网络后重试');
    }
    if (String(e?.message || '').toLowerCase().includes('timeout')) {
      throw new Error('请求超时，请稍后重试');
    }
    throw new Error(e?.message || '请求失败');
  }
}

/** Raw axios instance for special cases (blobs, multipart with custom handling). */
export { service as http };
