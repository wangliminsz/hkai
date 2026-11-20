<template>
  <div class="page--with-nav cards">
    <AppNav title="保险图文卡" back-to="/home" />

    <div class="hint" style="margin-top: 12px">
      上传计划书 <b>PDF</b> → 自动识别产品 → 编辑文案 → 生成小红书 3:4 图文卡。数字均来自 PDF。
    </div>

    <section class="card upload-card">
      <input ref="fileInput" type="file" accept="application/pdf,.pdf" hidden @change="onFile" />
      <button type="button" class="upload-box" :disabled="detecting" @click="fileInput?.click()">
        <van-icon :name="detecting ? 'clock-o' : 'plus'" size="26" />
        <span class="upload-title">{{ fileObj ? fileName : '选择计划书 PDF' }}</span>
        <span class="upload-sub">{{ detecting ? '正在识别产品与文案…' : fileObj ? '点击重新选择文件' : '支持 PDF，单文件' }}</span>
      </button>
      <div class="support-line">
        <span class="faint small">已支持 {{ catalog.length }} 款产品 · {{ companies.length }} 家公司</span>
        <button type="button" class="link-btn" @click="catalogVisible = true">查看支持产品</button>
      </div>
    </section>

    <section v-if="detected" class="card">
      <div class="card-title">
        <span>识别结果</span>
        <StatusBadge status="succeeded" label="识别成功" />
      </div>
      <div class="detected-head">
        <div>
          <div class="plan-name">{{ detected.plan_name || chosenProductName || '未命名计划' }}</div>
          <div class="faint small">产品：{{ chosenProductName || detected.product }}（{{ chosenProduct || detected.product }}）· {{ detected.cards?.length || 0 }} 张卡</div>
        </div>
        <button type="button" class="link-btn" @click="productPicker = true">更换产品</button>
      </div>

      <div class="theme-row">
        <span class="label">主题</span>
        <div class="pill-group">
          <button
            v-for="t in THEMES"
            :key="t.value"
            type="button"
            class="chip"
            :class="{ 'chip--active': theme === t.value }"
            @click="theme = t.value"
          >
            {{ t.label }}
          </button>
        </div>
      </div>

      <van-collapse v-model="openCards" class="cards-collapse">
        <van-collapse-item v-for="c in detected.cards" :key="c.idx" :name="c.idx">
          <template #title>
            <span class="collapse-title">{{ c.idx + 1 }}. {{ c.name }}</span>
          </template>
          <template #value>
            <span class="faint small">{{ c.hint }}</span>
          </template>
          <div class="field-list">
            <div v-for="(val, key) in c.fields" :key="key" class="edit-field">
              <label>{{ key }}</label>
              <textarea
                :value="editValue(c.idx, key, val)"
                rows="2"
                @input="onEdit(c.idx, key, ($event.target as HTMLTextAreaElement).value, val)"
              ></textarea>
            </div>
          </div>
        </van-collapse-item>
      </van-collapse>

      <van-button block round type="primary" size="large" class="gen-btn" :loading="submitting" @click="generate">
        生成图文卡
      </van-button>
    </section>

    <section v-if="job" class="card">
      <div class="row-between">
        <div class="row" style="gap: 8px">
          <span class="job-id">#{{ job.id }}</span>
          <StatusBadge :status="job.status" :label="job.status_label" />
        </div>
        <van-button
          v-if="job.status === 'succeeded'"
          size="small"
          type="primary"
          plain
          :loading="downloading"
          @click="download()"
        >
          下载 ZIP
        </van-button>
      </div>

      <div v-if="job.status === 'queued' || job.status === 'running'" class="prog-wrap">
        <van-progress :percentage="job.progress || 0" stroke-width="7" color="#4a9eff" />
        <span class="faint small">{{ job.progress || 0 }}%</span>
      </div>

      <p v-if="job.error" class="err-text" style="margin-top: 10px">{{ job.error }}</p>

      <div v-if="previews.length" class="preview-grid">
        <img
          v-for="(src, i) in previews"
          :key="i"
          :src="src"
          :alt="`card ${i + 1}`"
          @click="previewImage(i)"
        />
      </div>
      <pre v-else-if="job.logs" class="logs">{{ job.logs }}</pre>
      <p v-else class="faint small" style="margin-top: 10px">（等待生成…）</p>
    </section>

    <section class="card">
      <div class="card-title">
        <span>生成历史</span>
        <button type="button" class="link-btn" :disabled="loading" @click="loadJobs">刷新</button>
      </div>
      <div v-if="!jobs.length" class="empty-box">暂无生成记录</div>
      <div v-else class="hist-list">
        <div v-for="row in jobs" :key="row.id" class="hist-item" @click="view(row)">
          <div class="hist-main">
            <div class="hist-title">
              <span class="job-id">#{{ row.id }}</span>
              <span class="hist-product">{{ row.product }}</span>
              <StatusBadge :status="row.status" :label="row.status_label" />
            </div>
            <div class="faint small hist-plan">{{ row.plan_name || '—' }}</div>
            <div class="faint small">{{ row.created_at }}</div>
          </div>
          <div class="hist-actions">
            <van-button v-if="row.zip_ready" size="mini" plain type="primary" @click.stop="download(row)">下载</van-button>
            <van-icon name="arrow" class="faint" />
          </div>
        </div>
      </div>
    </section>

    <van-popup v-model:show="catalogVisible" position="bottom" round class="catalog-popup">
      <div class="popup-head">
        <h3>支持的产品</h3>
        <span class="faint small">{{ filteredCatalog.length }} 款</span>
      </div>
      <van-search v-model="filterKw" placeholder="搜索产品名 / 代号 / 类别" />
      <div class="catalog-list">
        <div v-for="p in filteredCatalog" :key="p.id" class="catalog-item">
          <div class="cat-name">{{ p.name }}</div>
          <div class="faint small">{{ p.company }} · {{ p.id }} · {{ p.category || '—' }}</div>
        </div>
        <div v-if="!filteredCatalog.length" class="empty-box">没有匹配的产品</div>
      </div>
    </van-popup>

    <van-popup v-model:show="productPicker" position="bottom" round>
      <van-picker
        :columns="productColumns"
        :columns-field-names="{ text: 'label', value: 'id' }"
        @cancel="productPicker = false"
        @confirm="onProductConfirm"
      />
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { showImagePreview, showToast } from 'vant';
import AppNav from '@/components/AppNav.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import {
  createCardJob,
  detectCard,
  downloadCardsZip,
  fetchCardBlobUrl,
  getCardJob,
  getCardProducts,
  listCardJobs,
} from '@/api/cards';

const THEMES = [
  { label: 'YF 奶油蓝', value: 'yf-cream' },
  { label: 'AIA 红', value: 'aia-red' },
];

const fileInput = ref<HTMLInputElement | null>(null);
const fileObj = ref<File | null>(null);
const fileName = ref('');
const detecting = ref(false);
const detected = ref<any>(null);
const chosenProduct = ref('');
const theme = ref('yf-cream');
const openCards = ref<number[]>([]);
const edits = reactive<Record<string, string>>({});

const catalog = ref<any[]>([]);
const productOptions = ref<any[]>([]);
const catalogVisible = ref(false);
const productPicker = ref(false);
const filterKw = ref('');

const submitting = ref(false);
const downloading = ref(false);
const loading = ref(false);
const job = ref<any>(null);
const jobs = ref<any[]>([]);
const previews = ref<string[]>([]);
let timer: any = null;

const companies = computed(() => Array.from(new Set(catalog.value.map((p) => p.company).filter(Boolean))));

const filteredCatalog = computed(() => {
  const kw = filterKw.value.trim().toLowerCase();
  if (!kw) return catalog.value;
  return catalog.value.filter((p) =>
    [p.name, p.id, p.category, p.positioning].filter(Boolean).join(' ').toLowerCase().includes(kw)
  );
});

const productColumns = computed(() =>
  productOptions.value.map((p) => ({
    label: `${p.company ? p.company + ' · ' : ''}${p.name}（${p.id}）`,
    id: p.id,
  }))
);

const chosenProductName = computed(() => productOptions.value.find((p) => p.id === chosenProduct.value)?.name || '');

const editKey = (idx: number, key: string) => `${idx}.${key}`;
const editValue = (idx: number, key: string, orig: any) => edits[editKey(idx, key)] ?? orig;
function onEdit(idx: number, key: string, value: string, orig: any) {
  if (value === orig) delete edits[editKey(idx, key)];
  else edits[editKey(idx, key)] = value;
}

async function loadCatalog() {
  try {
    const res = await getCardProducts(false);
    catalog.value = res?.data || [];
  } catch {
    /* ignore */
  }
}
async function loadProducts() {
  try {
    const res = await getCardProducts(true);
    productOptions.value = res?.data || [];
  } catch {
    /* ignore */
  }
}

function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showToast('请选择 PDF 文件');
    return;
  }
  fileObj.value = file;
  fileName.value = file.name;
  chosenProduct.value = '';
  runDetect();
}

async function runDetect(productOverride?: string) {
  if (!fileObj.value) return;
  detecting.value = true;
  detected.value = null;
  Object.keys(edits).forEach((k) => delete edits[k]);
  try {
    const res = await detectCard(fileObj.value, productOverride || '');
    detected.value = res?.data || null;
    chosenProduct.value = productOverride || res?.data?.product || '';
    openCards.value = [0];
    showToast({ type: 'success', message: `识别成功：${res?.data?.product || ''}（${res?.data?.card_count || 0} 张）` });
  } catch (e: any) {
    showToast(e?.message || '识别失败');
  } finally {
    detecting.value = false;
  }
}

function onProductConfirm({ selectedOptions }: any) {
  const id = selectedOptions?.[0]?.id;
  productPicker.value = false;
  if (!id || id === chosenProduct.value) return;
  chosenProduct.value = id;
  runDetect(id);
}

function buildOverrides() {
  const out: Record<number, Record<string, string>> = {};
  for (const k of Object.keys(edits)) {
    const [idxStr, ...rest] = k.split('.');
    const idx = Number(idxStr);
    const field = rest.join('.');
    if (!out[idx]) out[idx] = {};
    out[idx][field] = edits[k];
  }
  return out;
}

async function generate() {
  if (!fileObj.value || !detected.value || submitting.value) return;
  const fd = new FormData();
  fd.append('file', fileObj.value);
  fd.append('product', chosenProduct.value || detected.value.product);
  fd.append('plan_name', detected.value.plan_name || '');
  fd.append('theme', theme.value);
  fd.append('overrides', JSON.stringify(buildOverrides()));
  submitting.value = true;
  try {
    const res = await createCardJob(fd);
    job.value = res?.data || null;
    clearPreviews();
    showToast({ type: 'success', message: '已提交，正在生成' });
    poll();
    loadJobs();
  } catch (e: any) {
    showToast(e?.message || '提交失败');
  } finally {
    submitting.value = false;
  }
}

function clearPreviews() {
  previews.value.forEach((u) => URL.revokeObjectURL(u));
  previews.value = [];
}

async function loadPreviews(j: any) {
  clearPreviews();
  const n = (j?.card_files || []).length;
  for (let i = 0; i < n; i++) {
    try {
      previews.value.push(await fetchCardBlobUrl(j.id, i));
    } catch {
      /* ignore */
    }
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
      const res = await getCardJob(job.value.id);
      job.value = res?.data || job.value;
      if (job.value.status === 'succeeded') {
        clearInterval(timer);
        timer = null;
        loadPreviews(job.value);
        loadJobs();
      } else if (job.value.status === 'failed') {
        clearInterval(timer);
        timer = null;
        loadJobs();
      }
    } catch {
      /* keep polling */
    }
  }, 3000);
}

async function loadJobs() {
  loading.value = true;
  try {
    const res = await listCardJobs();
    jobs.value = res?.data || [];
  } catch {
    /* ignore */
  } finally {
    loading.value = false;
  }
}

async function view(row: any) {
  try {
    const res = await getCardJob(row.id);
    job.value = res?.data || null;
    if (job.value?.status === 'succeeded') loadPreviews(job.value);
    else poll();
  } catch (e: any) {
    showToast(e?.message || '加载失败');
  }
}

async function download(row?: any) {
  const j = row || job.value;
  if (!j) return;
  downloading.value = true;
  try {
    await downloadCardsZip(j.id, `cards_${j.id}_${j.product}.zip`);
  } catch (e: any) {
    showToast(e?.message || '下载失败');
  } finally {
    downloading.value = false;
  }
}

function previewImage(index: number) {
  showImagePreview({ images: previews.value, startPosition: index, closeable: true });
}

onMounted(async () => {
  loadProducts();
  await loadCatalog();
  loadJobs();
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  clearPreviews();
});
</script>

<style scoped>
.cards {
  padding-bottom: calc(30px + var(--app-safe-bottom));
}

.upload-card {
  margin-top: 12px;
}
.upload-box {
  width: 100%;
  border: 1.5px dashed var(--app-border-strong);
  border-radius: 16px;
  background: var(--app-bg-soft);
  color: var(--app-muted);
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.upload-title {
  font-size: 14px;
  color: var(--app-text);
  font-weight: 600;
  word-break: break-all;
}
.upload-sub {
  font-size: 11.5px;
  color: var(--app-faint);
}
.support-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
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

.detected-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.plan-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-strong);
  margin-bottom: 3px;
}
.theme-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.theme-row .label {
  font-size: 12px;
  color: var(--app-muted);
}

.cards-collapse {
  margin-bottom: 14px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--app-border);
}
.cards-collapse :deep(.van-collapse-item__title),
.cards-collapse :deep(.van-collapse-item__content) {
  background: var(--app-card-2);
}
.collapse-title {
  font-size: 13px;
  color: var(--app-text);
  font-weight: 500;
}
.field-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.edit-field label {
  display: block;
  font-size: 11px;
  color: var(--app-faint);
  margin-bottom: 4px;
  word-break: break-all;
}
.edit-field textarea {
  width: 100%;
  resize: vertical;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-soft);
  color: var(--app-text);
  font: inherit;
  font-size: 12.5px;
  line-height: 1.6;
  padding: 8px 10px;
  outline: none;
}
.edit-field textarea:focus {
  border-color: rgba(74, 158, 255, 0.5);
}
.gen-btn {
  height: 48px;
}

.job-id {
  font-size: 12px;
  color: var(--app-faint);
}
.prog-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.prog-wrap :deep(.van-progress) {
  flex: 1;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.preview-grid img {
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  display: block;
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
  cursor: pointer;
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
  gap: 8px;
  flex-wrap: wrap;
}
.hist-product {
  font-size: 12.5px;
  color: var(--app-text);
}
.hist-plan {
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.hist-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.catalog-popup {
  max-height: 78vh;
  display: flex;
  flex-direction: column;
  padding: 16px 14px calc(20px + var(--app-safe-bottom));
}
.popup-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.popup-head h3 {
  margin: 0;
  font-size: 17px;
  color: var(--app-text-strong);
}
.catalog-list {
  overflow-y: auto;
  flex: 1;
}
.catalog-item {
  padding: 10px 2px;
  border-bottom: 1px solid var(--app-border);
}
.cat-name {
  font-size: 13px;
  color: var(--app-text);
  font-weight: 500;
}
</style>
