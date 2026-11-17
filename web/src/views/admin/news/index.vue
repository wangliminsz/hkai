<template>
	<div class="news-bc">
		<div class="page-bar">
			<h2 class="page-title">新闻推送</h2>
			<div class="bar-right">
				<el-button :loading="previewing" @click="genPreview">生成预览</el-button>
				<el-button type="primary" :loading="broadcasting" @click="broadcastNow">
					<el-icon style="margin-right:4px"><ele-Promotion /></el-icon>立即推送
				</el-button>
				<el-button :loading="loading" @click="loadHistory">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
			</div>
		</div>

		<div class="hint">
			点击「生成预览」会抓取启用中的新闻源并用 AI 生成今日简报（约 10-30 秒）；「立即推送」会把简报以飞书卡片发送到
			<b>全部渠道飞书群</b>，卡片含「📄 阅读文字版」「📋 阅读详细版」两个按钮（HTML 上传到 COS，公开可读）。
			每天 08:45 / 15:45 自动推送（cron）。
		</div>

		<section class="card">
			<div class="row-between">
				<div>
					<strong>{{ preview.title || '今日新闻简报' }}</strong>
					<span class="muted" v-if="preview.sources"> · {{ preview.sources.join(' / ') }} · {{ preview.item_count }} 条</span>
				</div>
				<el-tag v-if="preview.date" size="small" effect="dark" type="info">{{ preview.date }}</el-tag>
			</div>
			<pre class="content">{{ preview.summary || '点击右上角「生成预览」查看今日简报（会调用 AI，约 10-30 秒）' }}</pre>
		</section>

		<section class="card">
			<div class="row-between">
				<strong>推送历史</strong>
				<span class="muted">最近 50 条</span>
			</div>
			<el-table :data="list" size="small" class="hist">
				<el-table-column prop="id" label="#" width="70" />
				<el-table-column label="状态" width="100">
					<template #default="{ row }">
						<el-tag :type="tagType(row.status)" size="small" effect="dark">{{ row.status_label }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
				<el-table-column label="群(成功/总)" width="120" align="center">
					<template #default="{ row }">{{ row.ok_count }}/{{ row.total_groups }}<span v-if="row.fail_count" class="err"> ({{ row.fail_count }} 失败)</span></template>
				</el-table-column>
				<el-table-column prop="created_at" label="时间" width="180" />
				<el-table-column label="操作" width="90" align="center">
					<template #default="{ row }">
						<el-button size="small" @click="viewDetail(row)">查看</el-button>
					</template>
				</el-table-column>
			</el-table>
		</section>

		<el-dialog v-model="detailVisible" :title="detail ? `新闻推送 #${detail.id}` : '推送详情'" width="720px" destroy-on-close>
			<div v-if="detail">
				<div class="muted" style="margin-bottom:8px">
					状态：{{ detail.status_label }} · 成功 {{ detail.ok_count }}/{{ detail.total_groups }}
				</div>
				<div class="sub">标题</div>
				<div>{{ detail.title || '-' }}</div>
				<div class="sub">简报内容</div>
				<pre class="content">{{ detail.content || '（无）' }}</pre>
				<div v-if="detail.logs" class="sub">失败日志</div>
				<pre v-if="detail.logs" class="content err-log">{{ detail.logs }}</pre>
			</div>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="adminNews">
import { ref, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { previewNews, listNewsBroadcasts, createNewsBroadcast, getNewsBroadcast } from './api';

const preview = ref<any>({});
const list = ref<any[]>([]);
const loading = ref(false);
const previewing = ref(false);
const broadcasting = ref(false);
const detailVisible = ref(false);
const detail = ref<any>(null);
let timer: any = null;

const tagType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'info', failed: 'danger' } as any)[s] || 'info';

const loadHistory = async () => {
	loading.value = true;
	try {
		const res: any = await listNewsBroadcasts();
		if (res.code === 2000) list.value = res.data || [];
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const genPreview = async () => {
	previewing.value = true;
	try {
		const res: any = await previewNews();
		if (res.code === 2000) {
			preview.value = res.data;
			ElMessage.success('预览已生成');
		} else ElMessage.error(res.msg || '生成失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '生成失败');
	} finally {
		previewing.value = false;
	}
};

const poll = (id: number) => {
	clearInterval(timer);
	let n = 0;
	timer = setInterval(async () => {
		n++;
		try {
			const res: any = await getNewsBroadcast(id);
			if (res.code === 2000) {
				const idx = list.value.findIndex((x) => x.id === id);
				if (idx >= 0) list.value[idx] = res.data;
				if (res.data.status === 'succeeded' || res.data.status === 'failed' || n > 120) {
					clearInterval(timer);
					timer = null;
					broadcasting.value = false;
					loadHistory();
					if (res.data.status === 'succeeded') ElMessage.success(`推送完成：成功 ${res.data.ok_count}/${res.data.total_groups}`);
					else ElMessage.error('推送失败，查看历史详情');
				}
			}
		} catch {
			/* ignore */
		}
	}, 2500);
};

const broadcastNow = async () => {
	try {
		await ElMessageBox.confirm('确认立即生成新闻简报并推送到全部渠道飞书群？', '立即推送', { type: 'warning' });
	} catch {
		return;
	}
	broadcasting.value = true;
	try {
		const res: any = await createNewsBroadcast({ edition: 'manual' });
		if (res.code === 2000) {
			ElMessage.success('已提交，正在生成并推送');
			await loadHistory();
			poll(res.data.id);
		} else {
			broadcasting.value = false;
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		broadcasting.value = false;
		ElMessage.error(e?.message || '提交失败');
	}
};

const viewDetail = async (row: any) => {
	const res: any = await getNewsBroadcast(row.id);
	if (res.code === 2000) {
		detail.value = res.data;
		detailVisible.value = true;
	}
};

onMounted(loadHistory);
onUnmounted(() => {
	if (timer) clearInterval(timer);
});
</script>

<style scoped lang="scss">
.news-bc {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.muted { color: var(--cn-muted, #b1b4b8); font-size: 12.5px; }
	.err { color: #f56c6c; }
	.hint {
		font-size: 12.5px; line-height: 1.7; color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
	}
	.card {
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 12px; padding: 16px 18px; margin-bottom: 14px;
	}
	.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.content {
		margin: 12px 0 0; max-height: 380px; overflow: auto; background: #141414;
		border: 1px solid var(--cn-border, #2a2a2a); border-radius: 8px; padding: 10px 12px;
		font-size: 12px; line-height: 1.6; color: var(--cn-muted, #b1b4b8); white-space: pre-wrap;
	}
	.sub { margin-top: 12px; font-size: 13px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); }
	.err-log { color: #f56c6c; }
	.hist { margin-top: 10px; background: transparent; }
}
</style>
