<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useOperationsStore } from './stores/operations';
import { useAuthStore } from './stores/auth';
import ExperienceLayer from './components/ExperienceLayer.vue';

const operations = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
watch(() => auth.isAuthenticated, (isAuthenticated) => {
  if (!isAuthenticated && router.currentRoute.value.path !== '/login') void router.replace('/login');
});
onMounted(() => { if (auth.isAuthenticated) void operations.refresh('api'); });
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in"><component :is="Component" /></Transition>
  </RouterView>
  <Transition name="toast"><div v-if="operations.notice" class="toast" @click="operations.notice = ''">{{ operations.notice }}<span>×</span></div></Transition>
  <ExperienceLayer />
</template>
