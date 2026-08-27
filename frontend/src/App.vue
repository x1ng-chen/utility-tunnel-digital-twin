<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useOperationsStore } from './stores/operations';
import { useAuthStore } from './stores/auth';

const operations = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
let timer: number | undefined;
watch(() => auth.isAuthenticated, (isAuthenticated) => {
  if (!isAuthenticated && router.currentRoute.value.path !== '/login') void router.replace('/login');
});
onMounted(() => {
  if (auth.isAuthenticated) operations.refresh(window.sessionStorage.getItem('ut-django-token') ? 'api' : 'demo');
  timer = window.setInterval(() => {
    // API data is server-owned; only the local demo model advances on a timer.
    if (operations.source === 'demo') operations.tick();
  }, 5000);
});
onUnmounted(() => { if (timer) window.clearInterval(timer); });
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in"><component :is="Component" /></Transition>
  </RouterView>
  <Transition name="toast"><div v-if="operations.notice" class="toast" @click="operations.notice = ''">{{ operations.notice }}<span>×</span></div></Transition>
</template>
