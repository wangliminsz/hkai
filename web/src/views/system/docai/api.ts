import { request } from '/@/utils/service';

export function getDocAiAccess() {
	return request({ url: '/api/docai/access/', method: 'get' });
}
export function analyzeDoc(file: File, email: string, prompt = '') {
	const form = new FormData();
	form.append('file', file);
	form.append('email', email);
	form.append('prompt', prompt);
	return request({
		url: '/api/docai/analyze/',
		method: 'post',
		data: form,
		headers: { 'Content-Type': 'multipart/form-data' },
		timeout: 120000,
	});
}
export function getDocAiPrompts() {
	return request({ url: '/api/docai/prompts/', method: 'get' });
}
export function listDocAiJobs() {
	return request({ url: '/api/docai/jobs/', method: 'get' });
}
export function getDocAiJob(id: number) {
	return request({ url: `/api/docai/jobs/${id}/`, method: 'get' });
}
