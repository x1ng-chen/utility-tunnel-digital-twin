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
  signalTimer = window.setInterval(() => {
    signal.value = Math.round(58 + Math.random() * 36);
  }, 2500);
});

onUnmounted(() => {
  if (signalTimer) window.clearInterval(signalTimer);
});

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

async function submit() {
  auth.clearError();
  try {
    await auth.login(email.value, password.value, 'administrator', 'api');
    await operations.refresh('api');
    if (auth.isAuthenticated) void router.push('/dashboard');
  } catch (cause) {
    if (!auth.error) auth.error = cause instanceof Error ? cause.message : '登录失败，请检查账号或密码。';
  }
}

async function submitRegistration() {
  registrationError.value = '';
  registrationMessage.value = '';
  registrationLoading.value = true;
  try {
    await api.requestRegistration({
      account: registration.value.account.trim(),
      displayName: registration.value.displayName.trim(),
      role: registration.value.role,
    });
    registrationMessage.value = '申请已提交。管理员批准后会向你提供一次性密码设置链接。';
    registration.value = { account: '', displayName: '', role: 'operator' };
  } catch (cause) {
    registrationError.value = cause instanceof Error ? cause.message : '申请提交失败，请稍后重试。';
  } finally {
    registrationLoading.value = false;
  }
}

async function submitPasswordSetup() {
  registrationError.value = '';
  registrationMessage.value = '';
  if (setupPassword.value !== setupPasswordConfirm.value) {
    registrationError.value = '两次输入的密码不一致。';
    return;
  }
  registrationLoading.value = true;
  try {
    await api.setupRegistrationPassword(setupToken.value, setupPassword.value);
    registrationMessage.value = '密码设置成功，请返回登录。';
    setupPassword.value = '';
    setupPasswordConfirm.value = '';
  } catch (cause) {
    registrationError.value = cause instanceof Error ? cause.message : '密码设置失败，请联系管理员重新签发链接。';
  } finally {
    registrationLoading.value = false;
  }
}
</script>

<template>
  <main class="login-screen command-login">
    <div class="login-grid" aria-hidden="true" />
    <div class="login-scanline" aria-hidden="true" />

    <section class="login-frame" aria-label="综合管廊数字孪生运维平台登录">
      <header class="login-brand">
        <div class="login-brand-primary">
          <span class="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>
            <b>综合管廊</b>
            <small>数字孪生运维平台</small>
          </span>
        </div>
        <div class="secure-label"><i /> 账号授权访问</div>
      </header>

      <div class="login-body">
        <section class="login-copy" aria-labelledby="login-hero-title">
          <div class="login-hero-index" aria-hidden="true">01</div>
          <span class="eyebrow">综合管廊运行中心</span>
          <h1 id="login-hero-title">现场状态<br /><em>一屏掌握</em></h1>
          <p>统一查看设备状态、告警位置、处置工单和空间数据，让现场人员更快发现问题、更稳妥完成处置。</p>

          <div class="login-capability-grid" aria-label="平台核心能力">
            <span><b>01</b>三维定位<small>故障设备快速聚焦</small></span>
            <span><b>02</b>告警处置<small>确认、派单、闭环留痕</small></span>
            <span><b>03</b>设备监测<small>离线状态与末次数据保留</small></span>
            <span><b>04</b>空间管理<small>设备与模型节点一致映射</small></span>
          </div>

          <div class="signal-card">
            <div class="signal-heading">
              <span>运维流程示意</span>
              <b>发现 → 处置 → 复核</b>
            </div>
            <div class="signal-bars" aria-hidden="true">
              <i v-for="n in 24" :key="n" :style="{ height: `${25 + ((n * signal) % 68)}%` }" />
            </div>
            <small>本地数据服务 · 三维场景 · 告警中心 · 工单协同</small>
          </div>
        </section>

        <aside class="login-access-panel">
          <div class="login-access-meta">
            <span>受控访问区</span>
            <b>运维平台登录</b>
          </div>

          <form v-if="setupToken" class="login-card" @submit.prevent="submitPasswordSetup">
            <div class="card-kicker"><span>密码初始化</span><b>一次性链接</b></div>
            <h2>设置登录密码</h2>
            <p class="login-card-description">请设置至少 12 位的强密码。链接使用后立即失效。</p>
            <div class="form-fields">
              <label>新密码<input v-model="setupPassword" required minlength="12" type="password" autocomplete="new-password" placeholder="请输入新密码" /></label>
              <label>确认密码<input v-model="setupPasswordConfirm" required minlength="12" type="password" autocomplete="new-password" placeholder="请再次输入" /></label>
            </div>
            <p v-if="registrationError" class="form-error" role="alert">{{ registrationError }}</p>
            <p v-if="registrationMessage" class="form-success" role="status">{{ registrationMessage }}</p>
            <button class="login-submit" type="submit" :disabled="registrationLoading">
              {{ registrationLoading ? '正在设置…' : '设置密码' }}<span>→</span>
            </button>
            <button class="login-switch" type="button" @click="returnToLogin">返回登录</button>
          </form>

          <form v-else-if="!showRegistration" class="login-card" @submit.prevent="submit">
            <div class="card-kicker"><span>身份验证</span><b>安全连接</b></div>
            <h2>进入运维中枢</h2>
            <p class="login-card-description">请使用已分配的账号进入相应工作区域。</p>
            <div class="form-fields">
              <label>账号或邮箱<input v-model.trim="email" required type="text" autocomplete="username" placeholder="请输入账号或邮箱" /></label>
              <label>密码<input v-model="password" required type="password" autocomplete="current-password" placeholder="请输入密码" /></label>
            </div>
            <p v-if="auth.error" class="form-error" role="alert">{{ auth.error }}</p>
            <button class="login-submit" type="submit" :disabled="auth.loading">
              {{ auth.loading ? '正在验证身份…' : '安全登录' }}<span>→</span>
            </button>
            <button class="login-switch" type="button" @click="showRegistration = true">
              <span>＋</span> 没有账号？提交注册申请
            </button>
            <div class="login-foot">
              <span><i /> 身份验证受保护</span>
              <span>按角色授权访问</span>
            </div>
          </form>

          <form v-else class="login-card registration-card" @submit.prevent="submitRegistration">
            <div class="card-kicker"><span>账号申请</span><b>审批后启用</b></div>
            <h2>申请平台账号</h2>
            <p class="login-card-description">申请阶段不收集密码。管理员批准后，会签发一次性密码设置链接。</p>
            <div class="form-fields">
              <label>姓名或称呼<input v-model.trim="registration.displayName" required maxlength="80" placeholder="例如：张三" /></label>
              <label>申请账号<input v-model.trim="registration.account" required maxlength="80" autocomplete="username" placeholder="3–80 位字母、数字或 . _ - @" /></label>
              <label>申请角色
                <select v-model="registration.role">
                  <option value="operator">运维员：处理告警与工单</option>
                  <option value="viewer">查看者：仅查看运行信息</option>
                </select>
              </label>
            </div>
            <p v-if="registrationError" class="form-error" role="alert">{{ registrationError }}</p>
            <p v-if="registrationMessage" class="form-success" role="status">{{ registrationMessage }}</p>
            <button class="login-submit" type="submit" :disabled="registrationLoading">
              {{ registrationLoading ? '正在提交…' : '提交注册申请' }}<span>→</span>
            </button>
            <button class="login-switch" type="button" :disabled="registrationLoading" @click="showRegistration = false">← 返回登录</button>
          </form>

          <div class="login-security-note">
            <span>本地部署</span><span>最小权限</span><span>全链路审计</span>
          </div>
        </aside>
      </div>

      <footer class="login-footer">
        <span>综合管廊数字孪生运维平台</span>
        <span>设备定位 · 告警处置 · 工单闭环</span>
        <span>版本 3.6</span>
      </footer>
    </section>
  </main>
</template>
