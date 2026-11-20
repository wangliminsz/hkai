const RAW_BASE = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

/**
 * Build an absolute API URL.
 * - dev: VITE_API_URL = '' and Vite proxies /api -> Django
 * - prod: VITE_API_URL = '' and nginx proxies /api -> Django
 * - override: VITE_API_URL = 'https://hkai.favor100.site'
 */
export function apiUrl(path: string): string {
  if (!path) return RAW_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${RAW_BASE}${clean}`;
}

/** Resolve a value returned by the backend that may be absolute, root-relative or a data URL. */
export function resolveAsset(value?: string | null): string {
  if (!value) return '';
  if (/^(https?:|data:|blob:)/i.test(value)) return value;
  if (value.startsWith('/')) return value;
  return `/${value}`;
}

export function withToken(path: string): string {
  const token = window.localStorage.getItem('mhk_token') || '';
  const url = apiUrl(path);
  if (!token) return url;
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
}
