<template>
	<div class="portals-page">
		<div class="page-bar">
			<h2 class="page-title">保险公司门户</h2>
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
			配置各保险公司的门户登录。内部用户在「计划书生成」中选择公司后，系统会用这里的账号自动登录该门户。
			密码仅保存于服务器，界面不回显；留空表示不修改。
		</div>

		<el-table :data="list" v-loading="loading" size="small">
			<el-table-column prop="name" label="公司名称" min-width="200" />
			<el-table-column prop="code" label="代号" width="90" />
			<el-table-column prop="driver" label="驱动" width="120" />
			<el-table-column prop="account" label="登录账号" min-width="140" />
			<el-table-column label="密码" width="100">
				<template #default="{ row }">
					<el-tag :type="row.has_password ? 'success' : 'info'" size="small" effect="dark">
						{{ row.has_password ? '已设置' : '未设置' }}
					</el-tag>
				</template>
			</el-table-column>
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

		<el-dialog v-model="visible" :title="form.id ? '编辑公司' : '新增公司'" width="560px" :close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="96px" label-position="right">
				<el-form-item label="公司名称" required>
					<el-input v-model="form.name" placeholder="如 YF Life（萬通保險）" />
				</el-form-item>
				<el-form-item label="代号" required>
					<el-input v-model="form.code" placeholder="唯一标识，如 YF / AIA" />
				</el-form-item>
				<el-form-item label="门户驱动">
					<el-select v-model="form.driver" style="width:100%">
						<el-option value="yf" label="万通 YF Life" />
						<el-option value="aia" label="AIA 友邦" />
						<el-option value="other" label="其他" />
					</el-select>
				</el-form-item>
				<el-form-item label="门户地址">
					<el-input v-model="form.base_url" placeholder="https://proposal.yflife.app" />
				</el-form-item>
				<el-form-item label="登录账号"><el-input v-model="form.account" /></el-form-item>
				<el-form-item label="登录密码">
					<el-input v-model="form.password" type="password" show-password
						:placeholder="form.id ? '留空表示不修改' : '登录密码'" autocomplete="new-password" />
				</el-form-item>
				<el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
				<el-form-item label="排序"><el-input-number v-model="form.sort" :min="0" /></el-form-item>
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

<script setup lang="ts" name="adminPortals">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { listPortals, createPortal, updatePortal, deletePortal } from './api';

const list = ref<any[]>([]);
const loading = ref(false);
const visible = ref(false);
const saving = ref(false);
const form = ref<any>({});

const emptyForm = () => ({
	id: 0, name: '', code: '', driver: 'yf', base_url: '', account: '',
	password: '', enabled: true, sort: 1, remark: '',
});

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listPortals();
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
	form.value = { ...emptyForm(), ...row, password: '' };
	visible.value = true;
};

const save = async () => {
	if (!form.value.name || !form.value.code) {
		ElMessage.warning('请填写公司名称与代号');
		return;
	}
	saving.value = true;
	try {
		const payload = { ...form.value };
		delete payload.id;
		const res: any = form.value.id ? await updatePortal(form.value.id, payload) : await createPortal(payload);
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
		await ElMessageBox.confirm(`确认删除「${row.name}」？`, '删除', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deletePortal(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		load();
	} else ElMessage.error(res.msg || '删除失败');
};

onMounted(load);
</script>

<style scoped lang="scss">
.portals-page {
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
}
</style>
