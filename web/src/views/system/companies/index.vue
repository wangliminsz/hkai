<template>
	<div class="co-page">
		<div class="page-bar">
			<h2 class="page-title">保险公司管理</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
				<el-button type="primary" @click="openAdd">
					<el-icon style="margin-right:4px"><ele-Plus /></el-icon>新增公司
				</el-button>
			</div>
		</div>

		<div class="hint">
			这里维护卡片产品的「保险公司」字典；在「卡片模板 → 封面图与页脚 → 保险公司」里选择使用。
			删除公司后，相关产品会回退显示模板里的 brand 文本。
		</div>

		<el-table :data="list" v-loading="loading" size="small">
			<el-table-column prop="code" label="代号" width="120" />
			<el-table-column prop="name" label="公司名称" min-width="240" />
			<el-table-column prop="sort" label="排序" width="80" align="center" />
			<el-table-column label="启用" width="90" align="center">
				<template #default="{ row }">
					<el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="dark">{{ row.enabled ? '启用' : '停用' }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
			<el-table-column label="操作" width="150" align="center" fixed="right">
				<template #default="{ row }">
					<el-button size="small" @click="openEdit(row)">编辑</el-button>
					<el-button size="small" type="danger" @click="remove(row)">删除</el-button>
				</template>
			</el-table-column>
		</el-table>

		<el-dialog v-model="visible" :title="form.id ? '编辑公司' : '新增公司'" width="520px" :close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="96px">
				<el-form-item label="公司代号" required>
					<el-input v-model="form.code" :disabled="!!form.id" placeholder="如 YF / AIA / PRU（唯一）" />
				</el-form-item>
				<el-form-item label="公司名称" required>
					<el-input v-model="form.name" placeholder="如 YF Life 万通保险" />
				</el-form-item>
				<el-form-item label="排序"><el-input-number v-model="form.sort" :min="0" /></el-form-item>
				<el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
				<el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
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

<script setup lang="ts" name="companyManage">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { listCompanies, createCompany, updateCompany, deleteCompany } from './api';

const list = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const form = ref<any>({});

const emptyForm = () => ({ id: 0, code: '', name: '', sort: 1, enabled: true, remark: '' });

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listCompanies();
		if (res.code === 2000) list.value = res.data || [];
		else ElMessage.error(res.msg || '加载失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const openAdd = () => {
	form.value = emptyForm();
	visible.value = true;
};
const openEdit = (row: any) => {
	form.value = { ...emptyForm(), ...row };
	visible.value = true;
};

const save = async () => {
	if (!form.value.code || !form.value.name) {
		ElMessage.warning('请填写公司代号与名称');
		return;
	}
	saving.value = true;
	try {
		const payload = { ...form.value };
		delete payload.id;
		const res: any = form.value.id ? await updateCompany(form.value.id, payload) : await createCompany(payload);
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
		await ElMessageBox.confirm(`确认删除公司「${row.name}」？相关产品会回退显示 brand 文本。`, '删除公司', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deleteCompany(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		load();
	} else ElMessage.error(res.msg || '删除失败');
};

onMounted(load);
</script>

<style scoped lang="scss">
.co-page {
	.page-bar {
		display: flex; align-items: center; gap: 14px; margin-bottom: 14px;
	}
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
	}
}
</style>
