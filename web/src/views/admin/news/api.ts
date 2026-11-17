import { request } from '/@/utils/service';

export function listNewsSources() {
	return request({ url: '/api/funds/news-sources/', method: 'get' });
}
export function createNewsSource(data: any) {
	return request({ url: '/api/funds/news-sources/', method: 'post', data });
}
export function updateNewsSource(id: number, data: any) {
	return request({ url: `/api/funds/news-sources/${id}/`, method: 'put', data });
}
export function deleteNewsSource(id: number) {
	return request({ url: `/api/funds/news-sources/${id}/`, method: 'delete' });
}

export function previewNews() {
	return request({ url: '/api/funds/news/preview/', method: 'get', timeout: 300000 });
}
export function listNewsBroadcasts() {
	return request({ url: '/api/funds/news/broadcasts/', method: 'get' });
}
export function createNewsBroadcast(data: any = {}) {
	return request({ url: '/api/funds/news/broadcasts/', method: 'post', data });
}
export function getNewsBroadcast(id: number) {
	return request({ url: `/api/funds/news/broadcasts/${id}/`, method: 'get' });
}
