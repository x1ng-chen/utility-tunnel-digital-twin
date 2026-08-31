<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { api } from '../services/api';

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const operations = useOperationsStore();
const email = ref('');
const password = ref('');
const showRegistration = ref(false);
const registration = ref({ account: '', displayName: '', role: 'operator' as 'operator' | 'viewer' });
function takeSetupTokenFromAddress(): string {
  const token = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('setupToken') || '';
  if (token) window.history.replaceState(window.history.state, '', route.path);
  return token;
}

// Capture the fragment before the first render and immediately remove the
// credential from the visible address/history entry.
const setupToken = ref(takeSetupTokenFromAddress());
const setupPassword = ref('');
const setupPasswordConfirm = ref('');
const registrationMessage = ref('');
const registrationError = ref('');
const registrationLoading = ref(false);
const signal = ref(72);
let signalTimer: number | undefined;
onMounted(() => {
  signalTimer = window.setInterval(() => { signal.value = Math.round(58 + Math.random() * 36); }, 2500);
});
onUnmounted(() => { if (signalTimer) window.clearInterval(signalTimer); });
watch(() => route.hash, (fragment) => {
  const token = new URLSearchParams(fragment.replace(/^#/, '')).get('setupToken') || '';
  if (!token) return;
  setupToken.value = token;
  window.history.replaceState(window.history.state, '', route.path);
});

function returnToLogin() {
  setupToken.value = '';
  setupPassword.value = '';
  setupPasswordConfirm.value = '';
  registrationMessage.value = '';
  registrationError.value = '';
  void router.replace('/login');
}

async function submit() { auth.clearError(); try { await auth.login(email.value, password.value, 'administrator', 'api'); await operations.refresh('api'); if (auth.isAuthenticated) router.push('/dashboard'); } catch (cause) { if (!auth.error) auth.error = cause instanceof Error ? cause.message : '登录失败，请检查账号或密码。'; } }
async function submitRegistration() {
  registrationError.value = ''; registrationMessage.value = '';
  registrationLoading.value = true;
  try {
    await api.requestRegistration({ account: registration.value.account.trim(), displayName: registration.value.displayName.trim(), role: registration.value.role });
    registrationMessage.value = '申请已提交。管理员批准后会向你提供一次性密码设置链接。';
    registration.value = { account: '', displayName: '', role: 'operator' };
  } catch (cause) { registrationError.value = cause instanceof Error ? cause.message : '申请提交失败，请稍后重试。'; }
  finally { registrationLoading.value = false; }
}

async function submitPasswordSetup() {
  registrationError.value = ''; registrationMessage.value = '';
  if (setupPassword.value !== setupPasswordConfirm.value) { registrationError.value = '两次输入的密码不一致。'; return; }
  registrationLoading.value = true;
  try {
    await api.setupRegistrationPassword(setupToken.value, setupPassword.value);
    registrationMessage.value = '密码设置成功，请返回登录。';
    setupPassword.value = ''; setupPasswordConfirm.value = '';
  } catch (cause) { registrationError.value = cause instanceof Error ? cause.message : '密码设置失败，请联系管理员重新签发链接。'; }
  finally { registrationLoading.value = false; }
}
</script>

<template>
  <main class="login-screen"><div class="login-grid" /><div class="login-orb orb-one" /><div class="login-orb orb-two" /><div class="login-orbit orbit-one" aria-hidden="true" /><div class="login-orbit orbit-two" aria-hidden="true" /><section class="login-frame"><header class="login-brand"><span class="brand-mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL OPERATIONS</small></span><span class="secure-label"><i /> SECURE WORKSPACE</span></header><div class="login-body"><div class="login-copy"><span class="eyebrow">DIGITAL TWIN CONTROL ROOM</span><h1>让每一米管廊<br /><em>都清晰可见</em></h1><p>统一管理告警、工单、资产、遥测与空间数据，保障综合管廊安全稳定运行。</p><div class="signal-card"><div><span>系统链路在线</span><b>{{ signal }}%</b></div><div class="signal-bars"><i v-for="n in 18" :key="n" :style="{ height: `${25 + ((n * signal) % 68)}%` }" /></div><small>告警处置 · 工单协同 · 资产管理 · 审计追踪</small></div><div class="login-stats"><span><b>04</b>在线资产</span><span><b>03</b>风险阈值</span><span><b>∞</b>审计留痕</span></div></div><form v-if="setupToken" class="login-card" @submit.prevent="submitPasswordSetup"><div class="card-kicker">ACCOUNT SETUP <span>一次性链接</span></div><h2>设置登录密码</h2><p class="login-card-description">请设置至少 12 位的强密码。链接使用后立即失效。</p><div class="form-fields"><label>新密码<input v-model="setupPassword" required minlength="12" type="password" autocomplete="new-password" /></label><label>确认密码<input v-model="setupPasswordConfirm" required minlength="12" type="password" autocomplete="new-password" /></label></div><p v-if="registrationError" class="form-error" role="alert">{{ registrationError }}</p><p v-if="registrationMessage" class="form-success" role="status">{{ registrationMessage }}</p><button class="login-submit" type="submit" :disabled="registrationLoading">{{ registrationLoading ? '正在设置…' : '设置密码' }}<span>→</span></button><button class="login-switch" type="button" @click="returnToLogin">返回登录</button></form><form v-else-if="!showRegistration" class="login-card" @submit.prevent="submit"><div class="card-kicker">WELCOME BACK <span>LIVE</span></div><h2>进入运维中枢</h2><p class="login-card-description">请使用已分配的运维账号登录。</p><div class="form-fields"><label>账号或邮箱<input v-model.trim="email" required type="text" autocomplete="username" placeholder="请输入账号或邮箱" /></label><label>密码<input v-model="password" required type="password" autocomplete="current-password" placeholder="请输入密码" /></label></div><p v-if="auth.error" class="form-error" role="alert">{{ auth.error }}</p><button class="login-submit" type="submit" :disabled="auth.loading">{{ auth.loading ? '正在验证身份…' : '安全登录' }}<span>→</span></button><button class="login-switch" type="button" @click="showRegistration = true"><span>＋</span> 没有账号？提交注册申请</button><div class="login-foot"><span><i />身份验证受保护</span><span>按角色授权访问</span></div></form><form v-else class="login-card registration-card" @submit.prevent="submitRegistration"><div class="card-kicker">ACCOUNT REQUEST <span>审批后启用</span></div><h2>申请账号</h2><p class="login-card-description">申请阶段不收集密码；管理员批准后会签发一次性密码设置链接。</p><div class="form-fields"><label>姓名或称呼<input v-model.trim="registration.displayName" required maxlength="80" placeholder="例如：张三" /></label><label>申请账号<input v-model.trim="registration.account" required maxlength="80" autocomplete="username" placeholder="3–80 位字母、数字或 . _ - @" /></label><label>申请角色<select v-model="registration.role"><option value="operator">运维员：处理告警与工单</option><option value="viewer">查看者：仅查看运行信息</option></select></label></div><p v-if="registrationError" class="form-error" role="alert">{{ registrationError }}</p><p v-if="registrationMessage" class="form-success" role="status">{{ registrationMessage }}</p><button class="login-submit" type="submit" :disabled="registrationLoading">{{ registrationLoading ? '正在提交…' : '提交注册申请' }}<span>→</span></button><button class="login-switch" type="button" :disabled="registrationLoading" @click="showRegistration = false">← 返回登录</button></form></div><footer class="login-footer"><span>© 2026 UT / OPS</span><span>身份认证 · 最小权限 · 全链路审计</span><span>SUPPORT / 运维平台组</span></footer></section></main>
</template>
