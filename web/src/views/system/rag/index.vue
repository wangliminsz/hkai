<template>
	<div class="rag">
		<header class="rag-bar">
			<div class="brand">
				<el-icon class="logo"><ele-Reading /></el-icon>
				<div>
					<h1>香港保險產品知識庫</h1>
					<p class="sub">PageIndex · 推理式檢索 · 帶頁碼引用</p>
				</div>
			</div>

			<div class="picker">
				<el-select v-model="companyId" placeholder="全部保險公司" class="p-company" clearable @change="onCompanyChange">
					<el-option v-for="c in companies" :key="c" :value="c" :label="c" />
				</el-select>
				<el-select v-model="productId" placeholder="自動匹配產品" class="p-select" clearable @change="reset">
					<el-option v-for="p in productOptions" :key="p.product_id" :value="p.product_id" :label="productLabel(p)">
						{{ productLabel(p) }}
					</el-option>
				</el-select>
				<el-tag v-if="selected" :type="selected.indexed ? 'success' : 'warning'" size="small" effect="dark">
					{{ selected.indexed ? '已建索引' : '未建索引' }}
				</el-tag>
				<el-select v-if="productId && compareOptions.length" v-model="compareId" placeholder="對比產品（可選）"
					class="p-compare" clearable @change="resetMessages">
					<el-option v-for="p in compareOptions" :key="p.product_id" :value="p.product_id" :label="productLabel(p)" />
				</el-select>
				<label class="toggle">
					<el-switch v-model="autoPlain" size="small" /> 自動大白話
				</label>
			</div>
		</header>

		<div class="progress" :class="{ active: busy }"><div class="bar"></div></div>

		<main ref="scroller" class="chat">
			<div v-if="!messages.length" class="empty">
				<h2>問一問產品資料</h2>
				<p v-if="selected">{{ selected.summary }}</p>
				<p v-else>選擇產品，或直接提問由系統自動匹配。</p>
				<div class="samples">
					<button v-for="s in sampleList" :key="s" @click="input = s">{{ s }}</button>
				</div>
			</div>

			<div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
				<div class="bubble">
					<div class="role">
						<span>{{ m.role === 'user' ? '我' : '知識庫助手' }}</span>
						<button v-if="m.role === 'assistant' && m.content" class="copy"
							:class="{ done: copiedIndex === i }" @click="copyText(m.content, i)">
							<el-icon><ele-DocumentCopy v-if="copiedIndex !== i" /><ele-Select v-else /></el-icon>
							<span>{{ copiedIndex === i ? '已複製' : '複製' }}</span>
						</button>
					</div>
					<div v-if="m.content" class="text">{{ m.content }}<span v-if="m.streaming" class="caret"></span></div>
					<div v-else-if="m.streaming" class="text typing">
						<span class="spinner"></span>{{ phase || '檢索中…' }}<span v-if="elapsed" class="secs">已等待 {{ elapsed }}s</span>
					</div>

					<div v-if="m.role === 'assistant' && m.content && !m.streaming" class="plain-sec">
						<div class="plain-title">
							大白話版
							<button v-if="!m.plainPending" class="mini" @click="generatePlain(m, m.content)">
								{{ m.plain ? '重新生成' : '生成' }}
							</button>
						</div>
						<div v-if="m.plainPending" class="plain-body pending"><span class="spinner"></span>正在翻成大白話…</div>
						<div v-else-if="m.plainErr" class="plain-body err">生成失敗：{{ m.plainErr }}</div>
						<div v-else-if="m.plain" class="plain-body">{{ m.plain }}</div>
						<div v-else class="plain-body empty">未生成（點「生成」試試）。</div>
					</div>

					<div v-if="m.citations && m.citations.length" class="cites">
						<span v-for="c in m.citations" :key="c.index" class="cite">
							[{{ c.index }}] {{ DOC_LABEL[c.doc_type] || c.doc_type || '文件' }} · p.{{ c.page }}
						</span>
					</div>
				</div>
			</div>
		</main>

		<div v-if="errorMsg" class="error">{{ errorMsg }}</div>

		<footer class="composer">
			<textarea v-model="input" rows="2" placeholder="輸入問題，Enter 送出，Shift+Enter 換行"
				@keydown.enter.exact.prevent="send"></textarea>
			<el-button type="primary" :disabled="busy || !input.trim()" @click="send">送出</el-button>
		</footer>

		<section class="plainbox">
			<div class="plain-head">術語大白話<span class="hint">看不懂就丟進來，用人話講給你聽</span></div>
			<div class="plain-row">
				<textarea v-model="plainTerm" rows="2" placeholder="輸入不懂的術語或整段話，例如：不可異議條款、終期紅利、現金價值…"
					@keydown.enter.exact.prevent="runExplain(plainTerm)"></textarea>
				<el-button :disabled="plainBusy || !plainTerm.trim()" @click="runExplain(plainTerm)">解釋</el-button>
				<el-button :disabled="!plainTerm && !plainResult && !plainErr" @click="clearPlain">清空</el-button>
			</div>
			<div v-if="plainBusy" class="plain-out"><span class="spinner"></span>正在翻成大白話…</div>
			<div v-else-if="plainErr" class="plain-out err">出錯：{{ plainErr }}</div>
			<div v-else-if="plainResult" class="plain-out">{{ plainResult }}</div>
		</section>
	</div>
</template>

<script setup lang="ts" name="ragKb">
import { ref, onMounted, nextTick, computed } from 'vue';
import { getRagProducts, sendChatStream, explainTerm } from './api';

const products = ref<any[]>([]);
const companyId = ref('');
const productId = ref('');
const compareId = ref('');
const messages = ref<any[]>([]);
const input = ref('');
const busy = ref(false);
const errorMsg = ref('');
const scroller = ref<HTMLElement | null>(null);

const phase = ref('');
const elapsed = ref(0);
const copiedIndex = ref(-1);
let timer: any = null;

const plainTerm = ref('');
const plainResult = ref('');
const plainBusy = ref(false);
const plainErr = ref('');
const autoPlain = ref(false);

const selected = computed(() => products.value.find((p) => p.product_id === productId.value) || null);
// 可对比: 同 compare_group, 或同 category
const comparable = (a: any, b: any) => {
	if (!a || !b) return false;
	if (a.compare_group && a.compare_group === b.compare_group) return true;
	return !!(a.category && a.category === b.category);
};
const compareOptions = computed(() => {
	if (!selected.value || !productId.value) return [];
	return products.value.filter((p) => p.product_id !== productId.value && comparable(selected.value, p));
});
// 保险公司(取自 catalog 的 insurer 字段) → 先选公司, 再选该公司的产品
const companies = computed(() => {
	const set = new Set<string>();
	products.value.forEach((p) => {
		if (p.insurer) set.add(p.insurer);
	});
	return Array.from(set);
});
const productOptions = computed(() =>
	companyId.value ? products.value.filter((p) => p.insurer === companyId.value) : products.value
);
const productLabel = (p: any) => `${p.name}${p.indexed ? '' : ' · 未建索引'}`;
const onCompanyChange = () => {
	if (productId.value) {
		const p = products.value.find((x) => x.product_id === productId.value);
		if (p && companyId.value && p.insurer !== companyId.value) productId.value = '';
	}
	reset();
};
const DEFAULT_SAMPLES = ['尚裕終身壽險保什麼？', '危疾加護保(優越版) vs (標準版)有何差異？', '保費未繳的寬限期是多少天？'];
const sampleList = computed(() => (selected.value?.samples?.length ? selected.value.samples : DEFAULT_SAMPLES));
const DOC_LABEL: Record<string, string> = { contract: '合約條款', brochure: '產品介紹' };

onMounted(async () => {
	try {
		const res: any = await getRagProducts();
		products.value = res?.data?.products || res?.products || [];
	} catch (e: any) {
		errorMsg.value = e?.message || '載入產品失敗';
	}
});

function scrollToBottom() {
	nextTick(() => {
		if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
	});
}

function startTimer() {
	elapsed.value = 0;
	phase.value = '已接收問題，正在排隊…';
	timer = setInterval(() => (elapsed.value += 1), 1000);
}
function stopTimer() {
	if (timer) {
		clearInterval(timer);
		timer = null;
	}
}

function reset() {
	messages.value = [];
	errorMsg.value = '';
	compareId.value = '';
}
function resetMessages() {
	messages.value = [];
	errorMsg.value = '';
}

async function copyText(text: string, index: number) {
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
	copiedIndex.value = index;
	setTimeout(() => {
		if (copiedIndex.value === index) copiedIndex.value = -1;
	}, 1500);
}

async function runExplain(term: string) {
	const text = (term || '').trim();
	if (!text || plainBusy.value) return;
	plainBusy.value = true;
	plainErr.value = '';
	plainResult.value = '';
	try {
		const res: any = await explainTerm({ term: text });
		plainResult.value = res?.data?.explanation || '';
	} catch (e: any) {
		plainErr.value = e?.message || '生成失敗';
	} finally {
		plainBusy.value = false;
	}
}

function clearPlain() {
	plainTerm.value = '';
	plainResult.value = '';
	plainErr.value = '';
}

async function generatePlain(msg: any, answer: string) {
	msg.plain = '';
	msg.plainErr = '';
	msg.plainPending = true;
	try {
		const res: any = await explainTerm({ term: answer });
		msg.plain = res?.data?.explanation || '';
	} catch (e: any) {
		msg.plainErr = e?.message || '生成失敗';
	} finally {
		msg.plainPending = false;
		scrollToBottom();
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

	const reply: any = { role: 'assistant', content: '', citations: [], streaming: true };
	messages.value.push(reply);

	try {
		await sendChatStream({
			question,
			productId: productId.value,
			productIds: [productId.value, compareId.value].filter(Boolean),
			history,
			onStart: () => (phase.value = '已連上伺服器，等待模型回應…'),
			onMeta: (m: any) => {
				if (!productId.value) {
					productId.value = m.product_id;
					const p = products.value.find((x) => x.product_id === m.product_id);
					if (p && p.insurer) companyId.value = p.insurer;
				}
				phase.value = '正在檢索產品文件…';
			},
			onDelta: (text: string) => {
				if (!reply.content) phase.value = '正在整理答案…';
				reply.content += text;
				scrollToBottom();
			},
			onDone: (d: any) => {
				reply.content = d.answer;
				reply.citations = d.citations || [];
				reply.streaming = false;
				scrollToBottom();
				if (autoPlain.value && d.answer) generatePlain(reply, d.answer);
			},
		});
	} catch (e: any) {
		errorMsg.value = e?.message || '請求失敗';
		reply.content = reply.content || `（出錯：${errorMsg.value}）`;
		reply.streaming = false;
	} finally {
		stopTimer();
		reply.streaming = false;
		busy.value = false;
		scrollToBottom();
	}
}
</script>

<style scoped lang="scss">
.rag {
	--rag-primary: #409eff;
	--rag-card: #1a1a1c;
	--rag-border: #2a2a2a;
	--rag-border-2: #333333;
	--rag-text: #dadada;
	--rag-muted: #b1b4b8;
	--rag-faint: #8f9297;

	height: calc(100vh - 108px);
	display: flex;
	flex-direction: column;
	background: var(--rag-card);
	border: 1px solid var(--rag-border);
	border-radius: 14px;
	overflow: hidden;
	color: var(--rag-text);
	font-size: 14px;
}

.rag-bar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 16px;
	padding: 14px 18px;
	border-bottom: 1px solid var(--rag-border);
	flex-wrap: wrap;

	.brand {
		display: flex;
		align-items: center;
		gap: 12px;

		.logo {
			font-size: 24px;
			color: var(--rag-primary);
		}
		h1 {
			font-size: 16px;
			margin: 0;
			color: #eaeaea;
		}
		.sub {
			margin: 2px 0 0;
			font-size: 12px;
			color: var(--rag-faint);
		}
	}

	.picker {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;

		.p-company {
			width: 210px;
		}
		.p-select {
			width: 280px;
		}
		.p-compare {
			width: 200px;
		}
		.toggle {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 12.5px;
			color: var(--rag-muted);
			cursor: pointer;
		}
	}
}

.progress {
	height: 3px;
	background: #242424;
	overflow: hidden;

	.bar {
		height: 100%;
		width: 35%;
		background: linear-gradient(90deg, #7ea0ff, #2f5bea);
		border-radius: 3px;
		opacity: 0;
	}
	&.active .bar {
		opacity: 1;
		animation: slide 1.15s ease-in-out infinite;
	}
}
@keyframes slide {
	0% {
		margin-left: -35%;
	}
	100% {
		margin-left: 100%;
	}
}

.chat {
	flex: 1;
	overflow-y: auto;
	padding: 18px;
	display: flex;
	flex-direction: column;
	gap: 14px;

	> .empty {
		margin: auto;
		text-align: center;
		color: var(--rag-muted);
		max-width: 560px;

		h2 {
			color: #eaeaea;
		}
		.samples {
			display: flex;
			flex-direction: column;
			gap: 8px;
			margin-top: 16px;

			button {
				padding: 10px 14px;
				border: 1px solid var(--rag-border-2);
				background: #212121;
				border-radius: 10px;
				cursor: pointer;
				font-size: 13px;
				color: var(--rag-text);
			}
			button:hover {
				background: #262626;
			}
		}
	}
}

.row {
	display: flex;

	&.user {
		justify-content: flex-end;
	}

	.bubble {
		max-width: 82%;
		padding: 12px 14px;
		border-radius: 12px;
		background: #212121;
		line-height: 1.65;
	}

	&.assistant .bubble {
		/* 助手消息占满宽度, 使「大白話版」框在无内容时也是 100% 宽 */
		flex: 1 1 auto;
		width: 100%;
		max-width: 100%;
	}

	&.user .bubble {
		background: #2f5bea;
		color: #fff;
	}

	.role {
		font-size: 11px;
		color: var(--rag-faint);
		margin-bottom: 6px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		min-height: 20px;
	}
	&.user .role {
		color: rgba(255, 255, 255, 0.85);
	}

	.copy {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		border: 1px solid var(--rag-border-2);
		background: #1a1a1c;
		color: var(--rag-muted);
		font-size: 11px;
		padding: 2px 8px;
		border-radius: 6px;
		cursor: pointer;
	}
	.copy:hover {
		color: var(--rag-primary);
		border-color: #3a4a6a;
	}
	.copy.done {
		color: #4caf82;
		border-color: #2f5a45;
	}
	.text {
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 14px;
	}
	.typing {
		color: var(--rag-muted);
		display: flex;
		align-items: center;
	}
}

.spinner {
	display: inline-block;
	width: 14px;
	height: 14px;
	border: 2px solid #3a4a6a;
	border-top-color: var(--rag-primary);
	border-radius: 50%;
	animation: spin 0.8s linear infinite;
	margin-right: 8px;
}
@keyframes spin {
	to {
		transform: rotate(360deg);
	}
}
.secs {
	color: var(--rag-faint);
	font-size: 12px;
	margin-left: 10px;
}
.caret {
	display: inline-block;
	width: 7px;
	height: 15px;
	background: var(--rag-primary);
	margin-left: 2px;
	vertical-align: -2px;
	animation: blink 1s step-end infinite;
}
@keyframes blink {
	50% {
		opacity: 0;
	}
}

.cites {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 10px;

	.cite {
		font-size: 11.5px;
		background: #1a1a1c;
		border: 1px solid var(--rag-border-2);
		color: var(--rag-muted);
		padding: 3px 8px;
		border-radius: 6px;
	}
}

.error {
	color: #f56c6c;
	background: rgba(245, 108, 108, 0.1);
	padding: 8px 18px;
	font-size: 13px;
}

.composer {
	display: flex;
	gap: 10px;
	padding: 12px 18px;
	border-top: 1px solid var(--rag-border);
	align-items: flex-end;

	textarea {
		flex: 1;
		resize: none;
		padding: 10px 12px;
		border: 1px solid var(--rag-border-2);
		border-radius: 10px;
		font-size: 14px;
		font-family: inherit;
		background: #242424;
		color: var(--rag-text);
		outline: none;
	}
	textarea:focus {
		border-color: var(--rag-primary);
	}
}

.plain-sec {
	margin-top: 12px;
	border-top: 1px dashed var(--rag-border-2);
	padding-top: 10px;

	.plain-title {
		font-size: 12.5px;
		font-weight: 600;
		color: #4caf82;
		margin-bottom: 6px;
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.mini {
		border: 1px solid #2f5a45;
		background: #1a1a1c;
		color: #4caf82;
		font-size: 11px;
		padding: 2px 8px;
		border-radius: 6px;
		cursor: pointer;
	}
	.plain-body {
		font-size: 13.5px;
		line-height: 1.7;
		white-space: pre-wrap;
		color: var(--rag-text);
		background: #1e2420;
		border: 1px solid #2f5a45;
		border-radius: 10px;
		padding: 10px 12px;
		display: flex;
		align-items: center;
		width: 100%;
		box-sizing: border-box;
	}
	.plain-body.empty {
		color: var(--rag-faint);
		background: #1a1a1c;
		border-color: var(--rag-border-2);
	}
	.plain-body.err {
		color: #f56c6c;
		border-color: #5a2f2f;
	}
}

.plainbox {
	border-top: 1px solid var(--rag-border);
	background: #171717;
	padding: 12px 18px 16px;

	.plain-head {
		font-size: 13px;
		font-weight: 600;
		color: var(--rag-text);
		margin-bottom: 8px;
		display: flex;
		align-items: baseline;
		gap: 8px;

		.hint {
			font-weight: 400;
			font-size: 11.5px;
			color: var(--rag-faint);
		}
	}
	.plain-row {
		display: flex;
		gap: 10px;
		align-items: flex-end;

		textarea {
			flex: 1;
			resize: none;
			padding: 9px 12px;
			border: 1px solid var(--rag-border-2);
			border-radius: 10px;
			font-size: 13.5px;
			font-family: inherit;
			background: #242424;
			color: var(--rag-text);
			outline: none;
		}
		textarea:focus {
			border-color: var(--rag-primary);
		}
	}
	.plain-out {
		margin-top: 10px;
		padding: 10px 12px;
		background: #1a1a1c;
		border: 1px solid var(--rag-border-2);
		border-radius: 10px;
		font-size: 13.5px;
		line-height: 1.7;
		white-space: pre-wrap;
		color: var(--rag-text);
		display: flex;
		align-items: center;
	}
	.plain-out.err {
		color: #f56c6c;
		border-color: #5a2f2f;
	}
}
</style>
