<script setup lang="ts">
import AppShell from '../components/AppShell.vue';
</script>

<template>
  <AppShell>
    <section class="hero">
      <div><span class="eyebrow">404 · 页面不可用</span><h1>页面未找到</h1><p>这个地址不存在或已经调整。你可以通过左侧导航继续工作。</p></div>
    </section>
    <section class="panel recovery-panel" aria-label="恢复导航">
      <h2>选择接下来的工作</h2>
      <p>返回总览查看当前运行情况，或进入告警中心处理异常。</p>
      <div class="recovery-actions"><RouterLink class="primary-button" to="/dashboard">返回运行总览</RouterLink><RouterLink class="outline-button" to="/alerts">进入告警中心</RouterLink></div>
    </section>
  </AppShell>
</template>

<style scoped>
.recovery-panel { padding: 24px; }
.recovery-panel h2 { margin: 0 0 12px; }
.recovery-panel p { color: var(--ops-muted); line-height: 1.8; }
.recovery-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.recovery-actions a { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; text-decoration: none; }
</style>
