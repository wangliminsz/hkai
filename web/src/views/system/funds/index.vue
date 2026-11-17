<template>
	<div class="funds-page">
		<div class="page-bar">
			<h2 class="page-title">飞书群列表</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
				<el-button type="primary" @click="openAdd">
					<el-icon style="margin-right:4px"><ele-Plus /></el-icon>新增飞书群
				</el-button>
			</div>
		</div>

		<div class="hint">
			添加你们的<b>飞书群机器人 Webhook</b>；系统会在<b>周一至周五</b>把当日基金榜单推送到这里<b>所有启用</b>的群
			（周一~周二：本周销售量 Top；周三~周五：年初以来最佳/最差）。周六、周日不推送。
		</div>

		<el-table :data="list" v-loading="loading" size="small">
			<el-table-column prop="name" label="群名称" min-width="160" />
			<el-table-column label="Webhook" min-width="320">
				<template #default="{ row }">
					<el-tooltip :content="row.webhook_url" placement="top" :show-after="300">
						<span class="mono">{{ truncate(row.webhook_url) }}</span>
					</el-tooltip>
				</template>
			</el-table-column>
			<el-table-column label="启用" width="90" align="center">
				<template #default="{ row }">
					<el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="dark">{{ row.enabled ? '启用' : '停用' }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
			<el-table-column label="操作" width="150" align="center" fixed="right">
				<template #default="{ row }">
					<el-button size="small" @click="openEdit(row)">编辑</el-button>
					<el-button size="small" type="danger" @click="remove(row)">删除</el-button>
				</template>
			</el-table-column>
		</el-table>

		<el-dialog v-model="visible" :title="form.id ? '编辑飞书群' : '新增飞书群'" width="560px" :close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="96px">
				<el-form-item label="群名称" required>
					<el-input v-model="form.name" placeholder="如 销售一群 / 香港团队" />
				</el-form-item>
				<el-form-item label="Webhook" required>
					<el-input v-model="form.webhook_url" type="textarea" :rows="2"
						placeholder="飞书群机器人 Webhook，https://open.feishu.cn/open-apis/bot/v2/hook/…" />
				</el-form-item>
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

<script setup lang="ts" name="fundBroadcast">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { listFundGroups, createFundGroup, updateFundGroup, deleteFundGroup } from './api';

const list = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const form = ref<any>({});

const emptyForm = () => ({ id: 0, name: '', webhook_url: '', enabled: true, remark: '' });
const truncate = (s: string) => (s && s.length > 60 ? s.slice(0, 60) + '…' : s);

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listFundGroups();
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
	if (!form.value.name || !form.value.webhook_url) {
		ElMessage.warning('请填写群名称与 Webhook');
		return;
	}
	saving.value = true;
	try {
		const payload = { ...form.value };
		delete payload.id;
		const res: any = form.value.id ? await updateFundGroup(form.value.id, payload) : await createFundGroup(payload);
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
		await ElMessageBox.confirm(`确认删除飞书群「${row.name}」？`, '删除', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deleteFundGroup(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		load();
	} else ElMessage.error(res.msg || '删除失败');
};

onMounted(load);
</script>

<style scoped lang="scss">
.funds-page {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
	}
	.mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--cn-muted, #b1b4b8); }
}
</style>
