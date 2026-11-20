<template>
  <div class="page--with-nav proposal">
    <AppNav title="计划书生成" back-to="/home" />

    <div class="hint" style="margin-top: 12px">
      选择保险公司 → 输入客户资料 → 系统自动登录门户生成计划书 PDF。仅内部用户可用。
    </div>

    <section class="card">
      <div class="form-field">
        <label>保险公司</label>
        <van-field
          v-model="portalLabel"
          class="soft-field"
          readonly
          is-link
          placeholder="请选择保险公司"
          @click="portalPicker = portals.length > 0"
        />
      </div>

      <van-collapse v-model="openProducts" class="prod-collapse">
        <van-collapse-item :title="`可生成计划书（${products.length} 个产品）`" name="products">
          <div v-if="!products.length" class="faint small">加载中…</div>
          <div v-for="p in products" :key="p.code" class="prod-item">
            <div class="prod-name">{{ p.name }} <span class="faint small">{{ p.category ? '· ' + p.category : '' }}</span></div>
            <div v-for="v in p.variants" :key="v.tier || 'default'" class="prod-variant">
              <span v-if="v.tier" class="tier">{{ v.tier }}</span>
              <span>{{ v.periods.join(' / ') }}</span>
            </div>
          </div>
        </van-collapse-item>
      </van-collapse>

      <div class="form-field">
        <div class="row-between" style="margin-bottom: 8px">
          <label style="margin: 0">客户资料</label>
          <button type="button" class="link-btn" @click="fillExample">填入示例</button>
        </div>
        <textarea
          v-model="text"
          rows="5"
          class="prompt-area"
          :placeholder="EXAMPLE_PROMPT"
        ></textarea>
      </div>

      <div class="drill-row">
        <div>
          <div class="drill-title">仅演练</div>
          <div class="faint small">不真正出单，也不会生成 PDF</div>
        </div>
        <van-switch v-model="drill" size="22" />
      </div>

      <van-button
        block
        round
        type="primary"
        size="large"
        class="submit-btn"
        :loading="submitting"
        :disabled="!text.trim() || !portalId"
        @click="submit"
      >
        开始生成
      </van-button>
    </section>

    <section v-if="job" class="card">
      <div class="row-between">
        <div class="row" style="gap: 8px; flex-wrap: wrap">
          <span class="job-id">#{{ job.id }}</span>
          <StatusBadge :status="job.status" />
          <span v-if="job.portal?.name" class="faint small">{{ job.portal.name }}</span>
        </div>
        <a
          v-if="job.status === 'succeeded' && job.download_url"
          class="dl-btn"
          :href="downloadHref(job)"
          :download="job.pdf_name || 'proposal.pdf'"
        >
          下载 PDF
        </a>
      </div>
      <p v-if="job.error" class="err-text" style="margin-top: 8px">{{ job.error }}</p>
      <pre class="logs">{{ job.logs || '（等待日志…）' }}</pre>
    </section>

    <section class="card">
      <div class="card-title">
        <span>生成历史</span>
        <button type="button" class="link-btn" :disabled="loading" @click="loadHistory">刷新</button>
      </div>
      <div v-if="!history.length" class="empty-box">暂无生成记录</div>
      <div v-else class="hist-list">
        <div v-for="row in history" :key="row.id" class="hist-item">
          <div class="hist-main">
            <div class="hist-title">
              <span class="job-id">#{{ row.id }}</span>
              <StatusBadge :status="row.status" />
            </div>
            <div class="hist-text">{{ row.text }}</div>
            <div class="faint small">{{ row.created_at }}</div>
          </div>
          <a
            v-if="row.status === 'succeeded' && row.download_url"
            class="dl-btn dl-btn--sm"
            :href="downloadHref(row)"
            :download="row.pdf_name || 'proposal.pdf'"
          >
            下载
          </a>
        </div>
      </div>
    </section>

    <van-popup v-model:show="portalPicker" position="bottom" round>
      <van-picker
        :columns="portalColumns"
        :columns-field-names="{ text: 'text', value: 'id' }"
        @cancel="portalPicker = false"
        @confirm="onPortalConfirm"
      />
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { showToast } from 'vant';
import AppNav from '@/components/AppNav.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import {
  createProposalJob,
  getPortals,
  getProposalJob,
  getProposalProducts,
  listProposalJobs,
  proposalDownloadHref,
} from '@/api/proposal';

const EXAMPLE_PROMPT =
  'Mr.VIP，男性，40 岁，非吸烟者，投保尚裕寿险，保额 100 万美元，缴费期 20 年，居住地中国大陆';

const portals = ref<any[]>([]);
const products = ref<any[]>([]);
const portalId = ref<number | ''>('');
const portalPicker = ref(false);
const openProducts = ref<string[]>([]);
const text = ref('');
const drill = ref(false);
const submitting = ref(false);
const loading = ref(false);
const job = ref<any>(null);
const history = ref<any[]>([]);
let timer: any = null;

const portalLabel = computed(() => portals.value.find((p) => p.id === portalId.value)?.name || '');
const portalColumns = computed(() =>
  portals.value.map((p) => ({ text: p.name, id: p.id }))
);

function fillExample() {
  text.value = EXAMPLE_PROMPT;
}

function onPortalConfirm({ selectedOptions }: any) {
  const id = selectedOptions?.[0]?.id;
  if (id) portalId.value = id;
  portalPicker.value = false;
}

async function loadPortals() {
  try {
    const res = await getPortals();
    portals.value = res?.data || [];
    if (portals.value.length && !portalId.value) portalId.value = portals.value[0].id;
  } catch (e: any) {
    showToast(e?.message || '加载公司失败');
  }
}

async function loadProducts() {
  try {
    const res = await getProposalProducts();
    products.value = res?.data || [];
  } catch (e: any) {
    showToast(e?.message || '加载产品失败');
  }
}

async function loadHistory() {
  loading.value = true;
  try {
    const res = await listProposalJobs();
    history.value = res?.data || [];
  } catch (e: any) {
    showToast(e?.message || '加载历史失败');
  } finally {
    loading.value = false;
  }
}

function poll() {
  if (timer) return;
  timer = setInterval(async () => {
    if (!job.value || (job.value.status !== 'queued' && job.value.status !== 'running')) {
      clearInterval(timer);
      timer = null;
      return;
    }
    try {
      const res = await getProposalJob(job.value.id);
      job.value = res?.data || job.value;
      if (job.value.status !== 'queued' && job.value.status !== 'running') {
        clearInterval(timer);
        timer = null;
        loadHistory();
      }
    } catch {
      /* keep polling */
    }
  }, 2500);
}

async function submit() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    const res = await createProposalJob({
      portal_id: portalId.value,
      text: text.value.trim(),
      create_pdf: !drill.value,
    });
    job.value = res?.data || null;
    showToast({ type: 'success', message: '已提交，正在后台生成' });
    poll();
    loadHistory();
  } catch (e: any) {
    showToast(e?.message || '提交失败');
  } finally {
    submitting.value = false;
  }
}

function downloadHref(row: any) {
  return proposalDownloadHref(row);
}

onMounted(async () => {
  await Promise.all([loadPortals(), loadProducts()]);
  loadHistory();
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.proposal {
  padding-bottom: calc(30px + var(--app-safe-bottom));
}
.form-field {
  margin-bottom: 14px;
}
.form-field label {
  display: block;
  margin: 0 0 8px 4px;
  font-size: 12px;
  color: var(--app-muted);
}
.soft-field {
  background: var(--app-card-2);
  border: 1px solid var(--app-border-strong);
  border-radius: 12px;
  padding: 10px 12px;
}
.prod-collapse {
  margin-bottom: 14px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
}
.prod-collapse :deep(.van-collapse-item__title),
.prod-collapse :deep(.van-collapse-item__content) {
  background: var(--app-card-2);
  color: var(--app-text);
}
.prod-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--app-border);
}
.prod-item:last-child {
  border-bottom: none;
}
.prod-name {
  font-size: 12.5px;
  color: var(--app-text);
  font-weight: 500;
}
.prod-variant {
  display: flex;
  gap: 8px;
  font-size: 11.5px;
  color: var(--app-muted);
  line-height: 1.7;
}
.prod-variant .tier {
  color: #8cc4ff;
}
.prompt-area {
  width: 100%;
  resize: vertical;
  border-radius: 12px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-card-2);
  color: var(--app-text);
  font: inherit;
  font-size: 13px;
  line-height: 1.65;
  padding: 10px 12px;
  outline: none;
}
.prompt-area:focus {
  border-color: rgba(74, 158, 255, 0.5);
}
.link-btn {
  background: none;
  border: none;
  color: var(--app-primary);
  font-size: 12.5px;
  cursor: pointer;
  padding: 0;
}
.link-btn:disabled {
  opacity: 0.4;
}
.drill-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 2px 14px;
}
.drill-title {
  font-size: 13px;
  color: var(--app-text);
  font-weight: 500;
}
.submit-btn {
  height: 48px;
}
.job-id {
  font-size: 12px;
  color: var(--app-faint);
}
.dl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  border-radius: 10px;
  background: var(--app-primary);
  color: #0f1a2a;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.dl-btn--sm {
  padding: 5px 10px;
  font-size: 11.5px;
}
.hist-list {
  display: flex;
  flex-direction: column;
}
.hist-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 2px;
  border-bottom: 1px solid var(--app-border);
}
.hist-item:last-child {
  border-bottom: none;
}
.hist-main {
  min-width: 0;
}
.hist-title {
  display: flex;
  align-items: center;
  gap: 7px;
}
.hist-text {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  max-width: 250px;
}
</style>
