import { request } from '/@/utils/service';

// 知识库产品列表 + 索引状态(超管)
export function getKbProducts() {
	return request({
		url: '/api/rag/admin/products/',
		method: 'get',
	});
}

// 新建产品(上传 brochure + contract)，后端写目录/目录索引并异步建索引(超管)
export function createKbProduct(formData: FormData) {
	return request({
		url: '/api/rag/admin/products/',
		method: 'post',
		data: formData,
		headers: { 'Content-Type': 'multipart/form-data' },
		timeout: 300000,
	});
}

// 为已有产品(重新)建立索引(超管)
export function ingestKbProduct(data: { product_id: string; force?: boolean }) {
	return request({
		url: '/api/rag/admin/ingest/',
		method: 'post',
		data,
	});
}
