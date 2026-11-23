<template>
	<section class="qveris-pool">
		<div class="row-between">
			<div class="pool-title">
				<strong>{{ title }}</strong>
				<span class="muted" v-if="summary">
					· {{ summary.count }} 个 Key · 合计 {{ formatCredit(summary.total) }} · 最低 {{ formatCredit(summary.lowest) }}
				</span>
			</div>
			<div class="bar-right">
				<el-button size="small" :loading="loading" @click="load(true)">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新余额
				</el-button>
				<el-button v-if="summary?.can_write" size="small" type="primary" @click="openAdd">
					<el-icon style="margin-right:4px"><ele-Plus /></el-icon>新增 Key
				</el-button>
			</div>
		</div>

		<div class="hint">
			每个渠道使用自己的 QVeris Key。多个 Key 会按 <b>LRU（最久未用优先）</b> 轮换，以充分利用免费额度；
			Key 耗尽/失效会自动停用，全部不可用时相关功能会被拒绝（<b>不会借用平台 Key</b>）。
			请遵守 QVeris 服务条款，不建议高频大规模调用。刷新余额会实时请求 QVeris，可能稍慢。
		</div>

		<el-table :data="items" v-loading="loading" size="small">
			<el-table-column prop="name" label="名称" min-width="120" />
			<el-table-column label="Key（脱敏）" min-width="150">
				<template #default="{ row }">
					<span class="mono">{{ row.key_mask || '-' }}</span>
				</template>
			</el-table-column>
			<el-table-column label="剩余额度" width="120" align="right">
				<template #default="{ row }">
					<span :class="{ danger: row.remain_credit !== null && row.remain_credit < 50 }">
						{{ formatCredit(row.remain_credit) }}
					</span>
				</template>
			</el-table-column>
			<el-table-column label="状态" width="110" align="center">
				<template #default="{ row }">
					<el-tooltip v-if="!row.is_active && row.last_error" :content="row.last_error" placement="top">
						<el-tag type="danger" size="small" effect="dark">停用</el-tag>
					</el-tooltip>
					<el-tag v-else :type="row.is_active ? 'success' : 'info'" size="small" effect="dark">
						{{ row.is_active ? '启用' : '停用' }}
					</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="last_used_at" label="最近使用" width="160" />
			<el-table-column prop="last_checked_at" label="最近检查" width="160" />
			<el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
			<el-table-column v-if="summary?.can_write" label="操作" width="210" align="center" fixed="right">
				<template #default="{ row }">
					<el-button size="small" @click="openEdit(row)">编辑</el-button>
					<el-button size="small" :loading="testingId === row.id" @click="test(row)">测试</el-button>
					<el-button size="small" type="danger" @click="remove(row)">删除</el-button>
				</template>
			</el-table-column>
		</el-table>

		<el-dialog v-model="visible" :title="form.id ? '编辑 QVeris Key' : '新增 QVeris Key'" width="560px"
			:close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="96px">
				<el-form-item label="名称">
					<el-input v-model="form.name" placeholder="如 免费号1 / 备用号" />
				</el-form-item>
				<el-form-item label="API Key" :required="!form.id">
					<el-input v-model="form.api_key" type="password" show-password
						:placeholder="form.id ? '留空则不修改' : 'QVeris API Key，如 sk-...'" />
				</el-form-item>
				<el-form-item label="Base URL">
					<el-input v-model="form.base_url" placeholder="默认 https://qveris.ai/api/v1" />
				</el-form-item>
				<el-form-item label="优先级">
					<el-input-number v-model="form.priority" :min="0" :max="999" />
					<span class="muted" style="margin-left:8px">数字越小越优先（LRU 同序时参考）</span>
				</el-form-item>
				<el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
				<el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
			</el-form>
			<template #footer>
				<div style="text-align: right">
					<el-button type="primary" :loading="saving" @click="save">保存</el-button>
					<el-button @click="visible = false">取消</el-button>
				</div>
			</template>
		</el-dialog>
	</section>
</template>

<script setup lang="ts" name="QverisKeyPool">
import { computed, onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { createAiKey, deleteAiKey, getAiCredits, testAiKey, updateAiKey } from '/@/api/aikeys';

const props = withDefaults(defineProps<{ scope?: 'tenant' | 'platform'; title?: string }>(), {
	scope: 'tenant',
	title: 'QVeris Key 池',
});

const isPlatform = computed(() => props.scope === 'platform');
const items = ref<any[]>([]);
const summary = ref<any>(null);
const loading = ref(false);
const saving = ref(false);
const testingId = ref(0);
const visible = ref(false);
const form = ref<any>({});

const emptyForm = () => ({ id: 0, name: '', api_key: '', base_url: '', priority: 10, is_active: true, remark: '' });
const scopeParams = () => (isPlatform.value ? { tenant_id: 'platform' } : { scope: 'tenant' });
const formatCredit = (n: any) =>
	n === null || n === undefined ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });

const load = async (refresh = false) => {
	loading.value = true;
	try {
		const res: any = await getAiCredits({ provider: 'qveris', ...scopeParams(), ...(refresh ? { refresh: 1 } : {}) });
		if (res.code === 2000) {
			summary.value = res.data;
			items.value = res.data?.items || [];
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
	form.value = emptyForm();
	visible.value = true;
};

const openEdit = (row: any) => {
	form.value = { ...emptyForm(), ...row, api_key: '' };
	visible.value = true;
};

const save = async () => {
	if (!form.value.id && !form.value.api_key) {
		ElMessage.warning('请填写 QVeris API Key');
		return;
	}
	saving.value = true;
	try {
		const payload: any = {
			provider: 'qveris',
			name: form.value.name,
			api_key: form.value.api_key,
			base_url: form.value.base_url,
			priority: form.value.priority,
			is_active: form.value.is_active,
			remark: form.value.remark,
			...(isPlatform.value ? { tenant_id: 'platform' } : { scope: 'tenant' }),
		};
		const res: any = form.value.id ? await updateAiKey(form.value.id, payload) : await createAiKey(payload);
		if (res.code === 2000) {
			ElMessage.success('已保存');
			visible.value = false;
			load();
		} else {
			ElMessage.error(res.msg || '保存失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		saving.value = false;
	}
};

const test = async (row: any) => {
	testingId.value = row.id;
	try {
		const res: any = await testAiKey(row.id);
		if (res.code === 2000) {
			const balance = formatCredit(res.data?.balance);
			ElMessage.success(balance === '-' ? '连接成功' : `连接成功，当前余额 ${balance}`);
		} else {
			ElMessage.error(res.msg || '测试失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '测试失败');
	} finally {
		testingId.value = 0;
		load();
	}
};

const remove = async (row: any) => {
	try {
		await ElMessageBox.confirm(`确认删除 QVeris Key「${row.name || row.key_mask}」？`, '删除', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await deleteAiKey(row.id);
	if (res.code === 2000) {
		ElMessage.success('已删除');
		load();
	} else {
		ElMessage.error(res.msg || '删除失败');
	}
};

onMounted(() => load());
</script>

<style scoped lang="scss">
.qveris-pool {
	margin-top: 22px;
	.row-between { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
	.pool-title { display: flex; align-items: baseline; gap: 4px; flex-wrap: wrap; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;
	}
	.mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--cn-muted, #b1b4b8); }
	.muted { color: var(--cn-muted, #b1b4b8); font-size: 12.5px; }
	.danger { color: #f56c6c; font-weight: 600; }
}
</style>
