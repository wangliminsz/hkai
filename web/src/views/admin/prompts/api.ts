import { request } from '/@/utils/service';

export function listPrompts() {
	return request({ url: '/api/funds/prompts/', method: 'get' });
}
export function updatePrompt(key: string, content: string) {
	return request({ url: `/api/funds/prompts/${key}/`, method: 'put', data: { content } });
}
export function resetPrompt(key: string) {
	return request({ url: `/api/funds/prompts/${key}/reset/`, method: 'post' });
}
