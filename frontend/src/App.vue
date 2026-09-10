<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useOperationsStore } from './stores/operations';
import { useAuthStore } from './stores/auth';
import ExperienceLayer from './components/ExperienceLayer.vue';
import { Check, TriangleAlert } from 'lucide-vue-next';

const operations = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
let noticeTimer: number | undefined;
let liveTimer: number | undefined;
const noticeTone = computed(() => /暂不可用|失败|过期|错误|离线/.test(operations.notice) ? 'warning' : 'success');
watch(() => auth.isAuthenticated, (isAuthenticated) => {
  if (!isAuthenticated) {
    if (liveTimer) window.clearInterval(liveTimer);
    liveTimer = undefined;
    operations.stopRealtime();
    if (router.currentRoute.value.path !== '/login') void router.replace('/login');
  } else {
    startLiveRefresh();
  }
});
watch(() => operations.noticeRevision, () => {
  if (noticeTimer) window.clearTimeout(noticeTimer);
  if (!operations.notice) return;
  noticeTimer = window.setTimeout(() => { operations.notice = ''; }, 3000);
});
function startLiveRefresh() {
  if (liveTimer || !auth.isAuthenticated) return;
  operations.startRealtime();
  liveTimer = window.setInterval(() => {
    // WebSocket is primary. REST is a bounded recovery path for a disconnected
    // stream, not a disguised two-second polling implementation.
    if (document.visibilityState === 'visible' && operations.realtimeState !== 'connected') void operations.refreshLive();
  }, 2000);
}
function handleVisibility() {
  if (document.visibilityState === 'visible' && auth.isAuthenticated) void operations.refreshLive();
}
onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibility);
  if (auth.isAuthenticated) {
    void operations.refresh('api');
    startLiveRefresh();
  }
});
onUnmounted(() => {
  if (noticeTimer) window.clearTimeout(noticeTimer);
  if (liveTimer) window.clearInterval(liveTimer);
  operations.stopRealtime();
  document.removeEventListener('visibilitychange', handleVisibility);
});
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in"><component :is="Component" :key="route.path" /></Transition>
  </RouterView>
  <Transition name="notice">
    <section v-if="operations.notice" :class="['operation-notice', noticeTone]" role="status" aria-live="polite">
      <span class="notice-icon"><Check v-if="noticeTone === 'success'" /><TriangleAlert v-else /></span>
      <div><strong>{{ noticeTone === 'success' ? '操作已完成' : '操作提示' }}</strong><p>{{ operations.notice }}</p></div>
      <i :key="operations.noticeRevision" class="notice-progress" />
    </section>
  </Transition>
  <ExperienceLayer />
</template>
