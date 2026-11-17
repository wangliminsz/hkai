import { request } from '/@/utils/service';
import { Session } from '/@/utils/storage';
import { getBaseURL } from '/@/utils/baseUrl';

export function listAdminProducts() {
	return request({ url: '/api/cards/admin/products/', method: 'get' });
}

export function saveTemplate(pid: string, template: any) {
	return request({ url: `/api/cards/admin/products/${pid}/template/`, method: 'put', data: { content: template } });
}

export function saveParser(pid: string, parser: any) {
	return request({ url: `/api/cards/admin/products/${pid}/parser/`, method: 'put', data: { content: parser } });
}

export function previewCard(pid: string, cardIdx: number, edits: any = {}, sampleData: any = null) {
	return request({
		url: '/api/cards/admin/preview/',
		method: 'post',
		data: { product: pid, card_idx: cardIdx, style: 'llm', edits, sample_data: sampleData },
		timeout: 60000,
	});
}

export function uploadAsset(file: File) {
	const fd = new FormData();
	fd.append('file', file);
	return request({
		url: '/api/cards/admin/upload-asset/',
		method: 'post',
		data: fd,
		headers: { 'Content-Type': 'multipart/form-data' },
		timeout: 120000,
	});
}

export async function fetchAssetBlobUrl(path: string): Promise<string> {
	const token = Session.get('token');
	const res = await fetch(getBaseURL(`api/cards/admin/asset/?path=${encodeURIComponent(path)}`), {
		headers: token ? { Authorization: `JWT ${token}` } : {},
	});
	if (!res.ok) throw new Error('资源加载失败');
	return URL.createObjectURL(await res.blob());
}

export function aiDraft(fd: FormData) {
	return request({
		url: '/api/cards/admin/products/ai-draft/',
		method: 'post',
		data: fd,
		headers: { 'Content-Type': 'multipart/form-data' },
		timeout: 600000,
	});
}

export function validateDraft(pid: string) {
	return request({ url: `/api/cards/admin/products/${pid}/validate/`, method: 'post' });
}

export function publishDraft(pid: string) {
	return request({ url: `/api/cards/admin/products/${pid}/publish/`, method: 'post' });
}

export function renameProduct(pid: string, new_id: string) {
	return request({ url: `/api/cards/admin/products/${pid}/rename/`, method: 'post', data: { new_id } });
}

export function listCompanies() {
	return request({ url: '/api/cards/admin/companies/', method: 'get' });
}

export function createCompany(data: any) {
	return request({ url: '/api/cards/admin/companies/', method: 'post', data });
}

export function deleteCompany(id: number) {
	return request({ url: `/api/cards/admin/companies/${id}/`, method: 'delete' });
}
