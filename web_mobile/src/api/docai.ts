import { request } from '@/utils/http';
import { withToken } from '@/utils/url';

export function getDocAiAccess() {
  return request<any>({ url: '/api/docai/access/', method: 'get' });
}

export function getDocAiPrompts() {
  return request<any>({ url: '/api/docai/prompts/', method: 'get' });
}

export function analyzeDoc(file: File, email: string, prompt = '') {
  const form = new FormData();
  form.append('file', file);
  form.append('email', email);
  form.append('prompt', prompt);
  return request<any>({
    url: '/api/docai/analyze/',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  });
}

export function listDocAiJobs() {
  return request<any>({ url: '/api/docai/jobs/', method: 'get' });
}

export function getDocAiJob(id: number) {
  return request<any>({ url: `/api/docai/jobs/${id}/`, method: 'get' });
}

export function reportUrl(id: number) {
  return withToken(`/api/docai/jobs/${id}/report/`);
}

export function reportPdfUrl(id: number) {
  return withToken(`/api/docai/jobs/${id}/pdf/`);
}
