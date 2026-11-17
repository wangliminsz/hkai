<template>
	<div class="cards">
		<div class="bar">
			<h2 class="title">保险图文卡</h2>
			<el-tag size="small" effect="dark" type="info">小红书 3:4 · llm 风格</el-tag>
			<span class="muted">上传计划书 PDF → 自动识别产品 → 编辑文案 → 生成图文卡（数字来自 PDF）</span>
		</div>

		<section class="card">
			<el-upload drag :auto-upload="false" :show-file-list="false" accept="application/pdf"
				:on-change="onPick" class="pdf-up">
				<el-icon class="el-icon--upload"><ele-UploadFilled /></el-icon>
				<div class="el-upload__text">将计划书 PDF 拖到此处，或 <em>点击选择</em></div>
				<template #tip><div class="el-upload__tip">自动识别产品类型；点击下方「查看支持的产品」可查看全部已注册模板</div></template>
			</el-upload>
			<div v-if="fileName" class="fileline">
				<el-icon><ele-Document /></el-icon>
				<span>{{ fileName }}</span>
				<el-button size="small" :loading="detecting" @click="runDetect">重新识别</el-button>
			</div>
			<div class="support-line">
				<span class="muted">已支持 {{ catalog.length }} 款产品 · {{ companies.length }} 家公司</span>
				<el-button link type="primary" size="small" @click="catalogVisible = true">查看支持的产品</el-button>
			</div>
		</section>

		<section v-if="detected" class="card">
			<div class="row-between">
				<div>
					<strong>{{ detected.plan_name || chosenProductName }}</strong>
					<span class="muted"> · 产品 {{ chosenProductName }}（{{ chosenProduct || detected.product }}） · {{ detected.cards.length }} 张卡</span>
				</div>
				<div class="gen-actions">
					<el-select v-model="companyFilter" size="small" class="co-sel" clearable placeholder="全部公司" @change="onCompanyFilter">
						<el-option v-for="c in filterCompanies" :key="c.code" :value="c.code" :label="c.name" />
					</el-select>
					<el-select v-model="chosenProduct" size="small" class="prod-sel" placeholder="选择产品" @change="onProductChange">
						<el-option v-for="p in filteredProductOptions" :key="p.id" :value="p.id"
							:label="`${p.company ? p.company + ' · ' : ''}${p.name}${p.draft ? '（草稿）' : ''}（${p.id}）`" />
					</el-select>
					<el-select v-model="theme" size="small" class="theme-sel">
						<el-option value="yf-cream" label="YF 奶油蓝" />
						<el-option value="aia-red" label="AIA 红" />
					</el-select>
					<el-button type="primary" :loading="submitting" @click="generate">生成图文卡</el-button>
				</div>
			</div>

			<el-collapse class="cards-collapse">
				<el-collapse-item v-for="c in detected.cards" :key="c.idx" :name="c.idx">
					<template #title>
						<span class="cname">{{ c.idx + 1 }}. {{ c.name }}</span>
						<span class="chint">{{ c.hint }}</span>
					</template>
					<div class="fields">
						<div v-for="(val, key) in c.fields" :key="key" class="field">
							<label>{{ key }}</label>
							<el-input
								:model-value="editValue(c.idx, key, val)"
								:type="String(val).length > 40 ? 'textarea' : 'text'"
								:rows="3"
								size="small"
								@update:model-value="(v: string) => setEdit(c.idx, key, v, val)"
							/>
						</div>
					</div>
				</el-collapse-item>
			</el-collapse>
		</section>

		<section v-if="job" class="card">
			<div class="row-between">
				<div>
					状态：<el-tag :type="tagType(job.status)" size="small" effect="dark">{{ job.status_label }}</el-tag>
					<span class="muted"> #{{ job.id }} · {{ job.product }}</span>
				</div>
				<el-button v-if="job.status === 'succeeded'" type="primary" size="small" :loading="downloading" @click="download()">
					下载 ZIP
				</el-button>
			</div>
			<el-progress v-if="job.status === 'queued' || job.status === 'running' || job.status === 'failed'"
				:percentage="job.progress || 0" :stroke-width="8"
				:status="job.status === 'failed' ? 'exception' : undefined" class="prog" />
			<p v-if="job.error" class="err">{{ job.error }}</p>
			<div v-if="previews.length" class="grid">
				<img v-for="(src, i) in previews" :key="i" :src="src" :alt="`card ${i + 1}`" />
			</div>
			<pre v-else class="logs">{{ job.logs || '（等待生成…）' }}</pre>
		</section>

		<section class="card">
			<div class="row-between">
				<strong>生成历史</strong>
				<el-button size="small" :loading="loading" @click="loadJobs">刷新</el-button>
			</div>
			<el-table :data="jobs" size="small" class="hist">
				<el-table-column prop="id" label="#" width="70" />
				<el-table-column prop="product" label="产品" width="110" />
				<el-table-column label="状态" width="100">
					<template #default="{ row }">
						<el-tag :type="tagType(row.status)" size="small" effect="dark">{{ row.status_label }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column prop="plan_name" label="计划" min-width="200" show-overflow-tooltip />
				<el-table-column prop="created_at" label="时间" width="170" />
				<el-table-column label="操作" width="150" align="center">
					<template #default="{ row }">
						<el-button v-if="row.zip_ready" size="small" @click="download(row)">下载</el-button>
						<el-button size="small" @click="view(row)">查看</el-button>
					</template>
				</el-table-column>
			</el-table>
		</section>

		<el-dialog v-model="catalogVisible" title="支持的产品" width="760px" destroy-on-close>
			<div class="cat-filters">
				<el-select v-model="filterCompany" clearable placeholder="全部公司" class="cat-company">
					<el-option v-for="c in companies" :key="c" :value="c" :label="c" />
				</el-select>
				<el-input v-model="filterKw" clearable placeholder="搜索产品名 / 代号 / 类别" class="cat-search" />
			</div>
			<div class="cat-groups">
				<div v-for="g in groupedCatalog" :key="g.company" class="cat-group">
					<div class="cat-group-title">{{ g.company }} <span class="muted">（{{ g.items.length }} 款）</span></div>
					<el-table :data="g.items" size="small">
						<el-table-column prop="name" label="产品" min-width="220" />
						<el-table-column prop="id" label="代号" width="110" />
						<el-table-column prop="category" label="类别" width="90" />
						<el-table-column prop="positioning" label="定位" min-width="180" show-overflow-tooltip />
					</el-table>
				</div>
				<div v-if="!groupedCatalog.length" class="muted" style="padding:20px;text-align:center">没有匹配的产品</div>
			</div>
			<div class="cat-foot muted">共 {{ filteredCatalog.length }} 款 · {{ groupedCatalog.length }} 家公司</div>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="cardsGen">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { detectCard, createCardJob, listCardJobs, getCardJob, fetchCardBlobUrl, downloadCardsZip, getCardProducts } from './api';

const catalog = ref<any[]>([]);
const productOptions = ref<any[]>([]);
const chosenProduct = ref('');
const companyFilter = ref('');
const catalogVisible = ref(false);
const filterCompany = ref('');
const filterKw = ref('');
const companies = computed(() => Array.from(new Set(catalog.value.map((p) => p.company).filter(Boolean))));
const filterCompanies = computed(() => {
	const map = new Map<string, { code: string; name: string }>();
	for (const p of productOptions.value) {
		if (p.company_code && !map.has(p.company_code)) map.set(p.company_code, { code: p.company_code, name: p.company || p.company_code });
	}
	return Array.from(map.values());
});
const filteredProductOptions = computed(() =>
	companyFilter.value ? productOptions.value.filter((p) => p.company_code === companyFilter.value) : productOptions.value
);
const onCompanyFilter = () => {
	if (!filteredProductOptions.value.some((p) => p.id === chosenProduct.value)) {
		chosenProduct.value = filteredProductOptions.value[0]?.id || '';
		if (fileObj.value && chosenProduct.value) runDetect(chosenProduct.value);
	}
};
const chosenProductName = computed(() => {
	const p = productOptions.value.find((x) => x.id === chosenProduct.value);
	return p?.name || chosenProduct.value || '';
});
const filteredCatalog = computed(() => {
	const kw = filterKw.value.trim().toLowerCase();
	return catalog.value.filter((p) => {
		if (filterCompany.value && p.company !== filterCompany.value) return false;
		if (!kw) return true;
		return [p.name, p.id, p.category, p.positioning].filter(Boolean).join(' ').toLowerCase().includes(kw);
	});
});
const groupedCatalog = computed(() => {
	const map = new Map<string, any[]>();
	for (const p of filteredCatalog.value) {
		const key = p.company || '未归类';
		if (!map.has(key)) map.set(key, []);
		map.get(key)!.push(p);
	}
	return Array.from(map.entries()).map(([company, items]) => ({ company, items }));
});

const loadCatalog = async () => {
	try {
		const res: any = await getCardProducts();
		if (res.code === 2000) catalog.value = res.data || [];
	} catch {
		/* ignore */
	}
};
const loadProducts = async () => {
	try {
		const res: any = await getCardProducts(true);
		if (res.code === 2000) productOptions.value = res.data || [];
	} catch {
		/* ignore */
	}
};

onMounted(async () => {
	loadProducts();
	await loadCatalog();
	loadJobs();
});

const fileObj = ref<File | null>(null);
const fileName = ref('');
const detecting = ref(false);
const detected = ref<any>(null);
const edits = reactive<Record<string, string>>({});
const theme = ref('yf-cream');
const submitting = ref(false);
const downloading = ref(false);
const loading = ref(false);
const job = ref<any>(null);
const jobs = ref<any[]>([]);
const previews = ref<string[]>([]);
let timer: any = null;

const LABELS: Record<string, string> = { queued: '排队中', running: '生成中', succeeded: '已完成', failed: '失败' };
const statusLabel = (s: string) => LABELS[s] || s;
const tagType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'info', failed: 'danger' } as any)[s] || 'info';

const editKey = (idx: number, key: string) => `${idx}.${key}`;
const editValue = (idx: number, key: string, orig: string) => edits[editKey(idx, key)] ?? orig;
const setEdit = (idx: number, key: string, v: string, orig: string) => {
	if (v === orig) delete edits[editKey(idx, key)];
	else edits[editKey(idx, key)] = v;
};

const onPick = async (file: any) => {
	const raw: File = file?.raw;
	if (!raw) return;
	if (!raw.name.toLowerCase().endsWith('.pdf')) {
		ElMessage.warning('请选择 PDF 文件');
		return;
	}
	fileObj.value = raw;
	fileName.value = raw.name;
	chosenProduct.value = '';
	await runDetect();
};

const runDetect = async (productOverride?: string) => {
	if (!fileObj.value) return;
	detecting.value = true;
	detected.value = null;
	Object.keys(edits).forEach((k) => delete edits[k]);
	try {
		const res: any = await detectCard(fileObj.value, productOverride || '');
		if (res.code === 2000) {
			detected.value = res.data;
			chosenProduct.value = productOverride || res.data.product;
			ElMessage.success(`识别成功：${res.data.product}（${res.data.card_count} 张）`);
		} else {
			ElMessage.error(res.msg || '识别失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '识别失败');
	} finally {
		detecting.value = false;
	}
};

const onProductChange = () => {
	if (fileObj.value && chosenProduct.value) runDetect(chosenProduct.value);
};

const buildOverrides = () => {
	const out: Record<number, Record<string, string>> = {};
	for (const k of Object.keys(edits)) {
		const [idxStr, ...rest] = k.split('.');
		const idx = Number(idxStr);
		const field = rest.join('.');
		if (!out[idx]) out[idx] = {};
		out[idx][field] = edits[k];
	}
	return out;
};

const generate = async () => {
	if (!fileObj.value || !detected.value) return;
	const fd = new FormData();
	fd.append('file', fileObj.value);
	fd.append('product', chosenProduct.value || detected.value.product);
	fd.append('plan_name', detected.value.plan_name || '');
	fd.append('theme', theme.value);
	fd.append('overrides', JSON.stringify(buildOverrides()));
	submitting.value = true;
	try {
		const res: any = await createCardJob(fd);
		if (res.code === 2000) {
			job.value = res.data;
			previews.value = [];
			ElMessage.success('已提交，正在生成');
			poll();
			loadJobs();
		} else {
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '提交失败');
	} finally {
		submitting.value = false;
	}
};

const clearPreviews = () => {
	previews.value.forEach((u) => URL.revokeObjectURL(u));
	previews.value = [];
};

const loadPreviews = async (j: any) => {
	clearPreviews();
	const n = (j.card_files || []).length;
	for (let i = 0; i < n; i++) {
		try {
			previews.value.push(await fetchCardBlobUrl(j.id, i));
		} catch {
			/* ignore */
		}
	}
};

const poll = () => {
	if (timer) return;
	timer = setInterval(async () => {
		if (!job.value || (job.value.status !== 'queued' && job.value.status !== 'running')) {
			clearInterval(timer); timer = null; return;
		}
		try {
			const res: any = await getCardJob(job.value.id);
			if (res.code === 2000) {
				job.value = res.data;
				if (job.value.status === 'succeeded') {
					clearInterval(timer); timer = null;
					loadPreviews(job.value);
					loadJobs();
				} else if (job.value.status === 'failed') {
					clearInterval(timer); timer = null;
					loadJobs();
				}
			}
		} catch { /* ignore */ }
	}, 3000);
};

const loadJobs = async () => {
	loading.value = true;
	try {
		const res: any = await listCardJobs();
		if (res.code === 2000) jobs.value = res.data || [];
	} catch { /* ignore */ } finally { loading.value = false; }
};

const view = async (row: any) => {
	const res: any = await getCardJob(row.id);
	if (res.code === 2000) {
		job.value = res.data;
		if (job.value.status === 'succeeded') loadPreviews(job.value);
		else poll();
	}
};

const download = async (row?: any) => {
	const j = row || job.value;
	if (!j) return;
	downloading.value = true;
	try {
		await downloadCardsZip(j.id, `cards_${j.id}_${j.product}.zip`);
	} catch (e: any) {
		ElMessage.error(e?.message || '下载失败');
	} finally {
		downloading.value = false;
	}
};

onUnmounted(() => {
	if (timer) clearInterval(timer);
	clearPreviews();
});
</script>

<style scoped lang="scss">
.cards {
	--c-card: #1a1a1c;
	--c-border: #2a2a2a;
	--c-text: #dadada;
	--c-muted: #b1b4b8;
	--c-faint: #8f9297;
	color: var(--c-text);

	.bar {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
	.title { font-size: 18px; font-weight: 600; color: #eaeaea; margin: 0; }
	.muted { color: var(--c-faint); font-size: 12.5px; }
	.card {
		background: var(--c-card);
		border: 1px solid var(--c-border);
		border-radius: 12px;
		padding: 16px 18px;
		margin-bottom: 14px;
	}
	.pdf-up { :deep(.el-upload-dragger) { background: #191919; border-color: #333; } }
	.fileline {
		display: flex; align-items: center; gap: 10px; margin-top: 10px;
		font-size: 13px; color: var(--c-muted);
	}
	.support-line {
		display: flex; align-items: center; gap: 10px; margin-top: 8px;
	}
	.cat-filters { display: flex; gap: 10px; margin-bottom: 12px; }
	.cat-company { width: 240px; }
	.cat-search { flex: 1; }
	.cat-foot { margin-top: 8px; font-size: 12px; }
	.cat-groups { max-height: 470px; overflow: auto; }
	.cat-group + .cat-group { margin-top: 14px; }
	.cat-group-title {
		font-size: 13px; font-weight: 600; color: #eaeaea;
		margin: 4px 0 8px; padding-left: 2px;
	}
	.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
	.gen-actions { display: flex; align-items: center; gap: 10px; }
	.theme-sel { width: 130px; }
	.prod-sel { width: 300px; }
	.co-sel { width: 190px; }
	.cards-collapse { margin-top: 12px; }
	.cname { color: var(--c-text); font-size: 13px; }
	.chint { color: var(--c-faint); font-size: 12px; margin-left: 10px; }
	.fields { display: flex; flex-direction: column; gap: 10px; }
	.field {
		display: grid; grid-template-columns: 140px 1fr; gap: 10px; align-items: start;
		label { font-size: 12px; color: var(--c-faint); padding-top: 6px; word-break: break-all; }
	}
	.prog { margin-top: 12px; }
	.err { color: #f56c6c; font-size: 13px; margin: 8px 0 0; }
	.logs {
		margin: 10px 0 0; max-height: 260px; overflow: auto; background: #141414;
		border: 1px solid var(--c-border); border-radius: 8px; padding: 10px 12px;
		font-size: 12px; color: var(--c-muted); white-space: pre-wrap;
	}
	.grid {
		margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px;
		img { width: 100%; border-radius: 8px; border: 1px solid var(--c-border); display: block; }
	}
	.hist { margin-top: 10px; background: transparent; }
}
</style>
