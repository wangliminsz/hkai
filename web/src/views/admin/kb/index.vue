<template>
	<div class="kb-page">
		<div class="page-bar">
			<h2 class="page-title">AI 知识库管理</h2>
			<el-input v-model="keyword" class="page-search" placeholder="搜索产品名称 / 产品ID / 公司 / 分组"
				clearable @keyup.enter="applySearch" @clear="applySearch">
				<template #prefix>
					<el-icon class="search-ico" title="搜索" @click="applySearch"><ele-Search /></el-icon>
				</template>
			</el-input>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
				<el-button type="primary" @click="openAdd">
					<el-icon style="margin-right:4px"><ele-Plus /></el-icon>新增产品
				</el-button>
			</div>
		</div>

		<div class="hint">
			上传**产品介绍(brochure)**与**合同条款(contract)**后，系统会自动建目录、写目录并调用 PageIndex 在后台建立检索索引
			（约 $0.001/页，视文档大小需数分钟）。建成后**所有渠道立即可用**。
		</div>

		<el-table :data="filtered" v-loading="loading" class="kb-table" size="small" :row-class-name="() => 'kb-row'">
			<el-table-column prop="product_id" label="产品 ID" width="110" />
			<el-table-column label="名称" min-width="220">
				<template #default="{ row }">
					<div class="pname">{{ row.name }}</div>
					<div v-if="row.name_en" class="pen">{{ row.name_en }}</div>
				</template>
			</el-table-column>
			<el-table-column prop="insurer" label="公司" min-width="150" />
			<el-table-column label="类别 / 分组" min-width="170">
				<template #default="{ row }">
					<div class="pen">{{ row.category || '-' }}</div>
					<div v-if="row.compare_group" class="pgroup">分组: {{ row.compare_group }}</div>
				</template>
			</el-table-column>
			<el-table-column label="文档" width="90" align="center">
				<template #default="{ row }">{{ row.docs_indexed }}/{{ row.docs_total }}</template>
			</el-table-column>
			<el-table-column label="状态" width="120" align="center">
				<template #default="{ row }">
					<el-tag :type="tagType(row.state)" size="small" effect="dark">{{ row.state_label }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column label="更新时间" width="170">
				<template #default="{ row }"><span class="muted">{{ row.updated_at || '-' }}</span></template>
			</el-table-column>
			<el-table-column label="操作" width="140" align="center" fixed="right">
				<template #default="{ row }">
					<el-button v-if="row.state === 'queued' || row.state === 'indexing'" size="small" loading disabled>处理中</el-button>
					<el-button v-else size="small" :type="row.indexed ? 'warning' : 'primary'" @click="ingest(row, row.indexed)">
						{{ row.indexed ? '重新建立' : '建立索引' }}
					</el-button>
				</template>
			</el-table-column>
		</el-table>

		<el-dialog v-model="addVisible" title="新增产品" width="680px" :close-on-click-modal="false" destroy-on-close>
			<div class="auto-hint">
				只上传 PDF（可多个）即可 —— AI 自动识别 <b>产品名称 / 公司 / 类别 / 摘要 / 标签 / 文档类型</b> 并建立检索索引。
				识别结果可在下方「可选：手动填写 / 覆盖」中修正。
			</div>
			<el-upload drag multiple :auto-upload="false" :file-list="fileList" accept="application/pdf"
				:on-change="onPick" :on-remove="onRemove" class="pdf-upload">
				<el-icon class="el-icon--upload"><ele-UploadFilled /></el-icon>
				<div class="el-upload__text">将 PDF 拖到此处，或 <em>点击选择</em></div>
				<template #tip>
					<div class="el-upload__tip">支持多个 PDF（产品介绍 / 合同条款 / 其他均可）</div>
				</template>
			</el-upload>

			<el-collapse class="opt-collapse">
				<el-collapse-item title="可选：手动填写 / 覆盖" name="opt">
					<el-form :model="form" label-width="96px" label-position="right">
						<el-form-item label="产品 ID">
							<el-input v-model="form.product_id" placeholder="留空自动生成（PRD-XXXX）" />
						</el-form-item>
						<el-form-item label="产品名称"><el-input v-model="form.name" placeholder="留空由 AI 识别" /></el-form-item>
						<el-form-item label="英文名"><el-input v-model="form.name_en" /></el-form-item>
						<el-form-item label="保险公司">
							<el-select v-model="form.insurer" filterable allow-create default-first-option clearable
								placeholder="留空由 AI 识别" style="width:100%">
								<el-option v-for="c in insurers" :key="c" :value="c" :label="c" />
							</el-select>
						</el-form-item>
						<el-form-item label="类别"><el-input v-model="form.category" /></el-form-item>
						<el-form-item label="摘要"><el-input v-model="form.summary" type="textarea" :rows="2" /></el-form-item>
						<el-form-item label="标签"><el-input v-model="form.tags" placeholder="逗号分隔" /></el-form-item>
						<el-form-item label="对比分组"><el-input v-model="form.compare_group" /></el-form-item>
					</el-form>
				</el-collapse-item>
			</el-collapse>

			<template #footer>
				<div style="text-align: right">
					<el-button type="primary" :loading="submitting" @click="submit">上传并建立索引</el-button>
					<el-button @click="addVisible = false">取消</el-button>
				</div>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="adminKb">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getKbProducts, createKbProduct, ingestKbProduct } from './api';

const list = ref<any[]>([]);
const loading = ref(false);
const addVisible = ref(false);
const submitting = ref(false);
const form = ref<any>({});
const fileList = ref<any[]>([]);
const keyword = ref('');
const applied = ref('');
let timer: any = null;

// 仅点击搜索图标 / 回车时应用搜索(输入时不触发)
const applySearch = () => {
	applied.value = keyword.value.trim();
};
const filtered = computed(() => {
	const k = applied.value.toLowerCase();
	if (!k) return list.value;
	return list.value.filter((p: any) =>
		[p.product_id, p.name, p.name_en, p.insurer, p.category, p.compare_group, (p.tags || []).join(' ')]
			.filter(Boolean)
			.join(' ')
			.toLowerCase()
			.includes(k)
	);
});

const insurers = computed(() => Array.from(new Set(list.value.map((p) => p.insurer).filter(Boolean))));

const tagType = (s: string) => ({ done: 'success', indexing: 'primary', queued: 'info', error: 'danger' } as any)[s] || 'info';

const anyBusy = () => list.value.some((p) => p.state === 'queued' || p.state === 'indexing');
const schedulePoll = () => {
	if (timer) {
		clearInterval(timer);
		timer = null;
	}
	if (anyBusy()) timer = setInterval(load, 4000);
};

const load = async () => {
	loading.value = true;
	try {
		const res: any = await getKbProducts();
		if (res.code === 2000) {
			list.value = res.data.products || [];
			schedulePoll();
		} else {
			ElMessage.error(res.msg || '加载失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const openAdd = () => {
	fileList.value = [];
	form.value = {
		product_id: '',
		name: '',
		name_en: '',
		insurer: '',
		category: '',
		summary: '',
		tags: '',
		compare_group: '',
		currency: 'HKD',
		region: 'HK',
	};
	addVisible.value = true;
};

const onPick = (_file: any, list: any[]) => {
	fileList.value = list;
};
const onRemove = (_file: any, list: any[]) => {
	fileList.value = list;
};

const submit = async () => {
	if (!fileList.value.length) {
		ElMessage.warning('请至少上传一个 PDF 文件');
		return;
	}
	const fd = new FormData();
	['product_id', 'name', 'name_en', 'insurer', 'category', 'summary', 'tags', 'compare_group', 'currency', 'region'].forEach((k) => {
		const v = form.value[k];
		if (v !== undefined && v !== null && String(v).trim() !== '') fd.append(k, String(v));
	});
	fileList.value.forEach((f: any) => {
		if (f.raw) fd.append('files', f.raw);
	});

	submitting.value = true;
	try {
		const res: any = await createKbProduct(fd);
		if (res.code === 2000) {
			ElMessage.success(res.msg || '已创建，正在后台建立索引');
			addVisible.value = false;
			await load();
		} else {
			ElMessage.error(res.msg || '创建失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '创建失败');
	} finally {
		submitting.value = false;
	}
};

const ingest = async (row: any, force: boolean) => {
	try {
		await ElMessageBox.confirm(
			force ? `确认重新建立 ${row.product_id} 的索引？(会重新调用 LLM)` : `确认为 ${row.product_id} 建立索引？`,
			'建立索引',
			{ type: 'warning' }
		);
	} catch {
		return;
	}
	try {
		const res: any = await ingestKbProduct({ product_id: row.product_id, force });
		if (res.code === 2000) {
			ElMessage.success('已提交后台建立索引');
			load();
		} else {
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '提交失败');
	}
};

onMounted(load);
onUnmounted(() => {
	if (timer) clearInterval(timer);
});
</script>

<style scoped lang="scss">
.kb-page {
	.page-bar {
		display: flex;
		align-items: center;
		gap: 14px;
		margin-bottom: 14px;
	}
	.page-title {
		font-size: 18px;
		font-weight: 600;
		color: var(--cn-text-strong, #eaeaea);
		margin: 0;
		flex: 0 0 auto;
	}
	.page-search {
		width: 320px;
	}
	.search-ico {
		cursor: pointer;
		color: var(--cn-muted, #b1b4b8);
		transition: color 0.2s;
	}
	.search-ico:hover {
		color: #409eff;
	}
	.bar-right {
		display: flex;
		gap: 10px;
		margin-left: auto;
	}
	.hint {
		font-size: 12.5px;
		line-height: 1.7;
		color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c);
		border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px;
		padding: 10px 14px;
		margin-bottom: 14px;
	}
	.auto-hint {
		font-size: 12.5px;
		line-height: 1.7;
		color: var(--cn-muted, #b1b4b8);
		background: rgba(64, 158, 255, 0.08);
		border: 1px solid rgba(64, 158, 255, 0.25);
		border-radius: 10px;
		padding: 10px 14px;
		margin-bottom: 12px;
	}
	.opt-collapse {
		margin-top: 14px;
	}
	.pname {
		color: var(--cn-text, #dadada);
	}
	.pen {
		font-size: 12px;
		color: var(--cn-faint, #8f9297);
	}
	.pgroup {
		font-size: 12px;
		color: var(--cn-primary, #409eff);
	}
	.muted {
		color: var(--cn-faint, #8f9297);
	}
	.file-input {
		color: var(--cn-muted, #b1b4b8);
		font-size: 13px;
	}
	.file-name {
		margin-left: 10px;
		font-size: 12px;
		color: var(--cn-faint, #8f9297);
	}
}

.kb-table {
	background: transparent;
}
</style>
