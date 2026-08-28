<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { getApiBaseUrl, setApiBaseUrl } from '../services/api';
import type { Role } from '../types';

const router = useRouter();
const auth = useAuthStore();
const operations = useOperationsStore();
const mode = ref<'demo' | 'api'>('demo');
const role = ref<Role>('operator');
const email = ref('admin');
const password = ref('123');
const apiUrl = ref(getApiBaseUrl());
const signal = ref(72);
let signalTimer: number | undefined;
onMounted(() => { signalTimer = window.setInterval(() => { signal.value = Math.round(58 + Math.random() * 36); }, 2500); });
onUnmounted(() => { if (signalTimer) window.clearInterval(signalTimer); });

async function submit() { auth.clearError(); try { if (mode.value === 'api') setApiBaseUrl(apiUrl.value); await auth.login(email.value, password.value, role.value, mode.value); await operations.refresh(mode.value); if (auth.isAuthenticated) router.push('/dashboard'); } catch (cause) { if (!auth.error) auth.error = cause instanceof Error ? cause.message : '登录失败，请检查输入。'; } }
</script>

<template>
  <main class="login-screen"><div class="login-grid" /><div class="login-orb orb-one" /><div class="login-orb orb-two" /><section class="login-frame"><header class="login-brand"><span class="brand-mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL OPERATIONS</small></span><span class="secure-label"><i /> SECURE WORKSPACE</span></header><div class="login-body"><div class="login-copy"><span class="eyebrow">DIGITAL TWIN CONTROL ROOM</span><h1>让每一米管廊<br /><em>都清晰可见</em></h1><p>Vue 3 + Django 企业级运维平台，统一接入告警、工单、资产与遥测。</p><div class="signal-card"><div><span>系统链路在线</span><b>{{ signal }}%</b></div><div class="signal-bars"><i v-for="n in 18" :key="n" :style="{ height: `${25 + ((n * signal) % 68)}%` }" /></div><small>LOCAL SIMULATION · DJANGO API · 24 / 7 OBSERVABILITY</small></div><div class="login-stats"><span><b>04</b>在线资产</span><span><b>03</b>风险阈值</span><span><b>∞</b>审计留痕</span></div></div><form class="login-card" @submit.prevent="submit"><div class="card-kicker">WELCOME BACK <span>LIVE</span></div><h2>进入运维中枢</h2><div class="login-tabs"><button type="button" :class="{ active: mode === 'demo' }" @click="mode = 'demo'">演示工作区</button><button type="button" :class="{ active: mode === 'api' }" @click="mode = 'api'">Django API</button></div><div v-if="mode === 'demo'" class="form-fields"><label>演示角色<select v-model="role"><option value="operator">运维员 · 推荐</option><option value="administrator">管理员</option><option value="viewer">查看者</option></select></label><div class="demo-note"><span>本地安全演示模式</span><small>数据保存在浏览器，不会上传到服务器。</small><b>✓</b></div></div><div v-else class="form-fields"><label>API 地址<input v-model="apiUrl" required type="url" placeholder="http://127.0.0.1:8000/api" /></label><label>工作邮箱<input v-model="email" required type="email" autocomplete="username" /></label><label>密码<input v-model="password" required type="password" autocomplete="current-password" /></label></div><p v-if="auth.error" class="form-error" role="alert">{{ auth.error }}</p><button class="login-submit" type="submit" :disabled="auth.loading">{{ auth.loading ? '正在建立安全会话…' : mode === 'demo' ? '进入演示工作区' : '连接 Django 并登录' }}<span>→</span></button><div class="login-foot"><span><i />TLS 通道就绪</span><span>Vue 3 · Django · PostgreSQL</span></div></form></div><footer class="login-footer"><span>© 2026 UT / OPS</span><span>身份认证 · 最小权限 · 全链路审计</span><span>SUPPORT / 运维平台组</span></footer></section></main>
</template>
