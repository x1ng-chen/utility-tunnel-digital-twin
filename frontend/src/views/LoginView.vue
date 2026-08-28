<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';

const router = useRouter();
const auth = useAuthStore();
const operations = useOperationsStore();
const email = ref('admin');
const password = ref('123');
const signal = ref(72);
let signalTimer: number | undefined;
onMounted(() => { signalTimer = window.setInterval(() => { signal.value = Math.round(58 + Math.random() * 36); }, 2500); });
onUnmounted(() => { if (signalTimer) window.clearInterval(signalTimer); });

async function submit() { auth.clearError(); try { await auth.login(email.value, password.value, 'administrator', 'api'); await operations.refresh('api'); if (auth.isAuthenticated) router.push('/dashboard'); } catch (cause) { if (!auth.error) auth.error = cause instanceof Error ? cause.message : '登录失败，请检查账号或密码。'; } }
</script>

<template>
  <main class="login-screen"><div class="login-grid" /><div class="login-orb orb-one" /><div class="login-orb orb-two" /><section class="login-frame"><header class="login-brand"><span class="brand-mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL OPERATIONS</small></span><span class="secure-label"><i /> SECURE WORKSPACE</span></header><div class="login-body"><div class="login-copy"><span class="eyebrow">DIGITAL TWIN CONTROL ROOM</span><h1>让每一米管廊<br /><em>都清晰可见</em></h1><p>统一管理告警、工单、资产、遥测与空间数据，保障综合管廊安全稳定运行。</p><div class="signal-card"><div><span>系统链路在线</span><b>{{ signal }}%</b></div><div class="signal-bars"><i v-for="n in 18" :key="n" :style="{ height: `${25 + ((n * signal) % 68)}%` }" /></div><small>告警处置 · 工单协同 · 资产管理 · 审计追踪</small></div><div class="login-stats"><span><b>04</b>在线资产</span><span><b>03</b>风险阈值</span><span><b>∞</b>审计留痕</span></div></div><form class="login-card" @submit.prevent="submit"><div class="card-kicker">WELCOME BACK <span>LIVE</span></div><h2>进入运维中枢</h2><p class="login-card-description">请使用已分配的运维账号登录。</p><div class="form-fields"><label>账号或邮箱<input v-model.trim="email" required type="text" autocomplete="username" placeholder="请输入账号或邮箱" /></label><label>密码<input v-model="password" required type="password" autocomplete="current-password" placeholder="请输入密码" /></label></div><p v-if="auth.error" class="form-error" role="alert">{{ auth.error }}</p><button class="login-submit" type="submit" :disabled="auth.loading">{{ auth.loading ? '正在验证身份…' : '安全登录' }}<span>→</span></button><div class="login-foot"><span><i />身份验证受保护</span><span>按角色授权访问</span></div></form></div><footer class="login-footer"><span>© 2026 UT / OPS</span><span>身份认证 · 最小权限 · 全链路审计</span><span>SUPPORT / 运维平台组</span></footer></section></main>
</template>
