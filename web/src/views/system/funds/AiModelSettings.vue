<template>
	<section class="ai-models">
		<div class="row-between">
			<div class="pool-title">
				<strong>{{ title }}</strong>
				<span class="muted" v-if="!canWrite">（只读）</span>
			</div>
			<div class="muted" v-if="fallback !== null">
				渠道未配置时：{{ fallback ? '回退平台 Key' : '直接拒绝' }}
			</div>
		</div>

		<div class="hint">
			单 Key 配置（每渠道每个 provider 一条）。渠道配置后，相关功能优先使用渠道自己的 Key；
			未配置时按超管开关决定“回退平台”或“直接拒绝”。Key 只显示掩码，服务端加密存储。
			未配置的卡片内会给出 Base / 模型 / Key 的填写示例。
			RAG 的「模型」同时用于建索引（Index）与问答（Chat）——PageIndex 原本可分开配置，这里统一用一个模型。
		</div>

		<div class="cards">
			<div v-for="p in providers" :key="p.key" class="model-card">
				<div class="card-head">
					<div>
						<div class="name">{{ p.label }}</div>
						<div class="desc">{{ p.desc }}</div>
					</div>
					<el-tag :type="tagType(p.key)" size="small" effect="dark">{{ tagLabel(p.key) }}</el-tag>
				</div>

				<div v-if="rowFor(p.key)" class="key-row">
					<div class="masked">
						<span class="mono">{{ rowFor(p.key).key_mask || '-' }}</span>
						<span class="muted" v-if="rowFor(p.key).model">· {{ rowFor(p.key).model }}</span>
						<div class="muted">
							最近使用：{{ rowFor(p.key).last_used_at || '未使用' }}
							<span v-if="rowFor(p.key).used_count"> · {{ rowFor(p.key).used_count }} 次</span>
						</div>
					</div>
					<div class="key-actions">
						<el-switch :model-value="rowFor(p.key).is_active" :disabled="!canWrite"
							@change="(v: any) => toggle(p, v)" />
						<el-button size="small" :disabled="!canWrite" @click="openEdit(p)">编辑</el-button>
					</div>
				</div>

				<div v-else class="empty-block">
					<div class="sample">
						<div class="sample-row">
							<span>{{ p.short }} Base</span>
							<code>{{ p.defaultBase }}</code>
						</div>
						<div class="sample-row">
							<span>{{ p.short }} 模型</span>
							<code>{{ p.defaultModel }}</code>
						</div>
						<div class="sample-row">
							<span>{{ p.short }} Key</span>
							<code>sk-••••••••</code>
						</div>
					</div>
					<div class="empty-row">
						<el-button size="small" type="primary" :disabled="!canWrite" @click="openAdd(p)">配置 Key</el-button>
						<span class="muted" v-if="!canWrite">当前账号无编辑权限</span>
						<span class="muted" v-else>按上面示例填写即可；Base / 模型留空会用默认值</span>
					</div>
				</div>
			</div>
		</div>

		<el-dialog v-model="visible" :title="form.id ? `编辑 ${form.label}` : `配置 ${form.label}`" width="560px"
			:close-on-click-modal="false" destroy-on-close>
			<el-form :model="form" label-width="108px">
				<el-form-item label="API Key" :required="!form.id">
					<el-input v-model="form.api_key" type="password" show-password
						:placeholder="form.id ? '留空则不修改' : '填写该 provider 的 API Key'" />
				</el-form-item>
				<el-form-item label="Base URL">
					<el-input v-model="form.base_url" :placeholder="form.defaultBase" />
				</el-form-item>
				<el-form-item label="模型">
					<el-input v-model="form.model" :placeholder="form.defaultModel" />
					<div v-if="form.provider === 'pageindex'" class="muted" style="margin-top:4px;font-size:12px">
						PageIndex 建索引与问答共用这一个模型
					</div>
				</el-form-item>
				<el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
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

<script setup lang="ts" name="AiModelSettings">
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { createAiKey, getAiCredits, listAiKeys, updateAiKey } from '/@/api/aikeys';

const props = withDefaults(defineProps<{ scope?: 'tenant' | 'platform'; title?: string }>(), {
	scope: 'tenant',
	title: 'AI 模型',
});

const providers = [
	{
		key: 'deepseek',
		label: 'DeepSeek',
		short: 'DeepSeek',
		desc: '简报 / 文案 / 解析',
		defaultBase: 'https://api.deepseek.com',
		defaultModel: 'deepseek-flash',
	},
	{
		key: 'vllm',
		label: '视觉模型',
		short: '视觉',
		desc: '提交前截图核对',
		defaultBase: 'https://api.siliconflow.cn',
		defaultModel: 'Qwen/Qwen3-VL-30B-A3B-Instruct',
	},
	{
		key: 'pageindex',
		label: 'RAG 知识库',
		short: 'RAG',
		desc: 'PageIndex / 知识库检索',
		defaultBase: 'https://api.deepseek.com/v1',
		defaultModel: 'openai/deepseek-flash',
	},
];

const isPlatform = computed(() => props.scope === 'platform');
const items = ref<any[]>([]);
const canWrite = ref(false);
const fallback = ref<boolean | null>(null);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const form = ref<any>({});

const scopeParams = () => (isPlatform.value ? { tenant_id: 'platform' } : { scope: 'tenant' });
const rowFor = (key: string) => items.value.find((x) => x.provider === key);
const tagType = (key: string) => {
	const row = rowFor(key);
	if (!row) return 'info';
	return row.is_active ? 'success' : 'warning';
};
const tagLabel = (key: string) => {
	const row = rowFor(key);
	if (!row) return '未配置';
	return row.is_active ? '已配置' : '已停用';
};

const load = async () => {
	loading.value = true;
	try {
		const [keysRes, creditsRes]: any[] = await Promise.all([
			listAiKeys({ ...scopeParams() }),
			getAiCredits({ ...scopeParams() }),
		]);
		if (keysRes.code === 2000) {
			items.value = (keysRes.data || []).filter((x: any) => x.provider !== 'qveris');
		}
		if (creditsRes.code === 2000) {
			canWrite.value = !!creditsRes.data?.can_write;
			fallback.value = !!creditsRes.data?.fallback_to_global;
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '加载 AI 模型配置失败');
	} finally {
		loading.value = false;
	}
};

const emptyForm = (p: any) => ({
	id: 0,
	provider: p.key,
	label: p.label,
	name: p.label,
	api_key: '',
	base_url: p.defaultBase,
	model: p.defaultModel,
	defaultBase: p.defaultBase,
	defaultModel: p.defaultModel,
	is_active: true,
});

const openAdd = (p: any) => {
	form.value = emptyForm(p);
	visible.value = true;
};

const openEdit = (p: any) => {
	const row = rowFor(p.key);
	form.value = {
		...emptyForm(p),
		id: row.id,
		name: row.name || p.label,
		api_key: '',
		base_url: row.base_url || p.defaultBase,
		model: row.model || p.defaultModel,
		is_active: !!row.is_active,
	};
	visible.value = true;
};

const save = async () => {
	if (!form.value.id && !form.value.api_key) {
		ElMessage.warning('请填写 API Key');
		return;
	}
	saving.value = true;
	try {
		const payload: any = {
			provider: form.value.provider,
			name: form.value.name || form.value.label,
			api_key: form.value.api_key,
			base_url: form.value.base_url,
			model: form.value.model,
			is_active: form.value.is_active,
			extra: form.value.provider === 'pageindex' ? { index_model: form.value.model } : {},
			...scopeParams(),
		};
		const res: any = form.value.id
			? await updateAiKey(form.value.id, payload)
			: await createAiKey(payload);
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

const toggle = async (p: any, value: any) => {
	const row = rowFor(p.key);
	if (!row || !canWrite.value) return;
	const res: any = await updateAiKey(row.id, { is_active: !!value });
	if (res.code === 2000) {
		ElMessage.success(value ? '已启用' : '已停用');
		load();
	} else {
		ElMessage.error(res.msg || '操作失败');
	}
};

onMounted(load);
</script>

<style scoped lang="scss">
.ai-models {
	margin-top: 22px;
	.row-between { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
	.pool-title { display: flex; align-items: baseline; gap: 6px; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;
	}
	.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; align-items: stretch; }
	.model-card {
		display: flex; flex-direction: column;
		border: 1px solid var(--cn-border, #2a2a2a); background: var(--cn-card, #1a1a1c);
		border-radius: 12px; padding: 14px 16px;
	}
	.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
	.name { font-weight: 600; }
	.desc { font-size: 12.5px; color: var(--cn-muted, #b1b4b8); margin-top: 4px; }
	.key-row, .empty-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
	.key-row { margin-top: auto; padding-top: 14px; }
	.empty-block { margin-top: 12px; display: flex; flex-direction: column; flex: 1; }
	.empty-row { margin-top: auto; padding-top: 10px; }
	.sample {
		border: 1px dashed var(--cn-border, #2a2a2a); border-radius: 8px;
		background: rgba(255, 255, 255, 0.02); padding: 8px 12px; margin-bottom: 10px;
	}
	.sample-row {
		display: flex; justify-content: space-between; gap: 12px;
		font-size: 12.5px; line-height: 1.9;
		span { color: var(--cn-muted, #b1b4b8); flex-shrink: 0; }
		code {
			color: var(--cn-text, #dadada); font-family: ui-monospace, monospace;
			font-size: 12px; word-break: break-all; text-align: right;
		}
	}
	.key-actions { display: flex; align-items: center; gap: 10px; }
	.masked { min-width: 0; }
	.mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--cn-muted, #b1b4b8); }
	.muted { color: var(--cn-muted, #b1b4b8); font-size: 12.5px; }
}
</style>
