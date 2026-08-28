<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useOperationsStore } from './stores/operations';
import { useAuthStore } from './stores/auth';
import ExperienceLayer from './components/ExperienceLayer.vue';

const operations = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
let noticeTimer: number | undefined;
const noticeTone = computed(() => /暂不可用|失败|过期|错误|离线/.test(operations.notice) ? 'warning' : 'success');
watch(() => auth.isAuthenticated, (isAuthenticated) => {
  if (!isAuthenticated && router.currentRoute.value.path !== '/login') void router.replace('/login');
});
watch(() => operations.notice, (notice) => {
  if (noticeTimer) window.clearTimeout(noticeTimer);
  if (!notice) return;
  noticeTimer = window.setTimeout(() => { operations.notice = ''; }, 3000);
});
onMounted(() => { if (auth.isAuthenticated) void operations.refresh('api'); });
onUnmounted(() => { if (noticeTimer) window.clearTimeout(noticeTimer); });
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in"><component :is="Component" /></Transition>
  </RouterView>
  <Transition name="notice">
    <section v-if="operations.notice" :class="['operation-notice', noticeTone]" role="status" aria-live="polite">
      <span class="notice-icon">{{ noticeTone === 'success' ? '✓' : '!' }}</span>
      <div><strong>{{ noticeTone === 'success' ? '操作已完成' : '操作提示' }}</strong><p>{{ operations.notice }}</p></div>
      <i class="notice-progress" />
    </section>
  </Transition>
  <ExperienceLayer />
</template>
