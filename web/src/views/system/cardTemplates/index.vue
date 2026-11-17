<template>
	<div class="te">
		<div class="te-bar">
			<h2 class="te-title">卡片模板</h2>
			<el-select v-model="companyFilter" class="co-select" clearable placeholder="全部公司" @change="onCompanyFilter">
				<el-option v-for="c in companies" :key="c.code" :value="c.code" :label="c.name" />
			</el-select>
			<el-select v-model="pid" class="te-select" @change="onSelect">
				<el-option v-for="p in filteredProducts" :key="p.id" :value="p.id" :label="`${p.company_name ? p.company_name + ' · ' : ''}${p.name}${p.draft ? '（草稿）' : ''}（${p.id}）`" />
			</el-select>
			<el-tag v-if="selected && selected.draft" size="small" effect="dark" type="warning">草稿 · 未发布</el-tag>
			<el-tag v-else size="small" effect="dark" type="info">llm · 小红书 3:4</el-tag>
			<div class="te-actions">
				<el-button size="small" @click="openNew">+ 新建模板</el-button>
				<el-button size="small" @click="openEditPicker">编辑模板</el-button>
				<el-button v-if="selected && selected.draft" size="small" :loading="validating" @click="validateDraftNow">验证</el-button>
				<el-button v-if="selected && selected.draft" size="small" type="success" :loading="publishing" @click="publishNow">发布</el-button>
				<el-button size="small" :loading="previewing" @click="refreshPreview">刷新预览</el-button>
				<el-button size="small" type="primary" :loading="saving" @click="save">保存模板</el-button>
			</div>
		</div>

		<div v-if="loading" class="te-empty">加载中…</div>
		<div v-else-if="!selected" class="te-empty">请选择产品</div>
		<div v-else class="te-body">
			<aside class="te-left">
				<el-collapse v-model="openPanels">
					<el-collapse-item title="产品文案与 LLM 定位" name="copy">
						<el-form label-width="120px" size="small">
							<el-form-item label="产品名称">
								<el-input v-model="selected.template.copy.plan_default" placeholder="显示名称，如 环宇盈活储蓄保险计划 (AIA GF)" />
							</el-form-item>
							<el-form-item label="产品代号">
								<div class="rename-row">
									<el-input v-model="renameTo" size="small" placeholder="字母/数字/_/-，如 aia-gf" />
									<el-button size="small" @click="doRename">重命名</el-button>
								</div>
							</el-form-item>
							<el-form-item label="产品定位">
								<el-input v-model="selected.template.copy.product_positioning" />
							</el-form-item>
							<el-form-item label="卖点要点">
								<div class="points">
									<div v-for="(pt, i) in selected.template.copy.positioning_points" :key="i" class="point-row">
										<el-input v-model="selected.template.copy.positioning_points[i]" :placeholder="`卖点 ${i + 1}`" />
										<el-button link type="danger" @click="selected.template.copy.positioning_points.splice(i, 1)">删</el-button>
									</div>
									<el-button size="small" link type="primary" @click="selected.template.copy.positioning_points.push('')">+ 添加卖点</el-button>
								</div>
							</el-form-item>
							<el-form-item v-for="f in copyStrFields" :key="f" :label="f">
								<el-input v-model="selected.template.copy[f]" />
							</el-form-item>
						</el-form>
					</el-collapse-item>

					<el-collapse-item title="封面图与页脚" name="cover">
						<el-form label-width="120px" size="small">
							<el-form-item label="封面图">
								<div class="cover">
									<div class="cover-preview">
										<img v-if="coverUrl" :src="coverUrl" alt="cover" />
										<span v-else class="muted">无</span>
									</div>
									<div class="cover-ops">
										<el-input v-model="selected.template.cover.image" placeholder="assets/xxx.jpg" size="small" />
										<input class="file" type="file" accept="image/*" @change="onCover" />
									</div>
								</div>
							</el-form-item>
							<el-form-item label="保险公司">
								<div class="rename-row">
									<el-select v-model="selected.template.meta.company" size="small" style="flex:1" @change="onCompanyChange">
										<el-option v-for="c in companies" :key="c.code" :value="c.code" :label="`${c.name}（${c.code}）`" />
									</el-select>
									<el-button size="small" @click="companyVisible = true">管理公司</el-button>
								</div>
							</el-form-item>
							<el-form-item label="品牌名 brand">
								<el-input v-model="selected.template.meta.brand" />
							</el-form-item>
							<el-form-item label="页脚 footer">
								<el-input v-model="selected.template.meta.footer" />
							</el-form-item>
						</el-form>
					</el-collapse-item>

					<el-collapse-item v-for="c in styleCards" :key="c.rawIdx" :name="'card' + c.rawIdx">
						<template #title>
							<span class="card-title">{{ c.styleIdx + 1 }}. {{ roleName(c.card.role) }}</span>
						</template>
						<el-button size="small" type="primary" plain @click.stop="activate(c)">预览此卡</el-button>
						<el-form label-width="120px" size="small" class="card-form">
							<el-form-item v-if="c.card.title !== undefined" label="标题 title">
								<el-input v-model="c.card.title" />
							</el-form-item>
							<el-form-item v-if="c.card.subtitle !== undefined" label="副标 subtitle">
								<el-input v-model="c.card.subtitle" />
							</el-form-item>
							<el-form-item v-if="c.card.kicker !== undefined" label="kicker">
								<el-input v-model="c.card.kicker" />
							</el-form-item>
							<el-form-item v-for="f in strFields(c.card.bound_data)" :key="f" :label="f">
								<el-input v-model="c.card.bound_data[f]" />
							</el-form-item>
							<template v-for="arr in arrFields(c.card.bound_data)" :key="arr">
								<el-divider content-position="left">{{ arr }}（{{ (c.card.bound_data[arr] || []).length }}）</el-divider>
								<div v-for="(item, i) in c.card.bound_data[arr]" :key="i" class="arr-row">
									<template v-if="Array.isArray(item)">
										<el-input v-model="item[0]" placeholder="标签" />
										<el-input v-model="item[1]" placeholder="值" />
									</template>
									<el-input v-else-if="typeof item === 'string'" v-model="c.card.bound_data[arr][i]" />
									<template v-else>
										<el-input v-for="(v, k) in item" :key="k" v-model="item[k]" :placeholder="String(k)" />
									</template>
									<el-button link type="danger" @click="c.card.bound_data[arr].splice(i, 1)">删</el-button>
								</div>
								<el-button size="small" link type="primary" @click="addArrItem(c.card, arr)">+ 添加</el-button>
							</template>
						</el-form>
					</el-collapse-item>

					<el-collapse-item title="解析规则 parser.json（高级）" name="parser">
						<el-input v-model="parserText" type="textarea" :rows="14" class="json-area" />
						<el-button size="small" type="primary" :loading="savingParser" style="margin-top:8px" @click="saveParserDoc">保存 parser</el-button>
					</el-collapse-item>
				</el-collapse>
			</aside>

			<section class="te-right">
				<div class="preview-head">
					<span>卡片预览</span>
					<span v-if="previewing" class="muted">渲染中…</span>
				</div>
				<div v-if="previewMsg" class="preview-msg">{{ previewMsg }}</div>
				<div ref="previewWrap" class="preview-viewport" :style="{ height: previewBoxHeight + 'px' }">
					<iframe v-show="previewHtml" :srcdoc="previewHtml" class="preview-frame"
						:style="{ width: designW + 'px', height: designH + 'px', transform: `scale(${previewScale})` }" />
				</div>
			</section>
		</div>

		<el-dialog v-model="companyVisible" title="保险公司管理" width="600px" destroy-on-close>
			<el-table :data="companies" size="small" max-height="320">
				<el-table-column prop="code" label="代号" width="100" />
				<el-table-column prop="name" label="名称" min-width="180" />
				<el-table-column prop="sort" label="排序" width="80" align="center" />
				<el-table-column label="操作" width="90" align="center">
					<template #default="{ row }">
						<el-button size="small" type="danger" @click="removeCompany(row)">删除</el-button>
					</template>
				</el-table-column>
			</el-table>
			<div class="add-company">
				<el-input v-model="newCompany.code" placeholder="代号，如 YF" size="small" style="width:120px" />
				<el-input v-model="newCompany.name" placeholder="名称，如 YF Life 万通保险" size="small" style="flex:1" />
				<el-input-number v-model="newCompany.sort" :min="0" size="small" style="width:100px" />
				<el-button size="small" type="primary" :loading="savingCompany" @click="addCompany">添加</el-button>
			</div>
			<div class="muted" style="margin-top:8px">新增公司后，模板里即可在下拉中选择。</div>
		</el-dialog>

		<el-dialog v-model="editVisible" title="编辑模板" width="560px" destroy-on-close>
			<el-input v-model="editKeyword" placeholder="搜索产品名 / 代号" clearable style="margin-bottom:10px" />
			<el-table :data="filteredEditProducts" size="small" max-height="380" class="edit-table" @row-click="openEdit">
				<el-table-column prop="name" label="产品" min-width="220" />
				<el-table-column prop="id" label="代号" width="120" />
				<el-table-column label="状态" width="90" align="center">
					<template #default="{ row }">
						<el-tag v-if="row.draft" type="warning" size="small" effect="dark">草稿</el-tag>
						<el-tag v-else type="success" size="small" effect="dark">已发布</el-tag>
					</template>
				</el-table-column>
			</el-table>
			<div class="cat-foot muted">共 {{ filteredEditProducts.length }} 个 · 点击一行载入编辑器</div>
		</el-dialog>

		<el-dialog v-model="newVisible" title="新建卡片模板（AI 生成草稿）" width="620px" :close-on-click-modal="false" destroy-on-close>
			<div class="new-hint">
				上传一份「样例计划书 PDF」（必填）与「产品手册」（建议），选择参考产品；AI 会生成 parser 草稿并合并到参考模板，
				随后可在此编辑器微调 → 验证 → 发布。
			</div>
			<el-form :model="newForm" label-width="110px">
				<el-form-item label="产品代号" required>
					<el-input v-model="newForm.product_id" placeholder="小写字母/数字/下划线，如 ci-premium" />
				</el-form-item>
				<el-form-item label="参考产品" required>
					<el-select v-model="newForm.base_pid" style="width:100%">
						<el-option v-for="p in products" :key="p.id" :value="p.id" :label="`${p.name}（${p.id}）`" />
					</el-select>
				</el-form-item>
				<el-form-item label="保险公司">
					<el-select v-model="newForm.company" clearable style="width:100%" placeholder="选择保险公司（可选，之后也可改）">
						<el-option v-for="c in companies" :key="c.code" :value="c.code" :label="`${c.name}（${c.code}）`" />
					</el-select>
				</el-form-item>
				<el-form-item label="样例计划书" required>
					<input class="file" type="file" accept="application/pdf" @change="(e: any) => (newForm.proposal = e.target.files?.[0])" />
					<span class="muted">{{ newForm.proposal?.name || '未选择' }}</span>
				</el-form-item>
				<el-form-item label="产品手册">
					<input class="file" type="file" accept="application/pdf" @change="(e: any) => (newForm.brochure = e.target.files?.[0])" />
					<span class="muted">{{ newForm.brochure?.name || '可选' }}</span>
				</el-form-item>
			</el-form>
			<template #footer>
				<div style="text-align: right">
					<el-button type="primary" :loading="creating" @click="createDraft">AI 生成草稿</el-button>
					<el-button @click="newVisible = false">取消</el-button>
				</div>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="cardTemplates">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
	listAdminProducts, saveTemplate, saveParser, previewCard, uploadAsset, fetchAssetBlobUrl,
	aiDraft, validateDraft, publishDraft, renameProduct,
	listCompanies, createCompany, deleteCompany,
} from './api';

const loading = ref(true);
const saving = ref(false);
const savingParser = ref(false);
const previewing = ref(false);
const products = ref<any[]>([]);
const pid = ref('');
const selected = ref<any>(null);
const previewHtml = ref('');
const previewMsg = ref('');
const activeStyleIdx = ref(0);
const openPanels = ref<string[]>(['copy']);
const parserText = ref('');
const coverUrl = ref('');
const editVisible = ref(false);
const editKeyword = ref('');
const renameTo = ref('');
const companies = ref<any[]>([]);
const companyFilter = ref('');
const companyVisible = ref(false);
const savingCompany = ref(false);
const newCompany = ref({ code: '', name: '', sort: 1 });
const newVisible = ref(false);
const creating = ref(false);
const validating = ref(false);
const publishing = ref(false);
const newForm = ref<any>({ product_id: '', base_pid: '', company: '', proposal: null, brochure: null });
const previewWrap = ref<HTMLElement | null>(null);
const previewScale = ref(0.35);
let previewTimer: any = null;
let resizeObs: ResizeObserver | null = null;

const designW = computed(() => Number(selected.value?.template?.meta?.width) || 1080);
const designH = computed(() => Number(selected.value?.template?.meta?.height) || 1440);
const previewBoxHeight = computed(() => Math.round(designH.value * previewScale.value));

const updateScale = () => {
	const w = previewWrap.value?.clientWidth || 0;
	if (!w) return;
	const maxH = Math.max(320, window.innerHeight - 250);
	const s = Math.min(w / designW.value, maxH / designH.value);
	previewScale.value = Math.min(1, Math.max(0.12, s));
};

const observePreview = () => {
	nextTick(() => {
		updateScale();
		if (!resizeObs && previewWrap.value) {
			resizeObs = new ResizeObserver(updateScale);
			resizeObs.observe(previewWrap.value);
		}
	});
};

const filteredProducts = computed(() =>
	companyFilter.value ? products.value.filter((p) => p.company === companyFilter.value) : products.value
);

const onCompanyFilter = () => {
	if (pid.value && !filteredProducts.value.some((p) => p.id === pid.value)) {
		pid.value = filteredProducts.value[0]?.id || '';
	}
	if (pid.value) onSelect();
	else selected.value = null;
};

const filteredEditProducts = computed(() => {
	const k = editKeyword.value.trim().toLowerCase();
	if (!k) return products.value;
	return products.value.filter((p) =>
		[p.id, p.name].filter(Boolean).join(' ').toLowerCase().includes(k)
	);
});

const openEditPicker = () => {
	editKeyword.value = '';
	editVisible.value = true;
};

const openEdit = (row: any) => {
	if (!row) return;
	pid.value = row.id;
	onSelect();
	editVisible.value = false;
};

const copyStrFields = computed(() => {
	const c = selected.value?.template?.copy || {};
	return Object.keys(c).filter((k) => typeof c[k] === 'string' && !['plan_default', 'product_positioning'].includes(k));
});

const styleCards = computed(() => {
	const tpl = selected.value?.template;
	if (!tpl) return [];
	const out: any[] = [];
	(tpl.cards || []).forEach((card: any, rawIdx: number) => {
		const styles = card.styles || [];
		if (styles.length && !styles.includes('llm')) return;
		out.push({ rawIdx, styleIdx: out.length, card });
	});
	return out;
});

const ROLE_LABELS: Record<string, string> = {
	hero: '封面', summary: '摘要', numbers: '数字', coverage: '保障重点', multi: '多次赔付',
	points: '保障要点', chart: '现金价值图', irr: '收益率', reasons: '理由',
	letter: '致受保人信', essay: '人生阶段', company: '公司实力',
};
const roleName = (r: string) => ROLE_LABELS[r] || r;

const NON_TEXT_KEYS = ['items', 'stats', 'reasons', 'examples', 'stats_note', 'columns', 'rows', 'note', 'bars', 'pills', 'binds'];
const strFields = (bd: any) => Object.entries(bd || {}).filter(([k, v]) => typeof v === 'string' && !NON_TEXT_KEYS.includes(k)).map(([k]) => k);
const arrFields = (bd: any) => Object.entries(bd || {}).filter(([, v]) => Array.isArray(v)).map(([k]) => k);

const addArrItem = (card: any, arr: string) => {
	const list = card.bound_data[arr];
	if (!Array.isArray(list) || !list.length) return;
	const proto = list[0];
	if (typeof proto === 'string') list.push('');
	else if (Array.isArray(proto)) list.push(proto.map(() => ''));
	else {
		const o: any = {};
		Object.keys(proto).forEach((k) => (o[k] = ''));
		list.push(o);
	}
};

const onSelect = () => {
	const p = products.value.find((x) => x.id === pid.value);
	if (!p) {
		selected.value = null;
		return;
	}
	selected.value = JSON.parse(JSON.stringify(p));
	const t = selected.value.template;
	t.copy = t.copy || {};
	t.cover = t.cover || { image: '' };
	t.meta = t.meta || {};
	t.cards = t.cards || [];
	t.copy.positioning_points = Array.isArray(t.copy.positioning_points) ? t.copy.positioning_points : [];
	parserText.value = JSON.stringify(selected.value.parser || {}, null, 2);
	renameTo.value = selected.value.id;
	activeStyleIdx.value = 0;
	previewHtml.value = '';
	observePreview();
	refreshPreview();
};

const refreshPreview = async () => {
	if (!selected.value) return;
	previewing.value = true;
	previewMsg.value = '';
	try {
		const res: any = await previewCard(selected.value.id, activeStyleIdx.value, {}, null);
		if (res.code === 2000) previewHtml.value = res.data.html || '';
		else previewMsg.value = res.msg || '预览失败';
	} catch (e: any) {
		previewMsg.value = e?.message || '预览失败';
	} finally {
		previewing.value = false;
	}
};

const activate = (c: any) => {
	activeStyleIdx.value = c.styleIdx;
	refreshPreview();
};

const schedulePreview = () => {
	clearTimeout(previewTimer);
	previewTimer = setTimeout(refreshPreview, 800);
};
watch(() => selected.value?.template, () => schedulePreview(), { deep: true });
watch(designW, () => updateScale());
watch(() => selected.value?.id, () => observePreview());

watch(
	() => selected.value?.template?.cover?.image,
	async (p: string) => {
		if (coverUrl.value) URL.revokeObjectURL(coverUrl.value);
		coverUrl.value = '';
		if (p) {
			try {
				coverUrl.value = await fetchAssetBlobUrl(p);
			} catch {
				/* ignore */
			}
		}
	}
);

const onCover = async (e: any) => {
	const f = e.target.files?.[0];
	if (!f) return;
	try {
		const res: any = await uploadAsset(f);
		if (res.code === 2000) {
			selected.value.template.cover.image = res.data.path;
			ElMessage.success('已上传');
		} else ElMessage.error(res.msg || '上传失败');
	} catch (err: any) {
		ElMessage.error(err?.message || '上传失败');
	}
};

const save = async () => {
	if (!selected.value) return;
	saving.value = true;
	try {
		const res: any = await saveTemplate(selected.value.id, selected.value.template);
		if (res.code === 2000) {
			const newName = selected.value.template.copy?.plan_default || selected.value.id;
			selected.value.name = newName;
			const p = products.value.find((x) => x.id === selected.value.id);
			if (p) p.name = newName;
			ElMessage.success('模板已保存');
		} else ElMessage.error(res.msg || '保存失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		saving.value = false;
	}
};

const loadCompanies = async () => {
	try {
		const res: any = await listCompanies();
		if (res.code === 2000) companies.value = res.data || [];
	} catch {
		/* ignore */
	}
};

const onCompanyChange = (code: string) => {
	const c = companies.value.find((x) => x.code === code);
	if (c) selected.value.template.meta.brand = c.name;
};

const addCompany = async () => {
	const c = newCompany.value;
	if (!c.code || !c.name) {
		ElMessage.warning('请填写公司代号与名称');
		return;
	}
	savingCompany.value = true;
	try {
		const res: any = await createCompany({ code: c.code.trim(), name: c.name.trim(), sort: c.sort || 1, enabled: true });
		if (res.code === 2000) {
			ElMessage.success('已添加');
			newCompany.value = { code: '', name: '', sort: 1 };
			await loadCompanies();
		} else ElMessage.error(res.msg || '添加失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '添加失败');
	} finally {
		savingCompany.value = false;
	}
};

const removeCompany = async (row: any) => {
	try {
		await ElMessageBox.confirm(`确认删除公司「${row.name}」？（已归类的产品会回退到 brand 文本）`, '删除公司', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deleteCompany(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		await loadCompanies();
	} else ElMessage.error(res.msg || '删除失败');
};

const doRename = async () => {
	if (!selected.value) return;
	const newId = renameTo.value.trim();
	if (!newId || newId === selected.value.id) return;
	try {
		await ElMessageBox.confirm(
			`确认把产品代号「${selected.value.id}」改为「${newId}」？\n将重命名产品目录并同步模板/解析规则引用；历史生成任务仍保留旧代号。`,
			'重命名产品代号',
			{ type: 'warning' }
		);
	} catch {
		return;
	}
	try {
		const res: any = await renameProduct(selected.value.id, newId);
		if (res.code === 2000) {
			ElMessage.success('产品代号已更新');
			await load();
			pid.value = newId;
			onSelect();
		} else ElMessage.error(res.msg || '重命名失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '重命名失败');
	}
};

const openNew = () => {
	newForm.value = { product_id: '', base_pid: products.value[0]?.id || '', company: '', proposal: null, brochure: null };
	newVisible.value = true;
};

const createDraft = async () => {
	const f = newForm.value;
	if (!f.product_id || !f.base_pid || !f.proposal) {
		ElMessage.warning('请填写产品代号、参考产品，并上传样例计划书');
		return;
	}
	creating.value = true;
	try {
		const fd = new FormData();
		fd.append('product_id', f.product_id);
		fd.append('base_pid', f.base_pid);
		if (f.company) fd.append('company', f.company);
		fd.append('proposal', f.proposal);
		if (f.brochure) fd.append('brochure', f.brochure);
		const res: any = await aiDraft(fd);
		if (res.code === 2000) {
			ElMessage.success('草稿已生成，请调整后验证/发布');
			newVisible.value = false;
			await load();
			pid.value = res.data.product;
			onSelect();
		} else ElMessage.error(res.msg || '生成失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '生成失败');
	} finally {
		creating.value = false;
	}
};

const validateDraftNow = async () => {
	if (!selected.value) return;
	validating.value = true;
	try {
		const res: any = await validateDraft(selected.value.id);
		if (res.code === 2000) {
			const d = res.data;
			if (d.ok) ElMessage.success(`验证通过：${d.card_count} 张卡，关键字段齐全`);
			else ElMessageBox.alert(`缺少字段：${(d.missing || []).join(', ') || '-'}\n卡片数：${d.card_count}`, '验证未通过', { type: 'warning' });
		} else ElMessage.error(res.msg || '验证失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '验证失败');
	} finally {
		validating.value = false;
	}
};

const publishNow = async () => {
	if (!selected.value) return;
	try {
		await ElMessageBox.confirm('发布后渠道即可使用，确认发布？', '发布模板', { type: 'warning' });
	} catch {
		return;
	}
	const pidValue = selected.value.id;
	publishing.value = true;
	try {
		const res: any = await publishDraft(pidValue);
		if (res.code === 2000) {
			ElMessage.success('已发布');
			await load();
			pid.value = pidValue;
			onSelect();
		} else ElMessage.error(res.msg || '发布失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '发布失败');
	} finally {
		publishing.value = false;
	}
};

const saveParserDoc = async () => {
	if (!selected.value) return;
	let parsed: any;
	try {
		parsed = JSON.parse(parserText.value);
	} catch {
		ElMessage.error('parser JSON 格式错误');
		return;
	}
	savingParser.value = true;
	try {
		const res: any = await saveParser(selected.value.id, parsed);
		if (res.code === 2000) {
			selected.value.parser = parsed;
			ElMessage.success('parser 已保存');
		} else ElMessage.error(res.msg || '保存失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		savingParser.value = false;
	}
};

const load = async () => {
	loading.value = true;
	await loadCompanies();
	try {
		const res: any = await listAdminProducts();
		if (res.code === 2000) {
			products.value = res.data || [];
			if (products.value.length) {
				pid.value = products.value[0].id;
				onSelect();
			}
		} else ElMessage.error(res.msg || '加载失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

onMounted(() => {
	load();
	window.addEventListener('resize', updateScale);
});
onUnmounted(() => {
	window.removeEventListener('resize', updateScale);
	if (previewTimer) clearTimeout(previewTimer);
	if (resizeObs) {
		resizeObs.disconnect();
		resizeObs = null;
	}
	if (coverUrl.value) URL.revokeObjectURL(coverUrl.value);
});
</script>

<style scoped lang="scss">
.te {
	--t-card: #1a1a1c;
	--t-border: #2a2a2a;
	--t-text: #dadada;
	--t-muted: #b1b4b8;
	--t-faint: #8f9297;
	color: var(--t-text);

	.te-bar {
		display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px;
	}
	.te-title { font-size: 18px; font-weight: 600; color: #eaeaea; margin: 0; }
	.te-select { width: 300px; }
	.te-actions { margin-left: auto; display: flex; gap: 10px; }
	.te-empty { color: var(--t-faint); padding: 40px; text-align: center; }
	.te-body { display: grid; grid-template-columns: minmax(360px, 46%) 1fr; gap: 14px; align-items: start; }
	.te-left {
		background: var(--t-card); border: 1px solid var(--t-border); border-radius: 12px; padding: 8px 12px;
		max-height: calc(100vh - 170px); overflow: auto;
	}
	.point-row { display: flex; gap: 8px; width: 100%; margin-bottom: 6px; }
	.cover { display: flex; gap: 12px; width: 100%; }
	.cover-preview { width: 90px; height: 120px; border: 1px solid var(--t-border); border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center; background: #141414; }
	.cover-preview img { width: 100%; height: 100%; object-fit: cover; }
	.cover-ops { flex: 1; display: flex; flex-direction: column; gap: 8px; }
	.file { color: var(--t-muted); font-size: 12px; }
	.card-title { color: var(--t-text); font-size: 13px; }
	.card-form { margin-top: 10px; }
	.arr-row { display: flex; gap: 8px; width: 100%; margin-bottom: 6px; align-items: center; }
	.json-area :deep(textarea) { font-family: ui-monospace, monospace; font-size: 12px; }
	.muted { color: var(--t-faint); font-size: 12px; }
	.edit-table :deep(.el-table__row) { cursor: pointer; }
	.co-select { width: 190px; }
	.rename-row { display: flex; gap: 8px; width: 100%; }
	.add-company { display: flex; gap: 8px; margin-top: 12px; align-items: center; }
	.new-hint {
		font-size: 12.5px; line-height: 1.7; color: var(--t-muted);
		background: rgba(64, 158, 255, 0.08); border: 1px solid rgba(64, 158, 255, 0.25);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;
	}

	.te-right {
		background: var(--t-card); border: 1px solid var(--t-border); border-radius: 12px; padding: 12px;
		position: sticky; top: 0;
	}
	.preview-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 13px; color: var(--t-muted); }
	.preview-msg { color: #f56c6c; font-size: 12px; margin-bottom: 8px; }
	.preview-viewport {
		position: relative; width: 100%; overflow: hidden;
		background: #0f0f0f; border-radius: 8px;
	}
	.preview-frame {
		position: absolute; top: 0; left: 0;
		border: 0; background: #fff; transform-origin: top left;
	}
}
</style>
