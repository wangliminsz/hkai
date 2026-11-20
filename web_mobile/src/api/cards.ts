import { request } from '@/utils/http';
import { apiUrl } from '@/utils/url';
import { storage } from '@/utils/storage';

export function getCardProducts(includeDrafts = false) {
  return request<any>({
    url: '/api/cards/products/',
    method: 'get',
    params: includeDrafts ? { include_drafts: 1 } : {},
  });
}

export function detectCard(file: File, product = '') {
  const fd = new FormData();
  fd.append('file', file);
  if (product) fd.append('product', product);
  return request<any>({
    url: '/api/cards/detect/',
    method: 'post',
    data: fd,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  });
}

export function createCardJob(fd: FormData) {
  return request<any>({
    url: '/api/cards/jobs/',
    method: 'post',
    data: fd,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  });
}

export function listCardJobs() {
  return request<any>({ url: '/api/cards/jobs/', method: 'get' });
}

export function getCardJob(id: number) {
  return request<any>({ url: `/api/cards/jobs/${id}/`, method: 'get' });
}

async function authFetch(path: string) {
  const token = storage.getToken();
  return fetch(apiUrl(path), {
    headers: token ? { Authorization: `JWT ${token}` } : {},
  });
}

export async function fetchCardBlobUrl(id: number, idx: number): Promise<string> {
  const res = await authFetch(`/api/cards/jobs/${id}/card/${idx}/`);
  if (!res.ok) throw new Error(`预览失败 (${res.status})`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function downloadCardsZip(id: number, filename: string) {
  const res = await authFetch(`/api/cards/jobs/${id}/zip/`);
  const ct = res.headers.get('content-type') || '';
  if (!res.ok || !ct.includes('application/zip')) {
    let msg = `下载失败 (${res.status})`;
    try {
      const b = await res.json();
      if (b?.msg) msg = b.msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'cards.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
