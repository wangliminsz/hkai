import { request } from '/@/utils/service';
import { Session } from '/@/utils/storage';
import { getBaseURL } from '/@/utils/baseUrl';

export function getPortals() {
	return request({ url: '/api/proposal/portals/', method: 'get' });
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

// 下载受保护 PDF: <a href> 无法带 JWT, 用 fetch + blob
export async function downloadPdf(id: number, filename: string) {
	const token = Session.get('token');
	const res = await fetch(getBaseURL(`api/proposal/jobs/${id}/pdf/`), {
		headers: token ? { Authorization: `JWT ${token}` } : {},
	});
	const ct = res.headers.get('content-type') || '';
	if (!res.ok || !ct.includes('application/pdf')) {
		let msg = `下载失败 (${res.status})`;
		try {
			const b = await res.json();
			if (b?.msg) msg = b.msg;
		} catch {
			/* ignore */
		}
		throw new Error(msg);
	}
	const blob = await res.blob();
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename || 'proposal.pdf';
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 4000);
}
