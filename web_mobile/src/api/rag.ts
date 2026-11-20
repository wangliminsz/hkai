import { request } from '@/utils/http';
import { apiUrl, resolveAsset } from '@/utils/url';
import { storage } from '@/utils/storage';

export function getRagProducts() {
  return request<any>({ url: '/api/rag/products/', method: 'get' });
}

export function explainTerm(data: { term: string; context?: string | null }) {
  return request<any>({ url: '/api/rag/explain/', method: 'post', data, timeout: 120000 });
}

export function documentHref(doc: any): string {
  return doc?.download_url ? apiUrl(doc.download_url) : '';
}

export function assetHref(path?: string | null): string {
  return resolveAsset(path);
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
  const token = storage.getToken();
  const res = await fetch(apiUrl('/api/rag/chat/stream/'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `JWT ${token}` } : {}),
      'Accept-Language': storage.getLang(),
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
    let msg = `请求失败 (${res.status})`;
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

  const dispatch = (event: string, data: any) => {
    if (event === 'start') onStart?.(data);
    else if (event === 'meta') onMeta?.(data);
    else if (event === 'delta') onDelta?.(data.text || '');
    else if (event === 'done') onDone?.(data);
    else if (event === 'needs_product') onNeedsProduct?.(data);
    else if (event === 'error') throw new Error(data.message || '服务端错误');
  };

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
      dispatch(event, data);
    }
  }

  // Some proxies/backends end the final event without a trailing blank line.
  if (buffer.trim()) {
    try {
      const { event, data } = parseSseBlock(buffer);
      dispatch(event, data);
    } catch {
      /* incomplete trailing block — ignore */
    }
  }
}
