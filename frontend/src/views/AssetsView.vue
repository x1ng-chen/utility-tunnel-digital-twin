<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
const store = useOperationsStore();
const search = ref('');
const visible = computed(() => store.assets.filter((item) => `${item.code} ${item.name} ${item.zone}`.toLowerCase().includes(search.value.toLowerCase())));
</script>
<template><AppShell><section class="section-title"><div><span class="eyebrow light">ASSET REGISTER</span><h1>设备台账</h1><p>设备位置、健康状态与孪生模型统一维护。</p></div><input v-model="search" class="search-input" placeholder="搜索设备编码、名称或区域" /></section><section class="asset-grid"><article v-for="asset in visible" :key="asset.id" class="asset-card"><div class="asset-icon" :class="asset.status">◈</div><div><span class="eyebrow">{{ asset.zone }}</span><h2>{{ asset.name }}</h2><b>{{ asset.code }}</b><p>{{ asset.type }} · {{ asset.mesh }}</p></div><span :class="['asset-status', asset.status]">{{ asset.status === 'normal' ? '正常' : asset.status === 'warning' ? '关注' : asset.status }}</span></article></section></AppShell></template>
