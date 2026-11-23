<template>
	<div class="ws">
		<div class="ws-head">
			<h2 class="title">
				工作台<span v-if="tenantName" class="co"> · {{ tenantName }}</span>
			</h2>
			<p class="hi">{{ hiText }}{{ userName }}，这是今天的概览。</p>
		</div>

		<div class="quick-grid">
			<router-link v-for="q in quicks" :key="q.path" :to="q.path" class="q-card" :class="{ primary: q.primary }">
				<el-icon class="q-icon"><component :is="q.icon" /></el-icon>
				<div class="q-body">
					<div class="q-title">{{ q.title }}</div>
					<div class="q-desc">{{ q.desc }}</div>
				</div>
				<el-icon class="q-arrow"><ele-ArrowRight /></el-icon>
			</router-link>
		</div>

		<div class="tip">
			<strong>提示</strong>
			基金 / 新闻推送会发送到渠道已启用的飞书群；单基金深度分析在「飞书群推送」页由内部用户触发。
		</div>
	</div>
</template>

<script setup lang="ts" name="homeWorkspace">
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useUserInfo } from '/@/stores/userInfo';
import { getDocAiAccess } from '/@/views/system/docai/api';

const { userInfos } = storeToRefs(useUserInfo());
const docaiAllowed = ref(false);

const userName = computed(() => userInfos.value.name || userInfos.value.username || '用户');
const tenantName = computed(() => userInfos.value.tenant_name || '');
const isInternal = computed(() => (userInfos.value.role_info || []).some((r: any) => r.key === 'internal'));
const isTenantManager = computed(() => (userInfos.value.role_info || []).some((r: any) => r.key === 'tenant_manager'));

const hiText = computed(() => {
	const h = new Date().getHours();
	if (h < 6) return '凌晨好，';
	if (h < 12) return '早上好，';
	if (h < 18) return '下午好，';
	return '晚上好，';
});

const quicks = computed(() => {
	const items = [
		{ path: '/rag', title: 'AI 知识库', desc: '产品问答 · 术语解释', icon: 'ele-Reading' },
	];
	if (isTenantManager.value) {
		items.unshift({
			path: '/ai-keys',
			title: 'AI Key',
			desc: '配置渠道自己的 QVeris / DeepSeek / 视觉 / RAG Key',
			icon: 'ele-Key',
			primary: true,
		});
	}
	if (docaiAllowed.value) {
		items.push({ path: '/docai', title: 'AI 文件分析', desc: '上传 PDF/图片 → 邮件报告', icon: 'ele-MagicStick' });
	}
	if (isInternal.value) {
		items.push(
			{ path: '/proposal', title: '计划书生成', desc: '内部用户可用', icon: 'ele-Document' },
			{ path: '/cardTemplates', title: '图文卡-模板', desc: '编辑 / 发布卡片模板', icon: 'ele-Setting' },
			{ path: '/companies', title: '图文卡-公司', desc: '保险公司资料维护', icon: 'ele-OfficeBuilding' }
		);
	}
	items.push(
		{ path: '/cards', title: '保险图文卡', desc: '计划书 → 图文卡', icon: 'ele-Picture' }
	);
	if (isTenantManager.value) {
		items.push(
			{ path: '/funds', title: '飞书群推送', desc: '基金 / 新闻 / 深度分析', icon: 'ele-TrendCharts' },
			{ path: '/org', title: '组织架构', desc: '创建 / 管理员工账号', icon: 'ele-Coordinate' }
		);
	}
	items.push({ path: '/personal', title: '个人中心', desc: '账号与密码', icon: 'ele-User' });
	return items;
});

onMounted(async () => {
	try {
		const res: any = await getDocAiAccess();
		docaiAllowed.value = res.code === 2000 && !!res.data?.allowed;
	} catch {
		docaiAllowed.value = false;
	}
});
</script>

<style scoped lang="scss">
.ws {
	padding: 8px 4px 40px;
	color: var(--cn-text, #dadada);

	.ws-head {
		margin-bottom: 22px;
		.title {
			font-size: 22px;
			font-weight: 600;
			color: var(--cn-text-strong, #eaeaea);
			margin: 0 0 6px;
			.co { color: var(--cn-muted, #b1b4b8); font-weight: 400; font-size: 16px; }
		}
		.hi { margin: 0; color: var(--cn-muted, #b1b4b8); font-size: 13.5px; }
	}

	.quick-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 14px;
	}

	.q-card {
		display: flex;
		align-items: center;
		gap: 14px;
		padding: 18px;
		border-radius: 12px;
		background: var(--cn-card, #1a1a1c);
		border: 1px solid var(--cn-border, #2a2a2a);
		color: inherit;
		text-decoration: none;
		transition: border-color 0.15s, transform 0.15s;

		&:hover {
			border-color: #3d5a80;
			transform: translateY(-1px);
		}
		&.primary {
			border-color: rgba(64, 158, 255, 0.55);
			background: linear-gradient(135deg, rgba(64, 158, 255, 0.12), var(--cn-card, #1a1a1c) 55%);
			.q-icon { color: #79bbff; }
		}
		.q-icon { font-size: 22px; color: #409eff; flex-shrink: 0; }
		.q-body { flex: 1; min-width: 0; }
		.q-title { font-size: 15px; font-weight: 600; color: var(--cn-text-strong, #eaeaea); }
		.q-desc { font-size: 12.5px; color: var(--cn-muted, #b1b4b8); margin-top: 4px; }
		.q-arrow { color: var(--cn-faint, #8f9297); }
	}

	.tip {
		margin-top: 22px;
		padding: 12px 16px;
		border-radius: 10px;
		background: var(--cn-card, #1a1a1c);
		border: 1px solid var(--cn-border, #2a2a2a);
		font-size: 12.5px;
		line-height: 1.7;
		color: var(--cn-muted, #b1b4b8);
		strong { color: var(--cn-text, #dadada); margin-right: 6px; }
	}
}
</style>
