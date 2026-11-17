<template>
	<div class="channels">
		<!-- 工具栏 -->
		<div class="toolbar">
			<div class="left">
				<span class="title">{{ $t('message.pages.channels.title') }}</span>
				<span class="count" v-if="!loading">{{ $t('message.pages.channels.count', { n: filtered.length }) }}</span>
			</div>
			<div class="right">
				<el-input v-model="keyword" class="search-inp" :placeholder="$t('message.pages.channels.searchPlaceholder')" clearable>
					<template #prefix><el-icon class="search-ico"><ele-Search /></el-icon></template>
				</el-input>
				<el-button class="reload-btn" :loading="loading" @click="load">
					<el-icon style="margin-right: 4px"><ele-Refresh /></el-icon>{{ $t('message.pages.channels.refresh') }}
				</el-button>
			</div>
		</div>

		<!-- 空态 -->
		<div v-if="!loading && !filtered.length" class="empty">
			<div class="empty-ico"><el-icon><ele-CircleCheck /></el-icon></div>
			<div class="empty-txt">{{ $t('message.pages.channels.empty') }}</div>
		</div>

		<!-- 列表 -->
		<div v-else v-loading="loading" class="list-wrap">
			<el-table :data="filtered" size="default" stripe :header-cell-style="listHeaderStyle">
				<el-table-column :label="$t('message.pages.channels.colCompany')" min-width="160">
					<template #default="{ row }"><span class="cname">{{ row.name || row.username }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colAccount')" min-width="160">
					<template #default="{ row }"><span class="mono">{{ row.username }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colEmail')" min-width="190">
					<template #default="{ row }"><span class="muted">{{ row.email || $t('message.pages.channels.dash') }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colPhone')" min-width="130">
					<template #default="{ row }"><span class="muted">{{ row.mobile || $t('message.pages.channels.dash') }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colReferrer')" min-width="130">
					<template #default="{ row }"><span class="muted">{{ row.referrer || $t('message.pages.channels.dash') }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colApplied')" min-width="160">
					<template #default="{ row }"><span class="muted">{{ row.create_datetime || $t('message.pages.channels.dash') }}</span></template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colStatus')" width="120" align="center">
					<template #default="{ row }">
						<el-tag v-if="row.email_verified" type="info" size="small" effect="dark">{{ $t('message.pages.channels.statusPending') }}</el-tag>
						<el-tag v-else type="warning" size="small" effect="dark">{{ $t('message.pages.channels.statusUnverified') }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column :label="$t('message.pages.channels.colActions')" width="250" align="center" fixed="right">
					<template #default="{ row }">
						<el-button v-if="!row.email_verified" type="success" size="small" :loading="row._busy" @click="verify(row)">
							{{ $t('message.pages.channels.verify') }}
						</el-button>
						<el-button type="primary" size="small" :loading="row._busy" @click="approve(row)">
							{{ $t('message.pages.channels.approve') }}
						</el-button>
						<el-button size="small" :loading="row._busy" @click="reject(row)">
							{{ $t('message.pages.channels.reject') }}
						</el-button>
					</template>
				</el-table-column>
			</el-table>
		</div>
	</div>
</template>

<script setup lang="ts" name="adminChannels">
import { ref, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { GetPending, Approve, Reject, Verify } from './api';

const { t } = useI18n();
const listHeaderStyle = { background: '#1f1f1f', color: '#b1b4b8', borderColor: '#2a2a2a' };
const loading = ref(false);
const keyword = ref('');
const items = ref<any[]>([]);

const filtered = computed(() => {
	const kw = keyword.value.trim().toLowerCase();
	if (!kw) return items.value;
	return items.value.filter((it: any) =>
		(it.name || '').toLowerCase().includes(kw) ||
		(it.username || '').toLowerCase().includes(kw) ||
		(it.email || '').toLowerCase().includes(kw)
	);
});

const load = async () => {
	loading.value = true;
	try {
		const res: any = await GetPending();
		if (res.code === 2000) {
			items.value = (res.data || []).map((it: any) => ({ ...it, _busy: false }));
		}
	} catch (e) {
		ElMessage.error(t('message.pages.channels.loadFail'));
	} finally {
		loading.value = false;
	}
};

const approve = (row: any) => {
	ElMessageBox.confirm(t('message.pages.channels.approveConfirm'), '', { type: 'warning' })
		.then(async () => {
			row._busy = true;
			try {
				const res: any = await Approve({ user_id: row.id });
				if (res.code === 2000) {
					ElMessage.success(res.msg || t('message.pages.channels.approved'));
					await load();
				} else {
					ElMessage.warning(res.msg || t('message.pages.channels.actionFail'));
				}
			} catch (e) {
				ElMessage.error(t('message.pages.channels.actionFail'));
			} finally {
				row._busy = false;
			}
		})
		.catch(() => {});
};

const verify = (row: any) => {
	ElMessageBox.confirm(t('message.pages.channels.verifyConfirm'), '', { type: 'warning' })
		.then(async () => {
			row._busy = true;
			try {
				const res: any = await Verify({ user_id: row.id });
				if (res.code === 2000) {
					ElMessage.success(res.msg || t('message.pages.channels.verified'));
					await load();
				} else {
					ElMessage.warning(res.msg || t('message.pages.channels.actionFail'));
				}
			} catch (e) {
				ElMessage.error(t('message.pages.channels.actionFail'));
			} finally {
				row._busy = false;
			}
		})
		.catch(() => {});
};

const reject = (row: any) => {
	ElMessageBox.confirm(t('message.pages.channels.rejectConfirm'), '', { type: 'warning' })
		.then(async () => {
			let reason = '';
			try {
				const r = await ElMessageBox.prompt(t('message.pages.channels.rejectPrompt'), '', { inputValue: '' });
				reason = (r.value || '').trim();
			} catch (e) {
				return;
			}
			row._busy = true;
			try {
				const res: any = await Reject({ user_id: row.id, reason });
				if (res.code === 2000) {
					ElMessage.success(res.msg || t('message.pages.channels.rejected'));
					await load();
				} else {
					ElMessage.warning(res.msg || t('message.pages.channels.actionFail'));
				}
			} catch (e) {
				ElMessage.error(t('message.pages.channels.actionFail'));
			} finally {
				row._busy = false;
			}
		})
		.catch(() => {});
};

onMounted(load);
</script>

<style scoped lang="scss">
.channels {
	--cn-text: #eaeaea;
	--cn-muted: #b1b4b8;
	--cn-border: #2a2a2a;
	color: var(--cn-text);

	.toolbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 16px;

		.left .title { font-size: 18px; font-weight: 600; color: #f4f4f5; }
		.left .count { margin-left: 8px; font-size: 13px; color: #b1b4b8; }
		.right { display: flex; gap: 10px; align-items: center; }

		.search-inp {
			width: 260px;
			:deep(.el-input__wrapper) {
				background: #1a1a1c;
				box-shadow: 0 0 0 1px var(--cn-border) inset;
			}
			:deep(.el-input__inner) { color: var(--cn-text); }
		}
		.search-ico { color: #b1b4b8; }

		.reload-btn {
			background: rgba(64, 158, 255, 0.2);
			border-color: rgba(64, 158, 255, 0.35);
			color: #9ec9ff;
			&:hover, &:focus {
				background: rgba(64, 158, 255, 0.3);
				border-color: rgba(64, 158, 255, 0.5);
				color: #bcd9ff;
			}
		}
	}

	.empty {
		text-align: center;
		padding: 80px 0;
		color: var(--cn-muted);
		.empty-ico { font-size: 42px; color: #37373a; margin-bottom: 12px; }
		.empty-txt { font-size: 14px; }
	}

	.list-wrap {
		background: #1a1a1c;
		border: 1px solid var(--cn-border);
		border-radius: 12px;
		overflow: hidden;

		:deep(.el-table) {
			--el-table-border-color: #2a2a2a;
			--el-table-bg-color: transparent;
			--el-table-tr-bg-color: transparent;
			--el-table-header-bg-color: transparent;
			--el-table-row-hover-bg-color: rgba(255, 255, 255, 0.04);
			--el-table-text-color: #d8dade;
			--el-table-header-text-color: #b1b4b8;
			background: transparent;
			.el-table__cell { color: #d8dade; }
		}
	}

	.cname { color: #f4f4f5; font-weight: 500; }
	.mono { color: #9ec9ff; font-family: monospace; }
	.muted { color: #9b9da1; font-size: 13px; }
}
</style>
