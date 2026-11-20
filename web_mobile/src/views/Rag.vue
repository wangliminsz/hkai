<template>
  <div class="rag-page">
    <header class="rag-head">
      <div class="head-top">
        <div class="head-title">
          <span class="head-icon"><van-icon name="chat-o" /></span>
          <div>
            <h1>AI 知识库</h1>
            <p>产品问答 · 带页码引用 · 术语大白话</p>
          </div>
        </div>
        <div class="head-actions">
          <button type="button" class="ghost-btn" @click="termPopup = true">术语</button>
          <button type="button" class="ghost-btn" :disabled="!messages.length" @click="clearChat">清空</button>
        </div>
      </div>

      <van-dropdown-menu class="filters" active-color="#6fb4ff">
        <van-dropdown-item v-model="companyId" :options="companyOptions" @change="onCompanyChange" />
        <van-dropdown-item v-model="productId" :options="productOptions" @change="resetMessages" />
        <van-dropdown-item
          v-if="compareOptions.length"
          v-model="compareId"
          :options="compareOptions"
          @change="resetMessages"
        />
      </van-dropdown-menu>

      <div v-if="selected" class="selected-line">
        <span class="dot" :class="{ ok: selected.indexed }"></span>
        <span class="sel-name">{{ selected.name }}</span>
        <span class="faint small">{{ selected.insurer || '' }} · {{ selected.indexed ? '已建索引' : '未建索引' }}</span>
      </div>

      <div v-if="selected?.documents?.length" class="docs">
        <span class="docs-label">产品文件</span>
        <a
          v-for="d in selected.documents"
          :key="d.doc_type + d.file"
          class="doc-chip"
          :href="docHref(d)"
          target="_blank"
          rel="noopener"
        >
          <van-icon name="down" />
          {{ DOC_LABEL[d.doc_type] || d.doc_type }}
        </a>
      </div>
    </header>

    <div class="progress" :class="{ active: busy }"><span></span></div>

    <main ref="scroller" class="chat">
      <div v-if="!messages.length" class="welcome">
        <div class="welcome-icon"><van-icon name="chat-o" /></div>
        <h2>問一問產品資料</h2>
        <p v-if="selected">{{ selected.summary }}</p>
        <p v-else>选择产品；或直接提问并注明产品名称，系统会自动匹配。</p>
        <div class="samples">
          <button v-for="s in sampleList" :key="s" type="button" @click="useSample(s)">{{ s }}</button>
        </div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div v-if="m.role === 'assistant'" class="bot-avatar"><van-icon name="chat-o" /></div>
        <div class="bubble">
          <div v-if="m.content" class="text-wrap">
            <div v-if="splitAnswer(m.content).header" class="source-head">{{ splitAnswer(m.content).header }}</div>
            <div class="text markdown" v-html="renderMarkdown(splitAnswer(m.content).body)"></div>
            <span v-if="m.streaming" class="caret"></span>
          </div>
          <div v-else-if="m.streaming" class="typing">
            <span class="spinner"></span>
            <span>{{ phase || '检索中…' }}</span>
            <span v-if="elapsed" class="faint small">{{ elapsed }}s</span>
          </div>

          <div v-if="m.needsProduct" class="need-pick">
            <button
              v-for="c in m.candidates"
              :key="c.product_id"
              type="button"
              class="cand"
              @click="pickCandidate(c, m)"
            >
              {{ c.name }}<span v-if="!c.indexed" class="cand-sub">未建索引</span>
            </button>
          </div>

          <div v-if="m.role === 'assistant' && m.content && !m.streaming && !m.needsProduct" class="msg-tools">
            <button type="button" @click="copyText(m.content)">
              <van-icon name="records" /> 复制
            </button>
            <button type="button" @click="togglePlain(m)">
              <van-icon name="bulb-o" /> {{ m.plain || m.plainPending ? '收起大白话' : '大白话' }}
            </button>
            <span v-if="copied" class="faint small">已复制</span>
          </div>

          <div v-if="m.plainPending" class="plain"><span class="spinner"></span> 正在翻成大白话…</div>
          <div v-else-if="m.plainErr" class="plain err-text">{{ m.plainErr }}</div>
          <div v-else-if="m.plain" class="plain">{{ m.plain }}</div>

          <div v-if="m.citations?.length" class="cites">
            <span v-for="c in m.citations" :key="c.index" class="cite">
              [{{ c.index }}] {{ DOC_LABEL[c.doc_type] || c.doc_type || '文件' }} · p.{{ c.page }}
            </span>
          </div>
        </div>
      </div>
    </main>

    <p v-if="errorMsg" class="err-bar">{{ errorMsg }}</p>

    <footer class="composer">
      <div class="composer-box">
        <textarea
          v-model="input"
          rows="1"
          placeholder="输入问题…"
          :disabled="busy"
          @input="autoGrow"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <button type="button" class="send-btn" :disabled="busy || !input.trim()" @click="send">
          <van-icon :name="busy ? 'clock-o' : 'arrow-up'" />
        </button>
      </div>
      <p class="composer-tip">回答基于已上传的产品文件，请以正式条款为准。</p>
    </footer>

    <van-popup v-model:show="termPopup" position="bottom" round class="term-popup">
      <div class="term-head">
        <h3>術語大白話</h3>
        <p>看不懂的术语或整段话，用人话讲给你听。</p>
      </div>
      <van-field
        v-model="termInput"
        type="textarea"
        rows="3"
        autosize
        placeholder="例如：不可异议条款、终期红利、现金价值…"
        class="term-field"
      />
      <van-button
        block
        round
        type="primary"
        :loading="termBusy"
        :disabled="!termInput.trim()"
        @click="runExplain"
      >
        解释一下
      </van-button>
      <div v-if="termErr" class="term-out err-text">{{ termErr }}</div>
      <div v-else-if="termResult" class="term-out">{{ termResult }}</div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import { documentHref, explainTerm, getRagProducts, sendChatStream } from '@/api/rag';
import { renderMarkdown } from '@/utils/markdown';

const DOC_LABEL: Record<string, string> = { contract: '合约条款', brochure: '产品介绍' };

const products = ref<any[]>([]);
const companyId = ref('');
const productId = ref('');
const compareId = ref('');
const messages = ref<any[]>([]);
const input = ref('');
const busy = ref(false);
const errorMsg = ref('');
const phase = ref('');
const elapsed = ref(0);
const copied = ref(false);
const scroller = ref<HTMLElement | null>(null);

const termPopup = ref(false);
const termInput = ref('');
const termResult = ref('');
const termErr = ref('');
const termBusy = ref(false);

let timer: any = null;
let copyTimer: any = null;
let pendingSend = false;

const companies = computed(() => {
  const set = new Set<string>();
  products.value.forEach((p) => p.insurer && set.add(p.insurer));
  return Array.from(set);
});

const companyOptions = computed(() => [
  { text: '全部保险公司', value: '' },
  ...companies.value.map((c) => ({ text: c, value: c })),
]);

const filteredProducts = computed(() =>
  companyId.value ? products.value.filter((p) => p.insurer === companyId.value) : products.value
);

const productLabel = (p: any) => `${p.name}${p.indexed ? '' : '（未建索引）'}`;

const productOptions = computed(() => [
  { text: '自动匹配产品', value: '' },
  ...filteredProducts.value.map((p) => ({ text: productLabel(p), value: p.product_id })),
]);

const selected = computed(() => products.value.find((p) => p.product_id === productId.value) || null);

const comparable = (a: any, b: any) => {
  if (!a || !b) return false;
  if (a.compare_group && a.compare_group === b.compare_group) return true;
  return !!(a.category && a.category === b.category);
};

const compareOptions = computed(() => {
  if (!selected.value) return [];
  const list = products.value.filter(
    (p) => p.product_id !== selected.value!.product_id && comparable(selected.value, p)
  );
  if (!list.length) return [];
  return [{ text: '不对比', value: '' }, ...list.map((p) => ({ text: productLabel(p), value: p.product_id }))];
});

const DEFAULT_SAMPLES = ['尚裕终身寿险保什么？', '危疾加护保(优越版) vs (标准版)有何差异？', '尚裕终身寿险保费未缴的宽限期是多少天？'];
const sampleList = computed(() => (selected.value?.samples?.length ? selected.value.samples : DEFAULT_SAMPLES));

function docHref(d: any) {
  return documentHref(d);
}

function onCompanyChange() {
  if (productId.value) {
    const p = products.value.find((x) => x.product_id === productId.value);
    if (p && companyId.value && p.insurer !== companyId.value) productId.value = '';
  }
  resetMessages();
}

function resetMessages() {
  messages.value = [];
  compareId.value = '';
  errorMsg.value = '';
}

function clearChat() {
  messages.value = [];
  errorMsg.value = '';
}

function splitAnswer(content: string) {
  const text = content || '';
  const idx = text.indexOf('\n');
  const first = idx === -1 ? text : text.slice(0, idx);
  if (idx !== -1 && first.startsWith('【本次依據】')) {
    return { header: first, body: text.slice(idx + 1).replace(/^\n+/, '') };
  }
  return { header: '', body: text };
}

function pickCandidate(c: any, m: any) {
  const question = m?.question || input.value;
  productId.value = c.product_id;
  companyId.value = c.insurer || '';
  compareId.value = '';
  messages.value = [];
  errorMsg.value = '';
  input.value = question;
  if (busy.value) pendingSend = true;
  else send();
}

function useSample(s: string) {
  input.value = s;
  send();
}

function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

function scrollToBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
}

function startTimer() {
  elapsed.value = 0;
  phase.value = '已接收问题，正在排队…';
  timer = setInterval(() => (elapsed.value += 1), 1000);
}
function stopTimer() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

async function copyText(text: string) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  copied.value = true;
  if (copyTimer) clearTimeout(copyTimer);
  copyTimer = setTimeout(() => (copied.value = false), 1500);
}

async function togglePlain(msg: any) {
  if (msg.plainPending) return;
  if (msg.plain) {
    msg.plain = '';
    return;
  }
  msg.plainPending = true;
  msg.plainErr = '';
  try {
    const res = await explainTerm({ term: splitAnswer(msg.content).body || msg.content });
    msg.plain = res?.data?.explanation || '';
  } catch (e: any) {
    msg.plainErr = e?.message || '生成失败';
  } finally {
    msg.plainPending = false;
    scrollToBottom();
  }
}

async function runExplain() {
  const text = termInput.value.trim();
  if (!text || termBusy.value) return;
  termBusy.value = true;
  termErr.value = '';
  termResult.value = '';
  try {
    const res = await explainTerm({ term: text });
    termResult.value = res?.data?.explanation || '';
  } catch (e: any) {
    termErr.value = e?.message || '生成失败';
  } finally {
    termBusy.value = false;
  }
}

async function send() {
  const question = input.value.trim();
  if (!question || busy.value) return;

  const history = messages.value.map((m) => ({ role: m.role, content: m.content }));
  messages.value.push({ role: 'user', content: question });
  input.value = '';
  busy.value = true;
  errorMsg.value = '';
  startTimer();
  scrollToBottom();

  const reply: any = { role: 'assistant', content: '', citations: [], streaming: true, question };
  messages.value.push(reply);

  try {
    await sendChatStream({
      question,
      productId: productId.value,
      productIds: [productId.value, compareId.value].filter(Boolean),
      history,
      onStart: () => (phase.value = '已连上服务器，等待模型回应…'),
      onMeta: (m: any) => {
        if (!productId.value && m?.product_id) {
          productId.value = m.product_id;
          const p = products.value.find((x) => x.product_id === m.product_id);
          if (p?.insurer) companyId.value = p.insurer;
        }
        if (!compareId.value && Array.isArray(m?.product_ids) && m.product_ids.length > 1) {
          compareId.value = m.product_ids[1];
        }
        phase.value = '正在检索产品文件…';
      },
      onDelta: (text: string) => {
        if (!reply.content) phase.value = '正在整理答案…';
        reply.content += text;
        scrollToBottom();
      },
      onDone: (d: any) => {
        reply.content = d?.answer || reply.content;
        reply.citations = d?.citations || [];
        reply.streaming = false;
        stopTimer();
        scrollToBottom();
      },
      onNeedsProduct: (d: any) => {
        reply.content = d?.message || '未找到对应产品，请先选择产品后再提问。';
        reply.needsProduct = true;
        reply.candidates = d?.candidates || [];
        reply.streaming = false;
        phase.value = '';
        stopTimer();
        scrollToBottom();
      },
    });
  } catch (e: any) {
    errorMsg.value = e?.message || '请求失败';
    reply.content = reply.content || `（出错：${errorMsg.value}）`;
    reply.streaming = false;
  } finally {
    stopTimer();
    reply.streaming = false;
    busy.value = false;
    scrollToBottom();
    if (pendingSend) {
      pendingSend = false;
      nextTick(() => send());
    }
  }
}

onMounted(async () => {
  try {
    const res = await getRagProducts();
    products.value = res?.data?.products || res?.products || [];
  } catch (e: any) {
    errorMsg.value = e?.message || '加载产品失败';
  }
});

onUnmounted(() => {
  stopTimer();
  if (copyTimer) clearTimeout(copyTimer);
});

</script>

<style scoped>
.rag-page {
  height: calc(100dvh - var(--app-tabbar-h) - var(--app-safe-bottom));
  display: flex;
  flex-direction: column;
  background: var(--app-bg);
  padding-top: env(safe-area-inset-top);
  overflow: hidden;
}

.rag-head {
  flex-shrink: 0;
  padding: 12px 14px 8px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-bg);
}
.head-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.head-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.head-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7fbaff;
  background: rgba(74, 158, 255, 0.14);
  border: 1px solid rgba(74, 158, 255, 0.25);
  font-size: 20px;
}
.head-title h1 {
  margin: 0;
  font-size: 16px;
  color: var(--app-text-strong);
}
.head-title p {
  margin: 2px 0 0;
  font-size: 10.5px;
  color: var(--app-faint);
}
.head-actions {
  display: flex;
  gap: 6px;
}
.ghost-btn {
  padding: 6px 10px;
  border-radius: 10px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-card-2);
  color: var(--app-muted);
  font-size: 12px;
  cursor: pointer;
}
.ghost-btn:disabled {
  opacity: 0.4;
}

.filters {
  margin: 8px -14px 0;
  --van-dropdown-menu-height: 40px;
}
.filters :deep(.van-dropdown-menu__bar) {
  background: transparent;
  box-shadow: none;
  border-bottom: 1px solid var(--app-border);
}
.filters :deep(.van-dropdown-menu__title) {
  font-size: 12.5px;
}

.selected-line {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 2px 0;
  font-size: 12px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--app-warning);
}
.dot.ok {
  background: var(--app-success);
}
.sel-name {
  color: var(--app-text);
  font-weight: 500;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.docs {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 2px;
  overflow-x: auto;
}
.docs-label {
  font-size: 11px;
  color: var(--app-faint);
  flex-shrink: 0;
}
.doc-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(74, 158, 255, 0.3);
  background: rgba(74, 158, 255, 0.1);
  color: #8fc4ff;
  font-size: 11px;
}

.progress {
  height: 2px;
  flex-shrink: 0;
  overflow: hidden;
  background: transparent;
}
.progress span {
  display: block;
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, transparent, #4a9eff, transparent);
}
.progress.active span {
  width: 100%;
  animation: slide 1.2s linear infinite;
}
@keyframes slide {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 14px 12px 18px;
  -webkit-overflow-scrolling: touch;
}

.welcome {
  text-align: center;
  padding: 34px 18px;
  color: var(--app-muted);
}
.welcome-icon {
  width: 62px;
  height: 62px;
  margin: 0 auto 16px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: #7fbaff;
  background: rgba(74, 158, 255, 0.12);
  border: 1px solid rgba(74, 158, 255, 0.22);
}
.welcome h2 {
  margin: 0 0 8px;
  font-size: 18px;
  color: var(--app-text-strong);
}
.welcome p {
  margin: 0 auto 18px;
  font-size: 12.5px;
  line-height: 1.7;
  max-width: 300px;
}
.samples {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.samples button {
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--app-border);
  background: var(--app-card);
  color: var(--app-text);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}

.msg {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  align-items: flex-start;
}
.msg.user {
  justify-content: flex-end;
}
.bot-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #7fbaff;
  background: rgba(74, 158, 255, 0.14);
  border: 1px solid rgba(74, 158, 255, 0.22);
}
.bubble {
  max-width: 84%;
  padding: 11px 13px;
  border-radius: 16px;
  font-size: 13.5px;
  line-height: 1.7;
  word-break: break-word;
}
.msg.assistant .bubble {
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-top-left-radius: 5px;
  color: var(--app-text);
  max-width: calc(100% - 40px);
  flex: 1;
}
.msg.user .bubble {
  background: linear-gradient(135deg, #3f86e0, #2c66b8);
  color: #f4f9ff;
  border-top-right-radius: 5px;
  border: 1px solid rgba(120, 180, 255, 0.3);
}
.text {
  white-space: pre-wrap;
}
.text-wrap {
  white-space: normal;
}
.source-head {
  display: inline-block;
  margin-bottom: 8px;
  padding: 5px 9px;
  border-radius: 8px;
  border: 1px solid rgba(74, 158, 255, 0.3);
  border-left: 3px solid #6fb4ff;
  background: rgba(74, 158, 255, 0.1);
  color: #a9d0ff;
  font-size: 11.5px;
  line-height: 1.5;
  word-break: break-word;
}
.need-pick {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 9px;
  padding-top: 9px;
  border-top: 1px dashed var(--app-border);
}
.cand {
  padding: 6px 10px;
  border-radius: 9px;
  border: 1px solid rgba(76, 175, 130, 0.35);
  background: rgba(76, 175, 130, 0.1);
  color: #7dd6a5;
  font-size: 11.5px;
  line-height: 1.4;
  text-align: left;
}
.cand-sub {
  margin-left: 5px;
  color: var(--app-faint);
  font-size: 10.5px;
}
.text.markdown {
  white-space: normal;
}
.markdown p {
  margin: 0 0 8px;
}
.markdown p:last-child,
.markdown ul:last-child,
.markdown ol:last-child {
  margin-bottom: 0;
}
.markdown h3,
.markdown h4,
.markdown h5,
.markdown h6 {
  margin: 12px 0 6px;
  color: #f2f6fc;
  font-weight: 600;
  line-height: 1.4;
}
.markdown h3 { font-size: 15px; }
.markdown h4 { font-size: 14px; }
.markdown h5,
.markdown h6 { font-size: 13.5px; }
.markdown ul,
.markdown ol {
  margin: 6px 0 8px;
  padding-left: 20px;
}
.markdown li {
  margin: 3px 0;
}
.markdown strong {
  color: #ffffff;
}
.markdown code {
  background: rgba(120, 170, 255, 0.16);
  color: #a9d0ff;
  padding: 1px 5px;
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.caret {
  display: inline-block;
  width: 6px;
  height: 14px;
  margin-left: 2px;
  vertical-align: -2px;
  background: #6fb4ff;
  animation: blink 1s steps(1) infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.typing {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--app-muted);
  font-size: 12.5px;
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

.msg-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--app-border);
}
.msg-tools button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--app-faint);
  font-size: 11.5px;
  padding: 0;
  cursor: pointer;
}

.plain {
  margin-top: 9px;
  padding: 10px 11px;
  border-radius: 10px;
  background: rgba(240, 168, 59, 0.1);
  border: 1px solid rgba(240, 168, 59, 0.22);
  color: #e9c98f;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.cites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 9px;
}
.cite {
  font-size: 10.5px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--app-card-2);
  color: var(--app-muted);
  border: 1px solid var(--app-border);
}

.err-bar {
  flex-shrink: 0;
  margin: 0;
  padding: 8px 14px;
  background: rgba(255, 93, 93, 0.1);
  color: #ff9090;
  font-size: 12px;
  border-top: 1px solid rgba(255, 93, 93, 0.18);
}

.composer {
  flex-shrink: 0;
  padding: 10px 12px 8px;
  border-top: 1px solid var(--app-border);
  background: rgba(20, 20, 24, 0.96);
  backdrop-filter: blur(12px);
}
.composer-box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--app-card);
  border: 1px solid var(--app-border-strong);
  border-radius: 16px;
  padding: 6px 6px 6px 12px;
}
.composer-box:focus-within {
  border-color: rgba(74, 158, 255, 0.5);
}
.composer-box textarea {
  flex: 1;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  color: var(--app-text);
  font: inherit;
  font-size: 14px;
  line-height: 1.5;
  max-height: 120px;
  padding: 7px 0;
}
.composer-box textarea::placeholder {
  color: var(--app-faint);
}
.send-btn {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: #0f1a2a;
  background: linear-gradient(135deg, #7cc0ff, #4a9eff);
  cursor: pointer;
}
.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.composer-tip {
  margin: 6px 2px 0;
  font-size: 10px;
  color: var(--app-faint);
  text-align: center;
}

.term-popup {
  padding: 18px 16px calc(20px + var(--app-safe-bottom));
}
.term-head h3 {
  margin: 0;
  font-size: 17px;
  color: var(--app-text-strong);
}
.term-head p {
  margin: 5px 0 14px;
  font-size: 12px;
  color: var(--app-muted);
}
.term-field {
  background: var(--app-card-2);
  border: 1px solid var(--app-border-strong);
  border-radius: 14px;
  margin-bottom: 12px;
}
.term-out {
  margin-top: 14px;
  padding: 12px 13px;
  border-radius: 12px;
  background: var(--app-bg-soft);
  border: 1px solid var(--app-border);
  color: var(--app-text);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  max-height: 40vh;
  overflow-y: auto;
}
</style>
