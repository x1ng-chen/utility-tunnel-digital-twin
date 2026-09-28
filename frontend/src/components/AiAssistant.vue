<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { Send, Sparkles, Trash2, X } from 'lucide-vue-next';
import { useAiAssistantStore } from '../stores/aiAssistant';
import { useOperationsStore } from '../stores/operations';
import '../assets/ai-assistant.css';

const props = defineProps<{ pageName: string }>();
const assistant = useAiAssistantStore();
const operations = useOperationsStore();
const open = ref(false);
const draft = ref('');
const input = ref<HTMLTextAreaElement | null>(null);
const log = ref<HTMLElement | null>(null);
const available = computed(() => operations.source === 'api' && !operations.offline);

watch(open, async (isOpen) => {
  if (isOpen) { await nextTick(); input.value?.focus(); }
});

async function send() {
  if (!available.value || !draft.value.trim() || assistant.pending) return;
  try {
    await assistant.send(draft.value, props.pageName);
    draft.value = '';
    await nextTick();
    log.value?.scrollTo({ top: log.value.scrollHeight, behavior: 'smooth' });
    input.value?.focus();
  } catch { /* The store displays the request error and keeps the draft for retry. */ }
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void send();
  }
}
</script>

<template>
  <button class="ai-assistant-launcher" type="button" :aria-expanded="open" aria-controls="ai-assistant-panel" aria-label="打开 AI 助手" @click="open = !open">
    <Sparkles /><span>AI 助手</span>
  </button>
  <Teleport to="body">
    <section v-if="open" id="ai-assistant-panel" class="ai-assistant-panel" role="dialog" aria-label="AI 助手" @keydown.esc="open = false">
      <header class="ai-assistant-header">
        <span class="ai-assistant-avatar"><Sparkles /></span>
        <div><strong>运维 AI 助手</strong><small>DeepSeek · {{ pageName }}</small></div>
        <button type="button" aria-label="清空对话" title="清空对话" :disabled="assistant.pending || !assistant.messages.length" @click="assistant.clear()"><Trash2 /></button>
        <button type="button" aria-label="关闭 AI 助手" title="关闭" @click="open = false"><X /></button>
      </header>
      <div ref="log" class="ai-assistant-log" role="log" aria-live="polite" aria-label="对话记录">
        <p v-if="!assistant.messages.length" class="ai-assistant-intro">可以问我页面怎么用、告警如何处置，或设备数据该在哪里查看。</p>
        <div v-for="(message, index) in assistant.messages" :key="index" :class="['ai-assistant-message', message.role]">
          <small>{{ message.role === 'user' ? '你' : 'AI 助手' }}</small><p>{{ message.content }}</p>
        </div>
        <p v-if="assistant.pending" class="ai-assistant-pending" role="status">正在生成回答…</p>
      </div>
      <div v-if="!available" class="ai-assistant-status" role="status">登录并连接数据服务后可使用 AI 助手。</div>
      <div v-if="assistant.error" class="ai-assistant-error" role="alert">{{ assistant.error }}</div>
      <div class="ai-assistant-compose">
        <label for="ai-assistant-question">输入问题</label>
        <textarea id="ai-assistant-question" ref="input" v-model="draft" rows="2" maxlength="2000" placeholder="输入问题，Enter 发送，Shift+Enter 换行" :disabled="!available || assistant.pending" @keydown="onInputKeydown" />
        <button type="button" aria-label="发送给 AI 助手" :disabled="!available || assistant.pending || !draft.trim()" @click="send"><Send /></button>
      </div>
      <p class="ai-assistant-footnote">发送当前对话和页面名称；回答不代替现场核查。</p>
    </section>
  </Teleport>
</template>
