import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, type AssistantMessage } from '../services/api';

export const useAiAssistantStore = defineStore('aiAssistant', () => {
  const messages = ref<AssistantMessage[]>([]);
  const pending = ref(false);
  const error = ref('');
  let revision = 0;

  async function send(question: string, page: string) {
    const content = question.trim();
    if (!content || pending.value) return;
    const history = [...messages.value.slice(-10), { role: 'user' as const, content }];
    while (history.reduce((length, item) => length + item.content.length, 0) > 8000) history.splice(0, 2);
    const requestRevision = revision;
    pending.value = true;
    error.value = '';
    try {
      const response = await api.assistantChat(history, page);
      if (requestRevision === revision) messages.value.push({ role: 'user', content }, { role: 'assistant', content: response.data.reply.slice(0, 2000) });
    } catch (cause: unknown) {
      const failure = cause as { response?: { data?: { message?: string } }; code?: string };
      if (requestRevision === revision) {
        error.value = failure.response?.data?.message || (failure.code === 'ECONNABORTED' ? 'AI 助手响应超时，请稍后重试。' : '暂时无法连接 AI 助手，请稍后重试。');
        throw cause;
      }
    } finally {
      if (requestRevision === revision) pending.value = false;
    }
  }

  function clear() {
    revision += 1;
    messages.value = [];
    error.value = '';
    pending.value = false;
  }

  return { messages, pending, error, send, clear };
});
