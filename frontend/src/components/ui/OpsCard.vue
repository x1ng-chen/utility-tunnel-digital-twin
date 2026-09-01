<script setup lang="ts">
withDefaults(defineProps<{ title?: string; eyebrow?: string; compact?: boolean }>(), { title: '', eyebrow: '', compact: false });
</script>
<template><section :class="['ops-card tactical-frame', { compact }]" data-ui="card"><header v-if="title || eyebrow"><span v-if="eyebrow">[ {{ eyebrow }} ]</span><h2 v-if="title">{{ title }}</h2><slot name="actions" /></header><div class="ops-card-body"><slot /></div></section></template>
<style scoped>.ops-card{border:1px solid var(--ops-line);background:var(--ops-panel)}header{display:grid;grid-template-columns:1fr auto;align-items:end;padding:16px 18px;border-bottom:1px solid var(--ops-line)}header span{grid-column:1/-1;color:var(--ops-muted);font:11px/1.2 "Cascadia Mono",monospace;letter-spacing:.16em}h2{margin:5px 0 0;font-size:18px}.ops-card-body{padding:18px}.compact .ops-card-body{padding:12px}</style>
