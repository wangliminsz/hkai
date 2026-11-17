<template>
	<div class="signup-page">
		<header class="signup-header">
			<img :src="siteLogo" class="brand-mark" />
		</header>

		<main class="signup-panel">
			<div class="signup-card center-card" style="max-width: 460px">
				<div class="success-box">
					<div class="done-ico ok"><el-icon><ele-CircleCheck /></el-icon></div>
					<h1 class="card-title">{{ $t('message.pages.signup.pendingTitle') }}</h1>
					<p class="card-subtitle">{{ $t('message.pages.signup.pendingSubtitle', { company }) }}</p>
					<div class="card-actions">
						<el-button type="primary" round @click="relogin">{{ $t('message.pages.signup.goLogin') }}</el-button>
					</div>
				</div>
			</div>
		</main>

		<footer class="signup-footer">
			<p>{{ $t('message.pages.signup.footer') }}</p>
		</footer>
	</div>
</template>

<script lang="ts" setup name="signupPending">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { NextLoading } from '/@/utils/loading';
import { SystemConfigStore } from '/@/stores/systemConfig';
import { Session } from '/@/utils/storage';
import { APP_LOGO } from '/@/config/brand';
import _ from 'lodash-es';

const route = useRoute();
const router = useRouter();
const { systemConfig } = storeToRefs(SystemConfigStore());
const siteLogo = computed(() => {
	if (!_.isEmpty(systemConfig.value['login.site_logo'])) return systemConfig.value['login.site_logo'];
	return APP_LOGO;
});

const company = ref((route.query?.company as string) || '');

onMounted(() => {
	NextLoading.done();
});

const relogin = () => {
	Session.clear();
	router.push('/login');
};
</script>

<style scoped lang="scss">
@import './styles';

.done-ico {
	font-size: 52px;
	margin: 10px 0 4px;
	&.ok { color: #67c23a; }
}
</style>
