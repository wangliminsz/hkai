<template>
	<div class="prop">
		<div class="prop-bar">
			<h2 class="prop-title">计划书生成</h2>
			<el-select v-model="portalId" class="p-portal" placeholder="选择保险公司">
				<el-option v-for="p in portals" :key="p.id" :value="p.id" :label="p.name" />
			</el-select>
			<span class="muted">选择公司 → 输入客户资料 → 自动登录门户生成计划书 PDF</span>
		</div>

		<section class="card catalog">
			<div class="row-between">
				<strong>可生成计划书（{{ products.length }} 个产品）</strong>
				<span class="muted">当前系统支持以下险种与缴费期 · 点击产品可填入示例</span>
			</div>
			<div class="prod-grid">
				<div v-for="p in products" :key="p.code" class="prod" title="点击填入示例提示词" @click="useExample(p)">
					<div class="prod-name">
						<span>
							{{ p.name }}
							<span class="muted" v-if="p.category">· {{ p.category }}</span>
						</span>
						<span class="example-hint">示例</span>
					</div>
					<div v-for="v in p.variants" :key="v.tier || 'default'" class="prod-variant">
						<span v-if="v.tier" class="tier">{{ v.tier }}</span>
						<span>{{ v.periods.join(' / ') }}</span>
					</div>
				</div>
			</div>
		</section>

		<section class="card">
			<div class="prompt-wrap">
				<el-input v-model="text" type="textarea" :rows="4" resize="none" :placeholder="EXAMPLE_PROMPT" />
				<el-tooltip content="复制示例提示词" placement="top">
					<el-icon class="copy-ico" @click="copyExample"><ele-CopyDocument /></el-icon>
				</el-tooltip>
			</div>
			<div class="actions">
				<label class="chk">
					<el-switch v-model="drill" size="small" /> 仅演练（不出单，无 PDF）
				</label>
				<el-button type="primary" :loading="submitting" :disabled="!text.trim() || !portalId" @click="submit">
					开始生成
				</el-button>
			</div>
		</section>

		<section v-if="job" class="card">
			<div class="row-between">
				<div>
					状态：<el-tag :type="tagType(job.status)" size="small" effect="dark">{{ statusLabel(job.status) }}</el-tag>
					<span class="muted"> #{{ job.id }}</span>
					<span v-if="job.portal" class="muted"> · {{ job.portal.name }}</span>
				</div>
				<el-button
					v-if="job.status === 'succeeded' && job.download_url"
					tag="a"
					:href="downloadHref(job)"
					:download="job.pdf_name || 'proposal.pdf'"
					size="small"
					type="primary"
				>
					下载 PDF（{{ job.pdf_name }}）
				</el-button>
			</div>
			<p v-if="job.error" class="err">{{ job.error }}</p>
			<pre class="logs">{{ job.logs || '（等待日志…）' }}</pre>
		</section>

		<section class="card">
			<div class="row-between">
				<strong>生成历史</strong>
				<el-button size="small" :loading="loading" @click="loadHistory">刷新</el-button>
			</div>
			<el-table :data="history" size="small" class="hist">
				<el-table-column prop="id" label="#" width="70" />
				<el-table-column label="状态" width="100">
					<template #default="{ row }">
						<el-tag :type="tagType(row.status)" size="small" effect="dark">{{ statusLabel(row.status) }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column prop="text" label="客户资料" min-width="240" show-overflow-tooltip />
				<el-table-column prop="created_at" label="时间" width="170" />
				<el-table-column label="操作" width="100" align="center">
					<template #default="{ row }">
						<el-button
							v-if="row.status === 'succeeded' && row.download_url"
							tag="a"
							:href="downloadHref(row)"
							:download="row.pdf_name || 'proposal.pdf'"
							size="small"
						>
							下载
						</el-button>
					</template>
				</el-table-column>
			</el-table>
		</section>
	</div>
</template>

<script setup lang="ts" name="proposalGen">
import { ref, onMounted, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { getBaseURL } from '/@/utils/baseUrl';
import { getPortals, getProducts, listJobs, createJob, getJob } from './api';

const EXAMPLE_PROMPT =
	'Mr.VIP，男性，40 岁，非吸烟者，投保尚裕寿险，保额 100 万美元，缴费期 20 年，居住地中国大陆';

const buildExample = (p: any) => {
	const variant = p.variants?.[0] || {};
	const tier = variant.tier || '';
	const rawPeriod = variant.periods?.[0] || '20年缴';
	const isSavings = /儲蓄|储蓄|年金/.test(p.category || '');
	const parts = [
		'Mr.VIP', '男性', '40 岁', '非吸烟者',
		`投保${p.name}${tier ? `（${tier}）` : ''}`,
		isSavings ? '每年保费 1 万美元' : '保额 100 万美元',
		rawPeriod === '一次过缴付' ? '一次过缴付' : `缴费期 ${rawPeriod.replace(/缴$/, '')}`,
	];
	if (isSavings) parts.push('自保单 20 年起，至保单结束，每年提取最大值');
	parts.push('居住地中国大陆');
	return parts.join('，');
};

const useExample = (p: any) => {
	text.value = buildExample(p);
	ElMessage.success('已填入示例，可直接修改后生成');
};

const copyExample = async () => {
	try {
		await navigator.clipboard.writeText(EXAMPLE_PROMPT);
	} catch {
		const area = document.createElement('textarea');
		area.value = EXAMPLE_PROMPT;
		area.style.position = 'fixed';
		area.style.opacity = '0';
		document.body.appendChild(area);
		area.select();
		document.execCommand('copy');
		area.remove();
	}
	ElMessage.success('已复制示例，可粘贴后修改');
};

const portals = ref<any[]>([]);
const products = ref<any[]>([]);
const portalId = ref<number | ''>('');
const text = ref('');
const drill = ref(false);
const submitting = ref(false);
const loading = ref(false);
const job = ref<any>(null);
const history = ref<any[]>([]);
let timer: any = null;

const LABELS: Record<string, string> = {
	queued: '排队中', running: '生成中', needs_human: '需人工', succeeded: '已完成', failed: '失败',
};
const statusLabel = (s: string) => LABELS[s] || s;
const tagType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'info', needs_human: 'warning', failed: 'danger' } as any)[s] || 'info';

const loadPortals = async () => {
	try {
		const res: any = await getPortals();
		if (res.code === 2000) {
			portals.value = res.data || [];
			if (portals.value.length && !portalId.value) portalId.value = portals.value[0].id;
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '加载公司失败');
	}
};

const loadProducts = async () => {
	try {
		const res: any = await getProducts();
		if (res.code === 2000) products.value = res.data || [];
	} catch (e: any) {
		ElMessage.error(e?.message || '加载可生成计划书失败');
	}
};

const loadHistory = async () => {
	loading.value = true;
	try {
		const res: any = await listJobs();
		if (res.code === 2000) history.value = res.data || [];
	} catch (e: any) {
		ElMessage.error(e?.message || '加载历史失败');
	} finally {
		loading.value = false;
	}
};

const poll = () => {
	if (timer) return;
	timer = setInterval(async () => {
		if (!job.value || (job.value.status !== 'queued' && job.value.status !== 'running')) {
			clearInterval(timer);
			timer = null;
			return;
		}
		try {
			const res: any = await getJob(job.value.id);
			if (res.code === 2000) {
				job.value = res.data;
				if (job.value.status !== 'queued' && job.value.status !== 'running') {
					clearInterval(timer);
					timer = null;
					loadHistory();
				}
			}
		} catch {
			/* ignore */
		}
	}, 2500);
};

const submit = async () => {
	submitting.value = true;
	try {
		const res: any = await createJob({ portal_id: portalId.value, text: text.value.trim(), create_pdf: !drill.value });
		if (res.code === 2000) {
			job.value = res.data;
			ElMessage.success('已提交，正在后台生成');
			poll();
			loadHistory();
		} else {
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '提交失败');
	} finally {
		submitting.value = false;
	}
};

const downloadHref = (row: any) => (row?.download_url ? getBaseURL(row.download_url) : '');

onMounted(async () => {
	await Promise.all([loadPortals(), loadProducts()]);
	loadHistory();
});
onUnmounted(() => {
	if (timer) clearInterval(timer);
});
</script>

<style scoped lang="scss">
.prop {
	--p-card: #1a1a1c;
	--p-border: #2a2a2a;
	--p-border-2: #333;
	--p-text: #dadada;
	--p-muted: #b1b4b8;
	--p-faint: #8f9297;
	color: var(--p-text);

	.prop-bar {
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
	.prop-title {
		font-size: 18px;
		font-weight: 600;
		color: #eaeaea;
		margin: 0;
	}
	.p-portal {
		width: 260px;
	}
	.muted {
		color: var(--p-faint);
		font-size: 12.5px;
	}
	.card {
		background: var(--p-card);
		border: 1px solid var(--p-border);
		border-radius: 12px;
		padding: 16px 18px;
		margin-bottom: 14px;
	}
	.catalog {
		padding-bottom: 14px;
	}
	.prod-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 10px 18px;
		margin-top: 12px;
	}
	.prod {
		border: 1px solid var(--p-border-2);
		border-radius: 8px;
		padding: 10px 12px;
		background: #161618;
		cursor: pointer;
		transition: border-color 0.2s, background 0.2s;
	}
	.prod:hover {
		border-color: #409eff;
		background: #171a1e;
	}
	.prod-name {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		font-size: 13px;
		color: #eaeaea;
		font-weight: 500;
		margin-bottom: 5px;
	}
	.example-hint {
		flex-shrink: 0;
		font-size: 11px;
		font-weight: 400;
		color: #7db6ff;
	}
	.prod-variant {
		display: flex;
		gap: 8px;
		font-size: 12px;
		color: var(--p-muted);
		line-height: 1.7;
	}
	.prod-variant .tier {
		color: #7db6ff;
	}
	.prompt-wrap {
		position: relative;
		:deep(.el-textarea__inner) {
			padding-right: 36px;
		}
	}
	.copy-ico {
		position: absolute;
		top: 8px;
		right: 10px;
		font-size: 16px;
		color: var(--p-faint);
		cursor: pointer;
		transition: color 0.2s;
		z-index: 2;
	}
	.copy-ico:hover {
		color: #409eff;
	}
	.actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-top: 12px;
	}
	.chk {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 12.5px;
		color: var(--p-muted);
		cursor: pointer;
	}
	.row-between {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.err {
		color: #f56c6c;
		font-size: 13px;
		margin: 8px 0 0;
	}
	.logs {
		margin: 10px 0 0;
		max-height: 320px;
		overflow: auto;
		background: #141414;
		border: 1px solid var(--p-border);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 12px;
		line-height: 1.6;
		color: var(--p-muted);
		white-space: pre-wrap;
	}
	.hist {
		margin-top: 10px;
		background: transparent;
	}
}
</style>
