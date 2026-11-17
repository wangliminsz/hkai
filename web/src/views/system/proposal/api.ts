import { request } from '/@/utils/service';

export function getPortals() {
	return request({ url: '/api/proposal/portals/', method: 'get' });
}

export function getProducts() {
	return request({ url: '/api/proposal/products/', method: 'get' });
}

export function listJobs() {
	return request({ url: '/api/proposal/jobs/', method: 'get' });
}

export function createJob(data: { portal_id: number | ''; text: string; create_pdf: boolean }) {
	return request({ url: '/api/proposal/jobs/', method: 'post', data });
}

export function getJob(id: number) {
	return request({ url: `/api/proposal/jobs/${id}/`, method: 'get' });
}

