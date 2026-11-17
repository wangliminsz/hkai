<template>
	<div class="dashboard">
		<div class="stat-grid">
			<div v-for="card in cards" :key="card.label" class="stat-card">
				<div class="stat-icon" :style="{ background: card.color }">
					<el-icon><component :is="card.icon" /></el-icon>
				</div>
				<div class="stat-body">
					<div class="stat-value">{{ card.value }}</div>
					<div class="stat-label">{{ card.label }}</div>
				</div>
			</div>
		</div>

		<!-- 飞书群推送 -->
		<div class="panel">
			<div class="panel-title">飞书群推送</div>
			<div class="bc-grid">
				<div class="bc-item">
					<div class="bc-head">
						<span class="bc-name"><el-icon><ele-TrendCharts /></el-icon> 基金播报</span>
						<router-link to="/admin/funds" class="bc-link">去推送 →</router-link>
					</div>
					<div v-if="stat.last_fund" class="bc-body">
						<el-tag :type="bcType(stat.last_fund.status)" size="small" effect="dark">{{ stat.last_fund.status_label }}</el-tag>
						<span class="bc-meta">
							<template v-if="stat.last_fund.total > 0">成功 {{ stat.last_fund.ok }}/{{ stat.last_fund.total }}</template>
							<template v-else>未配置飞书群</template>
							· 最近一次 {{ stat.last_fund.created_at }}
						</span>
					</div>
					<div v-else class="bc-empty">暂无推送记录</div>
					<div class="bc-sub">周一/周二：本周销量 Top；周三~周五：年初以来最佳/最差（08:30）</div>
				</div>
				<div class="bc-item">
					<div class="bc-head">
						<span class="bc-name"><el-icon><ele-Notification /></el-icon> 新闻播报</span>
						<router-link to="/admin/news" class="bc-link">去推送 →</router-link>
					</div>
					<div v-if="stat.last_news" class="bc-body">
						<el-tag :type="bcType(stat.last_news.status)" size="small" effect="dark">{{ stat.last_news.status_label }}</el-tag>
						<span class="bc-meta">
							<template v-if="stat.last_news.total > 0">成功 {{ stat.last_news.ok }}/{{ stat.last_news.total }}</template>
							<template v-else>未配置飞书群</template>
							· 最近一次 {{ stat.last_news.created_at }}
						</span>
					</div>
					<div v-else class="bc-empty">暂无推送记录</div>
					<div class="bc-sub">每天两期：08:45 / 15:45（AI 简报）</div>
				</div>
			</div>
			<div class="bc-foot">渠道可在「基金播报」页自行添加飞书群；基金与新闻会推送到所有启用群。</div>
		</div>

		<!-- 快捷入口 -->
		<div class="panel">
			<div class="panel-title">快捷入口</div>
			<div class="quick-grid">
				<router-link v-for="q in quicks" :key="q.path" :to="q.path" class="quick-item">
					<el-icon class="quick-icon"><component :is="q.icon" /></el-icon>
					<div class="quick-body">
						<div class="quick-title">{{ q.title }}</div>
						<div v-if="q.desc" class="quick-desc">{{ q.desc }}</div>
					</div>
				</router-link>
			</div>
		</div>

		<!-- 环境配置 -->
		<div v-if="envGroupsNoAI.length" class="panel">
			<div class="panel-title">环境配置 (env)</div>
			<div class="env-groups">
				<div v-for="g in envGroupsNoAI" :key="g.group" class="env-group">
					<div class="env-group-title">{{ g.group }}</div>
					<div class="env-items">
						<div v-for="item in g.items" :key="item.key" class="env-row">
							<span class="env-label" :title="item.key">{{ item.label }}</span>
							<span class="env-value">{{ item.value === '' ? '（空）' : item.value }}</span>
						</div>
					</div>
				</div>
			</div>
			<div class="env-hint">
				以上为 <code>backend/conf/env.py</code> 配置（密钥已脱敏）；改动需重启后端生效。
			</div>
		</div>

		<!-- AI 模型 -->
		<div v-if="aiProviders.length" class="panel">
			<div class="panel-title">AI 模型</div>
			<div class="ai-grid">
				<div v-for="p in aiProviders" :key="p.name" class="ai-card">
					<div class="ai-card-title">{{ p.name }}</div>
					<div class="env-items">
						<div v-for="item in p.items" :key="item.key" class="env-row">
							<span class="env-label" :title="item.key">{{ item.label }}</span>
							<span class="env-value">{{ item.value === '' ? '（空）' : item.value }}</span>
						</div>
					</div>
				</div>
			</div>
			<div class="env-hint">
				以上为 <code>backend/conf/env.py</code>；DeepSeek 用于简报/文案/解析，视觉模型用于提交前截图核对，RAG 用于知识库检索。改完重启后端生效。
			</div>
		</div>

		<!-- AI 文件分析权限 -->
		<div class="panel">
			<div class="panel-title">AI 文件分析权限</div>
			<div class="bc-sub">控制谁能在「AI 文件分析」页上传 PDF/图片（分析报告发送到邮箱）。</div>
			<div class="perm-row">
				<label class="perm-item"><el-switch v-model="docai.allow_internal" /> 内部用户</label>
				<label class="perm-item"><el-switch v-model="docai.allow_manager" /> 渠道经理</label>
				<label class="perm-item"><el-switch v-model="docai.allow_member" /> 渠道成员</label>
				<el-button type="primary" size="small" :loading="docaiSaving" @click="saveDocAi">保存</el-button>
			</div>
		</div>

		<!-- Qveris API 额度 -->
		<div v-if="qveris" class="panel">
			<div class="panel-title">Qveris API 额度</div>
			<div class="qv-row">
				<div class="qv-main">
					<el-tag :type="qverisStatus.type" size="small" effect="dark">{{ qverisStatus.label }}</el-tag>
					<span class="qv-total">{{ formatCredit(qveris.total) }}</span>
					<span class="qv-meta">credits · {{ qveris.count }} 个 key · 最低 {{ formatCredit(qveris.lowest) }}</span>
				</div>
				<router-link to="/admin/funds" class="bc-link">查看明细 →</router-link>
			</div>
			<div class="bc-sub">用于基金分析（qveris.ai）；余额来自 PocketBase <code>qveris_keys</code>，更新于 {{ qveris.fetched_at }}，缓存 5 分钟。</div>
		</div>
	</div>
</template>

<script setup lang="ts" name="adminDashboard">
import { ref, computed, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { getDashboardStat, getEnvConfig, getQverisCredits, getDocAiSettings, updateDocAiSettings } from './api';

const stat = ref<any>({});
const envGroups = ref<any[]>([]);
const qveris = ref<any>(null);
const docai = ref<any>({ allow_internal: true, allow_manager: true, allow_member: true });
const docaiSaving = ref(false);

const cards = computed(() => [
	{ label: '渠道总数', value: stat.value.tenant_total ?? '-', icon: 'ele-OfficeBuilding', color: '#409eff' },
	{ label: '启用渠道', value: stat.value.tenant_active ?? '-', icon: 'ele-CircleCheck', color: '#67c23a' },
	{ label: '待审核渠道', value: stat.value.tenant_pending ?? '-', icon: 'ele-AlarmClock', color: '#e6a23c' },
	{ label: '内部用户', value: stat.value.internal_users ?? '-', icon: 'ele-UserFilled', color: '#7c5dfa' },
	{ label: '知识库产品', value: stat.value.kb_products ?? '-', icon: 'ele-Reading', color: '#13c2c2' },
	{ label: '卡片产品', value: stat.value.card_products ?? '-', icon: 'ele-Picture', color: '#eb2f96' },
	{ label: '保险公司', value: stat.value.card_companies ?? '-', icon: 'ele-OfficeBuilding', color: '#8c8c8c' },
	{ label: '渠道飞书群', value: stat.value.feishu_groups ?? '-', icon: 'ele-ChatDotRound', color: '#2f54eb' },
	{ label: '计划书任务', value: stat.value.proposal_jobs ?? '-', icon: 'ele-Document', color: '#fa8c16' },
	{ label: '新闻源', value: stat.value.news_sources ?? '-', icon: 'ele-MessageBox', color: '#faad14' },
]);

const quicks = computed(() => [
	{ path: '/admin/channels', title: '渠道审核', desc: `${stat.value.tenant_pending ?? '-'} 待审核`, icon: 'ele-List' },
	{ path: '/admin/kb', title: '知识库管理', desc: `${stat.value.kb_products ?? '-'} 个产品`, icon: 'ele-Reading' },
	{ path: '/admin/portals', title: '保险公司系统', desc: `${stat.value.portals ?? '-'} 个启用`, icon: 'ele-Connection' },
	{ path: '/admin/cards', title: '保险图文卡', desc: '上传计划书生成卡片', icon: 'ele-Picture' },
	{ path: '/admin/cardTemplates', title: '图文卡-模板', desc: `${stat.value.card_products ?? '-'} 已发布 / ${stat.value.card_drafts ?? 0} 草稿`, icon: 'ele-Setting' },
	{ path: '/admin/companies', title: '图文卡-公司', desc: `${stat.value.card_companies ?? '-'} 家`, icon: 'ele-OfficeBuilding' },
	{ path: '/admin/newsSources', title: '新闻源', desc: `${stat.value.news_sources ?? '-'} 个启用`, icon: 'ele-MessageBox' },
	{ path: '/admin/news', title: '新闻推送', desc: `${stat.value.news_broadcasts ?? 0} 次记录`, icon: 'ele-Notification' },
	{ path: '/admin/funds', title: '基金推送', desc: `${stat.value.fund_broadcasts ?? 0} 次记录`, icon: 'ele-TrendCharts' },
	{ path: '/admin/internalUsers', title: '内部用户', desc: '开通计划书生成权限', icon: 'ele-UserFilled' },
]);

const envGroupsNoAI = computed(() => envGroups.value.filter((g) => g.group !== 'AI 模型'));
const aiProviders = computed(() => {
	const g = envGroups.value.find((v) => v.group === 'AI 模型');
	if (!g) return [];
	const by = (prefix: string) => g.items.filter((i: any) => i.key.startsWith(prefix));
	return [
		{ name: 'DeepSeek（简报 / 文案 / 解析）', items: by('DEEPSEEK') },
		{ name: '视觉模型（提交前截图核对）', items: by('VLLM') },
		{ name: 'RAG 知识库（PageIndex）', items: by('PI') },
	].filter((p) => p.items.length);
});

const bcType = (s: string) => ({ succeeded: 'success', running: 'primary', queued: 'info', failed: 'danger' } as any)[s] || 'info';

const formatCredit = (n: any) => (n === null || n === undefined ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 }));

const qverisStatus = computed(() => {
	const low = qveris.value?.lowest;
	if (low === null || low === undefined) return { type: 'info', label: '未知' };
	if (low < 50) return { type: 'danger', label: '额度紧张' };
	if (low < 150) return { type: 'warning', label: '额度偏低' };
	return { type: 'success', label: '额度正常' };
});

onMounted(async () => {
	try {
		const [statRes, envRes]: any = await Promise.all([getDashboardStat(), getEnvConfig()]);
		if (statRes.code === 2000) stat.value = statRes.data || {};
		if (envRes.code === 2000) envGroups.value = envRes.data || [];
	} catch (e) {
		console.error('dashboard load failed', e);
	}
	try {
		const qvRes: any = await getQverisCredits();
		if (qvRes.code === 2000) qveris.value = qvRes.data || null;
	} catch (e) {
		console.error('qveris credits load failed', e);
	}
	try {
		const daRes: any = await getDocAiSettings();
		if (daRes.code === 2000) docai.value = daRes.data;
	} catch (e) {
		console.error('docai settings load failed', e);
	}
});

const saveDocAi = async () => {
	docaiSaving.value = true;
	try {
		const res: any = await updateDocAiSettings(docai.value);
		if (res.code === 2000) {
			docai.value = res.data;
			ElMessage.success('已保存');
		} else {
			ElMessage.error(res.msg || '保存失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '保存失败');
	} finally {
		docaiSaving.value = false;
	}
};
</script>

<style scoped lang="scss">
.dashboard {
	--cn-muted: #b1b4b8;
	--cn-border: #2a2a2a;
	--cn-text: #eaeaea;
	display: flex;
	flex-direction: column;
	gap: 24px;
	padding: 8px 4px 16px;
}

.stat-grid {
	display: grid;
	grid-template-columns: repeat(5, minmax(0, 1fr));
	gap: 18px;
}
@media (max-width: 1400px) {
	.stat-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 1100px) {
	.stat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 800px) {
	.stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
	.stat-grid { grid-template-columns: minmax(0, 1fr); }
}
.stat-card {
	background: #1a1a1c;
	border: 1px solid var(--cn-border);
	border-radius: 14px;
	padding: 20px;
	display: flex;
	align-items: center;
	gap: 16px;
	transition: border-color 0.2s ease;
	&:hover { border-color: #333333; }
	.stat-icon {
		width: 48px; height: 48px; border-radius: 12px;
		display: flex; align-items: center; justify-content: center;
		color: #fff; font-size: 22px; flex-shrink: 0;
	}
	.stat-body {
		.stat-value { font-size: 28px; font-weight: 600; color: var(--cn-text); line-height: 1.1; }
		.stat-label { font-size: 13px; color: var(--cn-muted); margin-top: 6px; }
	}
}

.panel {
	background: #1a1a1c;
	border: 1px solid var(--cn-border);
	border-radius: 14px;
	padding: 24px;
	.panel-title {
		font-size: 16px; font-weight: 600; color: var(--cn-text);
		margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid var(--cn-border);
	}
}

.bc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
.bc-item {
	border: 1px solid var(--cn-border); border-radius: 12px; padding: 16px 18px; background: #141414;
	.bc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
	.bc-name { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--cn-text); font-weight: 600; }
	.bc-link { font-size: 12px; color: #9ec9ff; text-decoration: none; }
	.bc-link:hover { color: #bcd9ff; }
	.bc-body { display: flex; align-items: center; gap: 10px; }
	.bc-meta { font-size: 12.5px; color: var(--cn-muted); }
	.bc-empty { font-size: 13px; color: var(--cn-faint, #8f9297); }
	.bc-sub { margin-top: 10px; font-size: 12px; color: var(--cn-muted); }
}
.bc-foot { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--cn-border); font-size: 12px; color: var(--cn-muted); }

.perm-row { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; margin-top: 4px; }
.perm-item { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--cn-text, #dadada); cursor: pointer; }

.qv-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.qv-main { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.qv-total { font-size: 26px; font-weight: 600; color: var(--cn-text); line-height: 1.1; }
.qv-meta { font-size: 12.5px; color: var(--cn-muted); }

.quick-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; }
.quick-item {
	display: flex; align-items: center; gap: 14px;
	border: 1px solid var(--cn-border); border-radius: 12px; padding: 14px 16px;
	background: #141414; text-decoration: none; transition: all 0.2s ease;
	&:hover { border-color: rgba(64, 158, 255, 0.5); background: #191c22; }
	.quick-icon { font-size: 22px; color: #9ec9ff; flex-shrink: 0; }
	.quick-title { font-size: 14px; color: var(--cn-text); font-weight: 500; }
	.quick-desc { margin-top: 4px; font-size: 12px; color: var(--cn-muted); }
}

.env-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 28px; }
.env-group {
	.env-group-title {
		font-size: 14px; font-weight: 600; color: #9ec9ff;
		margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--cn-border);
	}
}
.env-items {
	display: flex; flex-direction: column; gap: 10px;
	.env-row {
		display: flex; justify-content: space-between; align-items: center; gap: 16px; font-size: 13px;
		.env-label { color: var(--cn-muted); flex-shrink: 0; }
		.env-value {
			color: var(--cn-text); text-align: right; word-break: break-all; max-width: 68%;
			font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
		}
	}
}
.env-hint {
	margin-top: 20px; padding-top: 14px; border-top: 1px solid var(--cn-border);
	font-size: 12px; color: var(--cn-muted); line-height: 1.7;
	code { background: #212121; border: 1px solid var(--cn-border); border-radius: 6px; padding: 1px 6px; color: #9ec9ff; }
}

.ai-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
.ai-card {
	border: 1px solid var(--cn-border); border-radius: 12px; padding: 16px 18px; background: #141414;
	.ai-card-title { font-size: 13px; font-weight: 600; color: #b0a3ff; margin-bottom: 14px; }
}
</style>
