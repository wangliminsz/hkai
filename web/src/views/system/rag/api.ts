import { request } from '/@/utils/service';
import { Session } from '/@/utils/storage';
import { getBaseURL } from '/@/utils/baseUrl';

export function getRagProducts() {
	return request({
		url: '/api/rag/products/',
		method: 'get',
	});
}

export function explainTerm(data: { term: string; context?: string | null }) {
	return request({
		url: '/api/rag/explain/',
		method: 'post',
		data,
		timeout: 120000,
	});
}

function parseSseBlock(block: string) {
	let event = 'message';
	let data = '';
	for (const line of block.split('\n')) {
		if (line.startsWith('event:')) event = line.slice(6).trim();
		else if (line.startsWith('data:')) data += line.slice(5).trim();
	}
	return { event, data: data ? JSON.parse(data) : {} };
}

export async function sendChatStream(opts: {
	question: string;
	productId?: string;
	productIds?: string[];
	history?: any[];
	onStart?: (d: any) => void;
	onMeta?: (d: any) => void;
	onDelta?: (t: string) => void;
	onDone?: (d: any) => void;
	onNeedsProduct?: (d: any) => void;
}) {
	const { question, productId, productIds, history, onStart, onMeta, onDelta, onDone, onNeedsProduct } = opts;
	const token = Session.get('token');
	const res = await fetch(getBaseURL('api/rag/chat/stream/'), {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `JWT ${token}` } : {}),
		},
		body: JSON.stringify({
			question,
			product_id: productId || null,
			product_ids: productIds || [],
			history: history || [],
		}),
	});
	const contentType = res.headers.get('content-type') || '';
	if (!res.ok || !res.body || !contentType.includes('text/event-stream')) {
		// 鉴权失败时后端以 HTTP 200 + {code:4000,msg} 返回(自定义异常处理), 需读 body 取提示
		let msg = `請求失敗 (${res.status})`;
		try {
			const body = await res.json();
			if (body?.msg) msg = body.msg;
		} catch {
			/* ignore */
		}
		throw new Error(msg);
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { value, done } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });

		let idx: number;
		while ((idx = buffer.indexOf('\n\n')) !== -1) {
			const block = buffer.slice(0, idx);
			buffer = buffer.slice(idx + 2);
			if (!block.trim()) continue;
			const { event, data } = parseSseBlock(block);
			if (event === 'start') onStart?.(data);
			else if (event === 'meta') onMeta?.(data);
			else if (event === 'delta') onDelta?.(data.text || '');
			else if (event === 'done') onDone?.(data);
			else if (event === 'needs_product') onNeedsProduct?.(data);
			else if (event === 'error') throw new Error(data.message || '服務端錯誤');
		}
	}
}
