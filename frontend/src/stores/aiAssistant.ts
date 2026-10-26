import { ref } from 'vue';
import { defineStore } from 'pinia';
import { api, type AssistantMessage, type AgentResponse, type AgentTask } from '../services/api';

type AgentMessage = AssistantMessage & Omit<AgentResponse, 'reply'>;

export const useAiAssistantStore = defineStore('aiAssistant', () => {
  const messages = ref<AgentMessage[]>([]);
  const pending = ref(false);
  const error = ref('');
  let revision = 0;

  async function inspect() {
    if (pending.value) return;
    const requestRevision = revision;
    pending.value = true;
    error.value = '';
    try {
      const { data } = await api.stationInspection();
      if (requestRevision === revision) {
        const { reply, ...metadata } = data;
        messages.value.push({ role: 'user', content: '巡检五个检测点和31路传感器' },
          { role: 'assistant', content: reply.slice(0, 2000), ...metadata });
      }
    } catch (cause: unknown) {
      if (requestRevision === revision) {
        error.value = '巡检读取失败，请核对登录和数据服务后重试。';
        throw cause;
      }
    } finally { if (requestRevision === revision) pending.value = false; }
  }

  async function send(question: string, page: string, task?: AgentTask) {
    const content = question.trim();
    if (!content || pending.value) return;
    // Evidence is server-generated and must never be replayed as client tool context.
    const history = [...messages.value.slice(-10).map(({ role, content }) => ({ role, content })), { role: 'user' as const, content }];
    while (history.reduce((length, item) => length + item.content.length, 0) > 8000) history.splice(0, 2);
    const requestRevision = revision;
    pending.value = true;
    error.value = '';
    try {
      const response = await api.assistantChat(history, page, task);
      if (requestRevision === revision) {
        const { reply, ...metadata } = response.data;
        messages.value.push({ role: 'user', content }, { role: 'assistant', content: reply.slice(0, 2000), ...metadata });
      }
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

  return { messages, pending, error, send, inspect, clear };
});
