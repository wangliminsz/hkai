<template>
  <div class="page--with-nav docai">
    <AppNav title="AI 文件分析" back-to="/home" />

    <div v-if="checked && !allowed" class="card" style="margin-top: 12px; text-align: center; padding: 30px 18px">
      <van-icon name="warning-o" size="32" color="#f0a83b" />
      <h3 style="margin: 12px 0 6px; color: var(--app-text-strong)">暂无 AI 文件分析权限</h3>
      <p class="muted small" style="margin: 0">请联系超级管理员为你开通此功能。</p>
    </div>

    <template v-else>
      <div class="hint" style="margin-top: 12px">
        上传 <b>PDF</b> 或 <b>图片</b>（≤30MB），系统会用 AI 分析内容，并把 HTML 报告发送到填写的邮箱。通常需要 1–3 分钟。
      </div>

      <section class="card">
        <input ref="fileInput" type="file" accept=".pdf,image/*" hidden @change="onFile" />
        <button type="button" class="upload-box" @click="fileInput?.click()">
          <van-icon :name="file ? 'records' : 'plus'" size="26" />
          <span class="upload-title">{{ file ? file.name : '选择 PDF / 图片' }}</span>
          <span class="upload-sub">{{ file ? '点击重新选择' : '支持 PDF、PNG、JPEG、GIF、WebP、BMP' }}</span>
        </button>

        <div class="form-field">
          <label>收件邮箱</label>
          <van-field v-model="email" placeholder="name@example.com（多个用逗号分隔）" type="text" class="soft-field" />
        </div>

        <van-collapse v-model="openPrompt" class="prompt-collapse">
          <van-collapse-item title="分析 Prompt（可自定义）" name="prompt">
            <textarea v-model="prompt" rows="7" spellcheck="false" placeholder="留空则使用后台默认 Prompt"></textarea>
            <div class="prompt-actions">
              <button type="button" class="link-btn" :disabled="!defaultPrompt" @click="restorePrompt">恢复默认</button>
              <span class="faint small">留空时使用后台默认 Prompt</span>
            </div>
          </van-collapse-item>
        </van-collapse>

        <van-button
          block
          round
          type="primary"
          size="large"
          class="submit-btn"
          :loading="submitting"
          :disabled="!file || !email"
          @click="submit"
        >
          开始分析
        </van-button>
      </section>

      <section v-if="current" class="card">
        <div class="row-between">
          <div class="row" style="gap: 8px">
            <span class="job-id">#{{ current.id }}</span>
            <StatusBadge :status="current.status" />
          </div>
          <span class="faint small">{{ current.filename }}</span>
        </div>
        <div class="step">
          <span v-if="current.status === 'queued' || current.status === 'running'" class="spinner"></span>
          <span>{{
            current.status === 'queued'
              ? '排队中…'
              : current.status === 'running'
              ? current.step || '分析中…'
              : current.status === 'succeeded'
              ? '已完成，报告已发送到邮箱'
              : '失败'
          }}</span>
        </div>
        <p v-if="current.error" class="err-text" style="margin-top: 8px">{{ current.error }}</p>
        <div v-if="current.status === 'succeeded'" class="step-actions">
          <van-button size="small" type="primary" plain @click="openReport(current)">查看报告</van-button>
          <van-button size="small" plain @click="downloadPdf(current)">下载 PDF</van-button>
          <span class="faint small">已发送至 {{ current.email }}</span>
        </div>
      </section>

      <section class="card">
        <div class="card-title">
          <span>分析历史</span>
          <button type="button" class="link-btn" :disabled="loading" @click="loadHistory">刷新</button>
        </div>
        <div v-if="!history.length" class="empty-box">暂无分析记录</div>
        <div v-else class="hist-list">
          <div v-for="row in history" :key="row.id" class="hist-item">
            <div class="hist-main">
              <div class="hist-title">
                <span class="job-id">#{{ row.id }}</span>
                <span class="kind">{{ row.kind === 'pdf' ? 'PDF' : '图片' }}</span>
                <StatusBadge :status="row.status" />
              </div>
              <div class="hist-file">{{ row.filename }}</div>
              <div class="faint small">{{ row.created_at }} · {{ row.email }}</div>
            </div>
            <div class="hist-actions">
              <van-button
                size="mini"
                plain
                type="primary"
                :disabled="row.status !== 'succeeded'"
                @click="openReport(row)"
              >
                报告
              </van-button>
              <van-button
                size="mini"
                plain
                :disabled="row.status !== 'succeeded'"
                @click="downloadPdf(row)"
              >
                PDF
              </van-button>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { showToast } from 'vant';
import AppNav from '@/components/AppNav.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { useAuthStore } from '@/stores/auth';
import {
  analyzeDoc,
  getDocAiAccess,
  getDocAiJob,
  getDocAiPrompts,
  listDocAiJobs,
  reportPdfUrl,
  reportUrl,
} from '@/api/docai';

const auth = useAuthStore();

const checked = ref(false);
const allowed = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
const email = ref('');
const prompt = ref('');
const defaultPrompt = ref('');
const openPrompt = ref<string[]>([]);
const submitting = ref(false);
const loading = ref(false);
const history = ref<any[]>([]);
const current = ref<any>(null);
let timer: any = null;

function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const f = input.files?.[0];
  input.value = '';
  if (!f) return;
  file.value = f;
}

async function loadHistory() {
  loading.value = true;
  try {
    const res = await listDocAiJobs();
    history.value = res?.data || [];
  } catch (e: any) {
    showToast(e?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

async function loadPrompts() {
  try {
    const res = await getDocAiPrompts();
    defaultPrompt.value = res?.data?.prompt || '';
    prompt.value = defaultPrompt.value;
  } catch {
    defaultPrompt.value = '';
  }
}

function restorePrompt() {
  if (!defaultPrompt.value) return;
  prompt.value = defaultPrompt.value;
  showToast('已恢复默认 Prompt');
}

function poll(id: number) {
  if (timer) clearInterval(timer);
  timer = setInterval(async () => {
    try {
      const res = await getDocAiJob(id);
      current.value = res?.data || current.value;
      if (current.value?.status === 'succeeded' || current.value?.status === 'failed') {
        clearInterval(timer);
        timer = null;
        submitting.value = false;
        loadHistory();
        if (current.value.status === 'succeeded') showToast({ type: 'success', message: '分析完成，报告已发送到邮箱' });
        else showToast('分析失败，请查看错误信息');
      }
    } catch {
      /* keep polling */
    }
  }, 2500);
}

async function submit() {
  if (!file.value) return showToast('请选择文件');
  if (!email.value.trim()) return showToast('请填写收件邮箱');
  submitting.value = true;
  try {
    const res = await analyzeDoc(file.value, email.value.trim(), prompt.value);
    const data = res?.data || {};
    current.value = {
      id: data.id,
      filename: file.value.name,
      status: 'queued',
      step: 'queued',
      email: email.value.trim(),
    };
    showToast({ type: 'success', message: '已提交，正在分析…' });
    poll(data.id);
    loadHistory();
  } catch (e: any) {
    submitting.value = false;
    showToast(e?.message || '提交失败');
  }
}

function openReport(row: any) {
  window.open(reportUrl(row.id), '_blank');
}

function downloadPdf(row: any) {
  window.open(reportPdfUrl(row.id), '_blank');
}

onMounted(async () => {
  email.value = auth.user?.email || '';
  try {
    const res = await getDocAiAccess();
    allowed.value = !!res?.data?.allowed;
  } catch {
    allowed.value = false;
  } finally {
    checked.value = true;
  }
  if (allowed.value) {
    loadPrompts();
    loadHistory();
  }
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.docai {
  padding-bottom: calc(30px + var(--app-safe-bottom));
}
.upload-box {
  width: 100%;
  border: 1.5px dashed var(--app-border-strong);
  border-radius: 16px;
  background: var(--app-bg-soft);
  color: var(--app-muted);
  padding: 22px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  margin-bottom: 16px;
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
  text-align: center;
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
.prompt-collapse {
  margin-bottom: 14px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
}
.prompt-collapse :deep(.van-collapse-item__title),
.prompt-collapse :deep(.van-collapse-item__content) {
  background: var(--app-card-2);
  color: var(--app-text);
}
.prompt-collapse textarea {
  width: 100%;
  resize: vertical;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-soft);
  color: var(--app-text);
  font: inherit;
  font-size: 12.5px;
  line-height: 1.6;
  padding: 9px 10px;
  outline: none;
}
.prompt-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
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
.submit-btn {
  height: 48px;
}
.job-id {
  font-size: 12px;
  color: var(--app-faint);
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 13px;
  color: var(--app-text);
}
.step-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.spinner {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid rgba(120, 170, 255, 0.25);
  border-top-color: #6fb4ff;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
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
.hist-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}
.hist-title {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.kind {
  font-size: 10.5px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--app-border-strong);
  color: var(--app-muted);
}
.hist-file {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
</style>
