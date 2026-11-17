import { request } from '/@/utils/service';

const base = '/api/cards/admin/companies/';

export function listCompanies() {
	return request({ url: base, method: 'get' });
}

export function createCompany(data: any) {
	return request({ url: base, method: 'post', data });
}

export function updateCompany(id: number, data: any) {
	return request({ url: `${base}${id}/`, method: 'put', data });
}

export function deleteCompany(id: number) {
	return request({ url: `${base}${id}/`, method: 'delete' });
}
