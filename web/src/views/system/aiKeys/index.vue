<template>
	<div class="ai-key-page">
		<div class="page-head">
			<div>
				<h2 class="title">AI Key</h2>
				<p class="sub">
					配置渠道自己的 QVeris / DeepSeek / 视觉 / RAG Key。
					未配置时按超管策略回退平台 Key 或直接拒绝；Key 仅显示掩码，服务端加密存储。
				</p>
			</div>
		</div>

		<el-tabs v-model="tab" class="ai-tabs">
			<el-tab-pane label="AI 模型" name="models">
				<AiModelSettings title="AI 模型（单 Key）" />
			</el-tab-pane>
			<el-tab-pane label="QVeris Key 池" name="qveris">
				<QverisKeyPool title="QVeris Key 池（免费额度轮换）" />
			</el-tab-pane>
		</el-tabs>
	</div>
</template>

<script setup lang="ts" name="aiKeys">
import { ref } from 'vue';
import QverisKeyPool from '/@/views/system/funds/QverisKeyPool.vue';
import AiModelSettings from '/@/views/system/funds/AiModelSettings.vue';

const tab = ref('models');
</script>

<style scoped lang="scss">
.ai-key-page {
	padding: 8px 4px 40px;
	color: var(--cn-text, #dadada);

	.page-head {
		margin-bottom: 10px;
		.title {
			font-size: 22px;
			font-weight: 600;
			color: var(--cn-text-strong, #eaeaea);
			margin: 0 0 6px;
		}
		.sub {
			margin: 0;
			max-width: 900px;
			color: var(--cn-muted, #b1b4b8);
			font-size: 13px;
			line-height: 1.7;
		}
	}

	.ai-tabs {
		margin-top: 8px;
	}
}
</style>
