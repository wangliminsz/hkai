<template>
	<div class="docai-page">
		<div class="page-bar">
			<h2 class="page-title">AI 文件分析</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="loadHistory">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
			</div>
		</div>

		<el-alert v-if="!allowed && checked" type="warning" :closable="false" show-icon
			title="你当前没有 AI 文件分析权限，请联系超级管理员开通。" />

		<template v-else>
			<div class="hint">
				上传 <b>PDF</b> 或 <b>图片</b>（PNG/JPEG/GIF/WebP/BMP，≤30MB），系统会用 QVeris AI 分析内容，
				并把 HTML 报告发送到下面填写的邮箱。分析通常需要 1–3 分钟。
			</div>

			<section class="card">
				<el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onFileRemove"
					:file-list="fileList" accept=".pdf,image/*" class="uploader">
					<el-icon class="up-ico"><ele-UploadFilled /></el-icon>
					<div class="up-text">将 PDF / 图片拖到此处，或 <em>点击选择</em></div>
				</el-upload>

				<div class="form-row">
					<span class="lbl">收件邮箱</span>
					<el-input v-model="email" placeholder="name@example.com（多个用逗号分隔）" style="max-width: 520px" />
					<el-button type="primary" :loading="submitting" :disabled="!file || !email" @click="submit">
						<el-icon style="margin-right:4px"><ele-MagicStick /></el-icon>开始分析
					</el-button>
				</div>

				<details class="prompts">
					<summary>分析 Prompt 设置 <span class="hint-inline">PDF/图片共用，可自定义</span></summary>
					<div class="prompt-row">
						<label>分析 Prompt（PDF / 图片通用）</label>
						<el-input v-model="prompt" type="textarea" :rows="8" resize="vertical" spellcheck="false" />
					</div>
					<div class="prompt-actions">
						<el-button size="small" :disabled="!defaultPrompt" @click="restorePrompt">恢复默认</el-button>
						<span class="muted">留空时使用后台默认 Prompt。</span>
					</div>
				</details>
			</section>

			<section v-if="current" class="card">
				<div class="row-between">
					<strong>当前任务 #{{ current.id }} · {{ current.filename }}</strong>
					<el-tag :type="statusType(current.status)" size="small" effect="dark">{{ statusLabel(current.status) }}</el-tag>
				</div>
				<div class="step">
					<el-icon v-if="current.status === 'queued' || current.status === 'running'" class="is-loading"><ele-Loading /></el-icon>
					{{ current.status === 'queued' ? '排队中…' : current.status === 'running' ? current.step : current.status === 'succeeded' ? '已完成，报告已发送到邮箱' : '失败' }}
				</div>
				<div v-if="current.error" class="err">{{ current.error }}</div>
				<div v-if="current.status === 'succeeded'" class="actions">
					<el-button size="small" type="primary" @click="openReport(current)">查看报告</el-button>
					<span class="muted">已发送至 {{ current.email }}</span>
				</div>
			</section>

			<section class="card">
				<div class="row-between">
					<strong>分析历史</strong>
					<span class="muted">最近 50 条</span>
				</div>
				<el-table :data="history" size="small" v-loading="loading">
					<el-table-column prop="id" label="#" width="70" />
					<el-table-column label="类型" width="80">
						<template #default="{ row }"><el-tag size="small" effect="plain">{{ row.kind === 'pdf' ? 'PDF' : '图片' }}</el-tag></template>
					</el-table-column>
					<el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
					<el-table-column prop="email" label="收件邮箱" min-width="200" show-overflow-tooltip />
					<el-table-column label="状态" width="100">
						<template #default="{ row }">
							<el-tag :type="statusType(row.status)" size="small" effect="dark">{{ statusLabel(row.status) }}</el-tag>
						</template>
					</el-table-column>
					<el-table-column prop="created_at" label="时间" width="170" />
					<el-table-column label="操作" width="100" align="center">
						<template #default="{ row }">
							<el-button size="small" :disabled="row.status !== 'succeeded'" @click="openReport(row)">查看报告</el-button>
						</template>
					</el-table-column>
				</el-table>
			</section>
		</template>
	</div>
</template>

<script setup lang="ts" name="docai">
import { ref, onMounted, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { storeToRefs } from 'pinia';
import { useUserInfo } from '/@/stores/userInfo';
import { Session } from '/@/utils/storage';
import { getBaseURL } from '/@/utils/baseUrl';
import { getDocAiAccess, getDocAiPrompts, analyzeDoc, listDocAiJobs, getDocAiJob } from './api';

const { userInfos } = storeToRefs(useUserInfo());
const allowed = ref(true);
const checked = ref(false);
const email = ref(userInfos.value.email || '');
const fileList = ref<any[]>([]);
const file = ref<File | null>(null);
const submitting = ref(false);
const loading = ref(false);
const history = ref<any[]>([]);
const current = ref<any>(null);
const prompt = ref('');
const defaultPrompt = ref('');
let timer: any = null;

const statusLabel = (s: string) => ({ queued: '排队中', running: '分析中', succeeded: '已完成', failed: '失败' } as any)[s] || s;
const statusType = (s: string) => ({ queued: 'info', running: 'primary', succeeded: 'success', failed: 'danger' } as any)[s] || 'info';

const onFileChange = (f: any) => {
	file.value = f.raw as File;
	fileList.value = [f];
};
const onFileRemove = () => {
	file.value = null;
	fileList.value = [];
};

const loadHistory = async () => {
	loading.value = true;
	try {
		const res: any = await listDocAiJobs();
		if (res.code === 2000) history.value = res.data || [];
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const loadPrompts = async () => {
	try {
		const res: any = await getDocAiPrompts();
		if (res.code === 2000) {
			defaultPrompt.value = res.data?.prompt || '';
			prompt.value = defaultPrompt.value;
		}
	} catch {
		defaultPrompt.value = '';
	}
};

const restorePrompt = () => {
	if (!defaultPrompt.value) return;
	prompt.value = defaultPrompt.value;
	ElMessage.success('已恢复默认 Prompt');
};

const poll = (id: number) => {
	if (timer) clearInterval(timer);
	timer = setInterval(async () => {
		try {
			const res: any = await getDocAiJob(id);
			if (res.code !== 2000) return;
			current.value = res.data;
			if (res.data.status === 'succeeded' || res.data.status === 'failed') {
				clearInterval(timer);
				timer = null;
				submitting.value = false;
				loadHistory();
				if (res.data.status === 'succeeded') ElMessage.success('分析完成，报告已发送到邮箱');
				else ElMessage.error('分析失败，请查看错误信息');
			}
		} catch {
			/* keep polling */
		}
	}, 2500);
};

const submit = async () => {
	if (!file.value) return ElMessage.warning('请选择文件');
	submitting.value = true;
	try {
		const res: any = await analyzeDoc(file.value, email.value, prompt.value);
		if (res.code === 2000) {
			ElMessage.success('已提交，正在分析…');
			current.value = { id: res.data.id, filename: file.value.name, status: 'queued', step: 'queued', email: email.value };
			poll(res.data.id);
			loadHistory();
		} else {
			submitting.value = false;
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		submitting.value = false;
		ElMessage.error(e?.message || '提交失败');
	}
};

const openReport = (row: any) => {
	const token = Session.get('token');
	window.open(getBaseURL(`/api/docai/jobs/${row.id}/report/?token=${encodeURIComponent(token)}`), '_blank');
};

onMounted(async () => {
	try {
		const res: any = await getDocAiAccess();
		if (res.code === 2000) allowed.value = !!res.data?.allowed;
	} catch {
		allowed.value = false;
	} finally {
		checked.value = true;
	}
	if (allowed.value) {
		loadPrompts();
		loadHistory();
	}
});

onUnmounted(() => {
	if (timer) clearInterval(timer);
});
</script>

<style scoped lang="scss">
.docai-page {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
		b { color: var(--cn-text, #dadada); }
	}
	.card {
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 12px; padding: 16px; margin-bottom: 14px;
	}
	.row-between { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
	.uploader { margin-bottom: 14px; :deep(.el-upload-dragger) { background: var(--cn-card-2, #212121); border-color: var(--cn-border, #2a2a2a); } }
	.up-ico { font-size: 40px; color: #409eff; margin-bottom: 6px; }
	.up-text { color: var(--cn-muted, #b1b4b8); font-size: 13px; em { color: #409eff; font-style: normal; } }
	.form-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
	.lbl { color: var(--cn-muted, #b1b4b8); font-size: 13px; }
	.prompts {
		margin-top: 16px; border: 1px solid var(--cn-border, #2a2a2a); border-radius: 8px;
		padding: 10px 14px; background: var(--cn-card-2, #212121);
		summary { cursor: pointer; font-size: 13.5px; font-weight: 600; color: var(--cn-text, #dadada); user-select: none; }
		.hint-inline { font-weight: 400; color: var(--cn-muted, #b1b4b8); margin-left: 6px; }
	}
	.prompt-row {
		margin-top: 14px;
		label { display: block; font-weight: 600; margin-bottom: 6px; font-size: 13px; color: var(--cn-muted, #b1b4b8); }
	}
	.prompt-actions { display: flex; align-items: center; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
	.step { display: flex; align-items: center; gap: 8px; color: var(--cn-text, #dadada); font-size: 13.5px; }
	.err { color: #f56c6c; font-size: 12.5px; margin-top: 8px; white-space: pre-wrap; }
	.actions { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
	.muted { color: var(--cn-muted, #b1b4b8); font-size: 12.5px; }
}
</style>
