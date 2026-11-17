<template>
	<div class="iu-page">
		<div class="page-bar">
			<h2 class="page-title">内部用户管理</h2>
			<el-input v-model="keyword" class="page-search" placeholder="搜索账号 / 姓名 / 邮箱" clearable
				@keyup.enter="load" @clear="load">
				<template #prefix>
					<el-icon class="search-ico" title="搜索" @click="load"><ele-Search /></el-icon>
				</template>
			</el-input>
			<div class="bar-right">
				<el-button :loading="loading" @click="load">
					<el-icon style="margin-right:4px"><ele-Refresh /></el-icon>刷新
				</el-button>
			</div>
		</div>

		<div class="hint">
			「内部用户」可以生成保险计划书；渠道用户即使通过审核也不能生成。打开开关即授予该用户 internal 角色。
		</div>

		<el-table :data="list" v-loading="loading" size="small">
			<el-table-column prop="username" label="账号" min-width="200" />
			<el-table-column prop="name" label="姓名" min-width="120" />
			<el-table-column prop="email" label="邮箱" min-width="220" />
			<el-table-column label="状态" width="90" align="center">
				<template #default="{ row }">
					<el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="dark">{{ row.is_active ? '正常' : '停用' }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column label="内部用户" width="110" align="center">
				<template #default="{ row }">
					<el-switch :model-value="row.is_internal" @change="(v: boolean) => toggle(row, v)" />
				</template>
			</el-table-column>
		</el-table>
	</div>
</template>

<script setup lang="ts" name="adminInternalUsers">
import { ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { listUsers, setInternal } from './api';

const list = ref<any[]>([]);
const loading = ref(false);
const keyword = ref('');

const load = async () => {
	loading.value = true;
	try {
		const res: any = await listUsers(keyword.value.trim());
		if (res.code === 2000) list.value = res.data.items || [];
		else ElMessage.error(res.msg || '加载失败');
	} catch (e: any) {
		ElMessage.error(e?.message || '加载失败');
	} finally {
		loading.value = false;
	}
};

const toggle = async (row: any, val: boolean) => {
	try {
		const res: any = await setInternal(row.id, val);
		if (res.code === 2000) {
			row.is_internal = val;
			ElMessage.success(val ? '已设为内部用户' : '已取消内部用户');
		} else {
			ElMessage.error(res.msg || '操作失败');
		}
	} catch (e: any) {
		ElMessage.error(e?.message || '操作失败');
	}
};

onMounted(load);
</script>

<style scoped lang="scss">
.iu-page {
	.page-bar {
		display: flex;
		align-items: center;
		gap: 14px;
		margin-bottom: 14px;
	}
	.page-title {
		font-size: 18px;
		font-weight: 600;
		color: var(--cn-text-strong, #eaeaea);
		margin: 0;
		flex: 0 0 auto;
	}
	.page-search {
		width: 300px;
	}
	.search-ico {
		cursor: pointer;
		color: var(--cn-muted, #b1b4b8);
		transition: color 0.2s;
	}
	.search-ico:hover {
		color: #409eff;
	}
	.bar-right {
		display: flex;
		gap: 10px;
		margin-left: auto;
	}
	.hint {
		font-size: 12.5px;
		line-height: 1.7;
		color: var(--cn-muted, #b1b4b8);
		background: var(--cn-card, #1a1a1c);
		border: 1px solid var(--cn-border, #2a2a2a);
		border-radius: 10px;
		padding: 10px 14px;
		margin-bottom: 14px;
	}
}
</style>
