<template>
	<div class="pt-page">
		<div class="page-bar">
			<h2 class="page-title">AI 提示词</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
			</div>
		</div>

		<div class="hint">
			这里可覆盖系统内置的 AI 提示词（留空/恢复默认 即用代码里的默认值）。基金深度分析、新闻播报在**下次运行**时生效。
			带 <code>{news_json}</code> / <code>{date}</code> 的提示词请保留占位符。
		</div>

		<div v-for="p in items" :key="p.key" class="card">
			<div class="row-between">
				<div class="ttl">
					<strong>{{ p.title }}</strong>
					<el-tag :type="p.is_custom ? 'warning' : 'info'" size="small" effect="dark" style="margin-left:8px">
						{{ p.is_custom ? '自定义' : '默认' }}
					</el-tag>
					<div class="key">{{ p.key }} · {{ p.hint }}</div>
				</div>
				<div class="ops">
					<el-button size="small" type="primary" :loading="saving === p.key" @click="save(p)">保存</el-button>
					<el-button size="small" :disabled="!p.is_custom" @click="reset(p)">恢复默认</el-button>
				</div>
			</div>
			<el-input v-model="p.content" type="textarea" :autosize="{ minRows: 4, maxRows: 16 }" spellcheck="false" />
		</div>
	</div>
</template>

<script setup lang="ts" name="adminPrompts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { listPrompts, updatePrompt, resetPrompt } from './api';

const items = ref<any[]>([]);
const loading = ref(false);
const saving = ref('');

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listPrompts();
		if (res.code === 2000) items.value = res.data || [];
		else ElMessage.error(res.msg || '加载失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const save = async (p: any) => {
	saving.value = p.key;
	try {
		const res: any = await updatePrompt(p.key, p.content);
		if (res.code === 2000) {
			ElMessage.success('已保存');
			p.is_custom = !!p.content.trim();
		} else ElMessage.error(res.msg || '保存失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		saving.value = '';
	}
};

const reset = async (p: any) => {
	try {
		await ElMessageBox.confirm(`确认将「${p.title}」恢复为默认提示词？`, '恢复默认', { type: 'warning' });
	} catch {
		return;
	}
	const res: any = await resetPrompt(p.key);
	if (res.code === 2000) {
		ElMessage.success('已恢复默认');
		load();
	} else ElMessage.error(res.msg || '操作失败');
};

onMounted(load);
</script>

<style scoped lang="scss">
.pt-page {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
	}
	.card {
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 12px; padding: 14px 16px; margin-bottom: 14px;
	}
	.row-between { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
	.ttl .key { margin-top: 4px; font-size: 12px; color: var(--cn-muted, #b1b4b8); }
	.ops { display: flex; gap: 8px; flex-shrink: 0; }
}
</style>
