import { request } from '@/utils/http';
import { apiUrl } from '@/utils/url';

export function getPortals() {
  return request<any>({ url: '/api/proposal/portals/', method: 'get' });
}

export function getProposalProducts() {
  return request<any>({ url: '/api/proposal/products/', method: 'get' });
}

export function listProposalJobs() {
  return request<any>({ url: '/api/proposal/jobs/', method: 'get' });
}

export function createProposalJob(data: { portal_id: number | ''; text: string; create_pdf: boolean }) {
  return request<any>({ url: '/api/proposal/jobs/', method: 'post', data });
}

export function getProposalJob(id: number) {
  return request<any>({ url: `/api/proposal/jobs/${id}/`, method: 'get' });
}

export function proposalDownloadHref(job: any): string {
  return job?.download_url ? apiUrl(job.download_url) : '';
}
