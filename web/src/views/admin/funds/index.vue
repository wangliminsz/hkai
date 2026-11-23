<template>
	<div class="fund-bc">
		<div class="page-bar">
			<h2 class="page-title">基金推送</h2>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
				<el-button type="primary" :loading="broadcasting" :disabled="schedule && !schedule.send_today" @click="broadcastNow">
					<el-icon style="margin-right:4px"><ele-Promotion /></el-icon>立即推送
				</el-button>
				<el-button type="warning" :loading="analyzing" :disabled="schedule && !schedule.send_today" @click="analyzeNow">
					<el-icon style="margin-right:4px"><ele-MagicStick /></el-icon>生成分析卡片
				</el-button>
			</div>
		</div>

		<section class="card">
			<div class="row-between">
				<div>
					<strong>{{ todayLabel }}</strong>
					<span class="muted" v-if="schedule"> · 批次 {{ schedule.lot || '-' }} · {{ schedule.fund_count }} 只基金 · 目标群 {{ schedule.requested_groups }} 个</span>
				</div>
				<el-tag v-if="schedule" :type="schedule.send_today ? 'success' : 'warning'" size="small" effect="dark">
					{{ schedule.send_today ? '今日推送' : '周末不推送' }}
				</el-tag>
			</div>
			<pre class="content">{{ schedule?.content || '（加载中…）' }}</pre>
		</section>

		<section class="card">
			<div class="row-between">
				<strong>推送历史</strong>
				<span class="muted">最近 50 条</span>
			</div>
			<el-table :data="broadcasts" size="small" class="hist">
				<el-table-column prop="id" label="#" width="70" />
				<el-table-column label="状态" width="100">
					<template #default="{ row }">
						<el-tag :type="tagType(row.status)" size="small" effect="dark">{{ row.status_label }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column label="星期" width="90">
					<template #default="{ row }">{{ WEEKDAYS[row.weekday] }}</template>
				</el-table-column>
				<el-table-column prop="lot" label="批次" width="130" />
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

		<section class="card">
			<div class="row-between">
				<strong>深度分析历史</strong>
				<span class="muted">QVeris 逐只基金分析（最近 50 条）</span>
			</div>
			<el-table :data="analyses" size="small" class="hist">
				<el-table-column prop="id" label="#" width="70" />
				<el-table-column label="状态" width="100">
					<template #default="{ row }">
						<el-tag :type="tagType(row.status)" size="small" effect="dark">{{ row.status_label }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column prop="lot" label="批次" width="130" />
				<el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
				<el-table-column label="卡片(成功/总)" width="130" align="center">
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

		<el-dialog v-model="detailVisible" :title="detail ? `推送 #${detail.id}` : '推送详情'" width="720px" destroy-on-close>
			<div v-if="detail">
				<div class="muted" style="margin-bottom:8px">
					状态：{{ detail.status_label }} · {{ WEEKDAYS[detail.weekday] }} · 批次 {{ detail.lot }} · 成功 {{ detail.ok_count }}/{{ detail.total_groups }}
				</div>
				<div class="sub">消息内容</div>
				<pre class="content">{{ detail.content || '（无）' }}</pre>
				<div v-if="detail.logs" class="sub">失败日志</div>
				<pre v-if="detail.logs" class="content err-log">{{ detail.logs }}</pre>
			</div>
		</el-dialog>
	</div>
</template>

<script setup lang="ts" name="adminFunds">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getFundSchedule, listFundBroadcasts, createFundBroadcast, getFundBroadcast,
	createFundAnalysis, listFundAnalysis } from './api';

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const schedule = ref<any>(null);
const broadcasts = ref<any[]>([]);
const analyses = ref<any[]>([]);
const loading = ref(false);
const broadcasting = ref(false);
const analyzing = ref(false);
const detailVisible = ref(false);
const detail = ref<any>(null);
let timer: any = null;

const tagType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'info', failed: 'danger' } as any)[s] || 'info';
const todayLabel = computed(() => {
	if (!schedule.value) return '今日预览';
	return `${schedule.value.weekday_name || WEEKDAYS[schedule.value.weekday]} 推送预览`;
});

const load = async () => {
	loading.value = true;
	try {
		const [s, b, a]: any = await Promise.all([getFundSchedule(), listFundBroadcasts(), listFundAnalysis()]);
		if (s.code === 2000) schedule.value = s.data;
		if (b.code === 2000) broadcasts.value = b.data || [];
		if (a.code === 2000) analyses.value = a.data || [];
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const poll = (id: number) => {
	clearInterval(timer);
	let n = 0;
	timer = setInterval(async () => {
		n++;
		try {
			const res: any = await getFundBroadcast(id);
			if (res.code === 2000) {
				const idx = broadcasts.value.findIndex((x) => x.id === id);
				if (idx >= 0) broadcasts.value[idx] = res.data;
				if (res.data.status === 'succeeded' || res.data.status === 'failed' || n > 60) {
					clearInterval(timer);
					timer = null;
					broadcasting.value = false;
					analyzing.value = false;
					if (res.data.status === 'succeeded') ElMessage.success(`推送完成：成功 ${res.data.ok_count}/${res.data.total_groups}`);
					else ElMessage.error('推送失败，查看历史详情');
				}
			}
		} catch {
			/* ignore */
		}
	}, 2000);
};

const broadcastNow = async () => {
	try {
		await ElMessageBox.confirm('确认立即推送今日基金榜单到全部渠道飞书群？', '立即推送', { type: 'warning' });
	} catch {
		return;
	}
	broadcasting.value = true;
	try {
		const res: any = await createFundBroadcast({ weekday: schedule.value?.weekday });
		if (res.code === 2000) {
			ElMessage.success('已提交，正在推送');
			await load();
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

const analyzeNow = async () => {
	try {
		await ElMessageBox.confirm('将对今日每只基金调用 QVeris 生成深度分析并推送到全部渠道群（每只间隔约 20 秒，会消耗 QVeris 额度）。确认继续？', '生成分析卡片', { type: 'warning' });
	} catch {
		return;
	}
	analyzing.value = true;
	try {
		const res: any = await createFundAnalysis({ weekday: schedule.value?.weekday });
		if (res.code === 2000) {
			ElMessage.success('已提交，正在逐只生成分析');
			await load();
			poll(res.data.id);
		} else {
			analyzing.value = false;
			ElMessage.error(res.msg || '提交失败');
		}
	} catch (e: any) {
		analyzing.value = false;
		ElMessage.error(e?.message || '提交失败');
	}
};

const viewDetail = async (row: any) => {
	const res: any = await getFundBroadcast(row.id);
	if (res.code === 2000) {
		detail.value = res.data;
		detailVisible.value = true;
	}
};

onMounted(load);
onUnmounted(() => {
	if (timer) clearInterval(timer);
});
</script>

<style scoped lang="scss">
.fund-bc {
	.page-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
	.page-title { font-size: 18px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); margin: 0; }
	.bar-right { display: flex; gap: 10px; margin-left: auto; }
	.muted { color: var(--cn-muted, #b1b4b8); font-size: 12.5px; }
	.err { color: #f56c6c; }
	.credit-num { font-variant-numeric: tabular-nums; }
	.credit-num.warn { color: #e6a23c; }
	.credit-num.danger { color: #f56c6c; font-weight: 600; }

	.card {
		background: var(--cn-card, #1a1a1c); border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 12px; padding: 16px 18px; margin-bottom: 14px;
	}
	.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.content {
		margin: 12px 0 0; max-height: 340px; overflow: auto; background: #141414;
		border: 1px solid var(--cn-border, #2a2a2a); border-radius: 8px; padding: 10px 12px;
		font-size: 12px; line-height: 1.6; color: var(--cn-muted, #b1b4b8); white-space: pre-wrap;
	}
	.sub { margin-top: 12px; font-size: 13px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); }
	.err-log { color: #f56c6c; }
	.hist { margin-top: 10px; background: transparent; }
}
</style>
