<script setup lang="ts">withDefaults(defineProps<{ tone?: 'normal'|'warning'|'critical'|'offline'|'info' }>(),{tone:'info'});</script>
<template><span :class="tone"><i /><slot /></span></template>
<style scoped>span{display:inline-flex;align-items:center;gap:7px;padding:5px 8px;border:1px solid currentColor;color:var(--ops-signal);font:11px/1 "Cascadia Mono",monospace;letter-spacing:.06em;text-transform:uppercase}i{width:6px;height:6px;background:currentColor}.normal{color:var(--ops-ok)}.warning{color:var(--ops-warn)}.critical{color:var(--ops-danger)}.offline{color:#64748b}</style>
