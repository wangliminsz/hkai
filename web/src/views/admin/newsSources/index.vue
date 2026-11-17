<template>
	<div class="ns-page">
		<div class="page-bar">
			<h2 class="page-title">新闻源</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
				<el-button type="primary" @click="openAdd">
					<el-icon style="margin-right:4px"><ele-Plus /></el-icon>新增新闻源
				</el-button>
			</div>
		</div>

		<div class="hint">
			新闻播报会抓取这里<b>启用的源</b>。内置源直接选（华尔街见闻 / 36氪 / 腾讯 / Hacker News …）；
			其它网站用「RSS/Atom」类型填订阅地址即可（无需改代码）。
		</div>

		<el-table :data="list" v-loading="loading" size="small">
			<el-table-column prop="name" label="名称" min-width="150" />
			<el-table-column label="类型" width="100" align="center">
				<template #default="{ row }">
					<el-tag :type="row.kind === 'builtin' ? 'primary' : 'success'" size="small" effect="dark">
						{{ row.kind === 'builtin' ? '内置源' : 'RSS' }}
					</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="value" label="键名 / RSS 地址" min-width="300" show-overflow-tooltip />
			<el-table-column prop="keywords" label="关键词" min-width="120" show-overflow-tooltip />
			<el-table-column prop="limit" label="条数" width="70" align="center" />
			<el-table-column label="启用" width="80" align="center">
				<template #default="{ row }">
					<el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="dark">{{ row.enabled ? '启用' : '停用' }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="sort" label="排序" width="70" align="center" />
			<el-table-column label="操作" width="150" align="center" fixed="right">
				<template #default="{ row }">
					<el-button size="small" @click="openEdit(row)">编辑</el-button>
					<el-button size="small" type="danger" @click="remove(row)">删除</el-button>
				</template>
			</el-table-column>
		</el-table>

		<el-dialog v-model="visible" :title="form.id ? '编辑新闻源' : '新增新闻源'" width="560px" :close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="96px">
				<el-form-item label="名称" required><el-input v-model="form.name" placeholder="如 华尔街见闻 / 某博客" /></el-form-item>
				<el-form-item label="类型">
					<el-select v-model="form.kind" style="width:100%">
						<el-option value="builtin" label="内置源" />
						<el-option value="rss" label="RSS / Atom" />
					</el-select>
				</el-form-item>
				<el-form-item label="键名" v-if="form.kind === 'builtin'" required>
					<el-select v-model="form.value" filterable allow-create default-first-option style="width:100%" placeholder="选择或输入内置键">
						<el-option v-for="k in BUILTIN" :key="k" :value="k" :label="k" />
					</el-select>
				</el-form-item>
				<el-form-item label="RSS 地址" v-else required>
					<el-input v-model="form.value" placeholder="https://example.com/feed.xml" />
				</el-form-item>
				<el-form-item label="关键词"><el-input v-model="form.keywords" placeholder="逗号分隔（可选）" /></el-form-item>
				<el-form-item label="每源条数"><el-input-number v-model="form.limit" :min="1" :max="50" /></el-form-item>
				<el-form-item label="排序"><el-input-number v-model="form.sort" :min="0" /></el-form-item>
				<el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
			</el-form>
			<template #footer>
				<div style="text-align: right">
					<el-button type="primary" :loading="saving" @click="save">保存</el-button>
					<el-button @click="visible = false">取消</el-button>
				</div>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="adminNewsSources">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { listNewsSources, createNewsSource, updateNewsSource, deleteNewsSource } from '../news/api';

const BUILTIN = [
	'wallstreetcn', '36kr', 'tencent', 'weibo', 'hackernews', 'github', 'producthunt', 'v2ex',
	'lobsters', 'devto', 'sspai', 'infoq_cn',
	'reuters', 'bbc_top', 'bbc_world', 'bbc_chinese', 'guardian_world', 'aljazeera', 'france24',
	'aihot', 'tldr_ai', 'import_ai', 'arxiv', 'huggingface', 'international', 'ai_newsletters',
];
const list = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const form = ref<any>({});

const emptyForm = () => ({ id: 0, name: '', kind: 'builtin', value: '', keywords: '', limit: 10, sort: 1, enabled: true });

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listNewsSources();
		if (res.code === 2000) list.value = res.data || [];
		else ElMessage.error(res.msg || '加载失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const openAdd = () => { form.value = emptyForm(); visible.value = true; };
const openEdit = (row: any) => { form.value = { ...emptyForm(), ...row }; visible.value = true; };

const save = async () => {
	if (!form.value.name || !form.value.value) {
		ElMessage.warning('请填写名称与键名/RSS地址');
		return;
	}
	saving.value = true;
	try {
		const payload = { ...form.value };
		delete payload.id;
		const res: any = form.value.id ? await updateNewsSource(form.value.id, payload) : await createNewsSource(payload);
		if (res.code === 2000) {
			ElMessage.success('已保存');
			visible.value = false;
			load();
		} else ElMessage.error(res.msg || '保存失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		saving.value = false;
	}
};

const remove = async (row: any) => {
	try {
		await ElMessageBox.confirm(`确认删除新闻源「${row.name}」？`, '删除', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deleteNewsSource(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		load();
	} else ElMessage.error(res.msg || '删除失败');
};

onMounted(load);
</script>

<style scoped lang="scss">
.ns-page {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
	}
}
</style>
