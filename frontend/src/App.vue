<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { useOperationsStore } from './stores/operations';
import { useAuthStore } from './stores/auth';

const operations = useOperationsStore();
const auth = useAuthStore();
let timer: number | undefined;
onMounted(() => { if (auth.isAuthenticated) operations.refresh(window.localStorage.getItem('ut-django-token') ? 'api' : 'demo'); timer = window.setInterval(() => operations.tick(), 5000); });
onUnmounted(() => { if (timer) window.clearInterval(timer); });
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in"><component :is="Component" /></Transition>
  </RouterView>
  <Transition name="toast"><div v-if="operations.notice" class="toast" @click="operations.notice = ''">{{ operations.notice }}<span>×</span></div></Transition>
</template>
