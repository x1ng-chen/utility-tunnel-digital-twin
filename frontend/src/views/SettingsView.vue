<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { isAxiosError } from 'axios';
import AppShell from '../components/AppShell.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { AdminUser, RegistrationRequest, Threshold, TwinModelRelease } from '../types';
import { createThresholdDraft, reconcileThresholdDraft, thresholdDraftConflicts, type ThresholdDraft } from '../utils/thresholdDraft';

const store = useOperationsStore();
const auth = useAuthStore();
const canWrite = computed(() => !store.offline && auth.user?.role === 'administrator');
const message = ref('');
const drafts = reactive<Record<string, ThresholdDraft>>({});
const thresholdBusyKey = ref<string | null>(null);
const users = ref<AdminUser[]>([]);
const usersLoading = ref(false);
const usersError = ref('');
const userBusyId = ref<number | null>(null);
const applications = ref<RegistrationRequest[]>([]);
const applicationsLoading = ref(false);
const applicationsError = ref('');
const applicationBusyId = ref<number | null>(null);
const approvedSetupLink = ref('');
const reviewNotes = reactive<Record<number, string>>({});
const passwordForm = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' });
const passwordMessage = ref('');
const passwordError = ref('');
const passwordSaving = ref(false);
const modelReleases = ref<TwinModelRelease[]>([]);
const modelLoading = ref(false);
const modelError = ref('');
const modelMessage = ref('');
const modelUpload = reactive({ version: '', notes: '', file: null as File | null });
const modelBusyId = ref<number | 'upload' | null>(null);
const modelFileInput = ref<HTMLInputElement>();

watch(() => store.thresholds.map((item) => ({ key: item.key, warning: item.warning, alarm: item.alarm, version: item.version })), (items) => {
  items.forEach((item) => {
    drafts[item.key] = reconcileThresholdDraft(drafts[item.key], item);
  });
}, { immediate: true, deep: true });

function draft(item: Threshold) {
  return drafts[item.key] || (drafts[item.key] = createThresholdDraft(item));
}

async function save(item: Threshold) {
  if (!canWrite.value || thresholdBusyKey.value !== null) return;
  if (thresholdDraftConflicts(draft(item), item)) {
    message.value = '配置已发生变化。请先载入最新值，核对后重新修改。';
    return;
  }
  thresholdBusyKey.value = item.key;
  message.value = '';
  const values = draft(item);
  try {
    await store.updateThreshold(item, values.warning, values.alarm);
    drafts[item.key] = createThresholdDraft(item);
    message.value = `${item.label} 已保存`;
  } catch (cause) {
    if (isAxiosError(cause) && cause.response?.status === 409) {
      await store.refresh('api');
      message.value = '其他会话已更新配置，你的草稿尚未保存。请载入最新值后重新修改。';
    } else {
      message.value = cause instanceof Error ? cause.message : '保存失败';
    }
  } finally {
    thresholdBusyKey.value = null;
  }
}

const canManageUsers = computed(() => canWrite.value && store.source === 'api');

async function loadUsers() {
  if (!canManageUsers.value) {
    users.value = [];
    return;
  }
  usersLoading.value = true;
  usersError.value = '';
  try {
    users.value = (await api.adminUsers({ page: 1, pageSize: 100 })).data.items;
  } catch (cause: unknown) {
    usersError.value = cause instanceof Error ? cause.message : '用户列表加载失败';
  } finally {
    usersLoading.value = false;
  }
}

async function updateUser(user: AdminUser, changes: Record<string, unknown>) {
  if (!canManageUsers.value || userBusyId.value !== null || user.role === 'administrator') return;
  usersError.value = '';
  userBusyId.value = user.id;
  try {
    const response = await api.updateAdminUser(user.id, changes);
    Object.assign(user, response.data);
  } catch (cause: unknown) {
    usersError.value = cause instanceof Error ? cause.message : '用户更新失败';
    await loadUsers();
  } finally {
    userBusyId.value = null;
  }
}

async function loadApplications() {
  if (!canManageUsers.value) { applications.value = []; return; }
  applicationsLoading.value = true; applicationsError.value = '';
  try {
    const [pending, approved] = await Promise.all([
      api.registrationRequests({ page: 1, pageSize: 100, status: 'pending' }),
      api.registrationRequests({ page: 1, pageSize: 100, status: 'approved' }),
    ]);
    applications.value = [...pending.data.items, ...approved.data.items.filter((item: RegistrationRequest) => !item.passwordSetAt)];
  }
  catch (cause: unknown) { applicationsError.value = cause instanceof Error ? cause.message : '账号申请加载失败'; }
  finally { applicationsLoading.value = false; }
}

async function reviewApplication(application: RegistrationRequest, nextStatus: 'approved' | 'rejected') {
  if (!canManageUsers.value || applicationBusyId.value !== null) return;
  applicationBusyId.value = application.id;
  applicationsError.value = '';
  approvedSetupLink.value = '';
  try {
    const reviewNote = reviewNotes[application.id]?.trim() || '';
    if (nextStatus === 'rejected' && !reviewNote) {
      applicationsError.value = '不予批准时请填写原因，方便申请人了解后续处理方式。';
      return;
    }
    const response = await api.reviewRegistrationRequest(application.id, { status: nextStatus, reviewNote });
    if (nextStatus === 'approved' && response.data.setupToken) {
      approvedSetupLink.value = `${window.location.origin}/login#setupToken=${encodeURIComponent(response.data.setupToken)}`;
    }
    applications.value = applications.value.filter((item) => item.id !== application.id);
    delete reviewNotes[application.id];
    await loadUsers();
  } catch (cause: unknown) { applicationsError.value = cause instanceof Error ? cause.message : '账号申请处理失败'; }
  finally { applicationBusyId.value = null; }
}

async function reissueSetupLink(application: RegistrationRequest) {
  if (!canManageUsers.value || applicationBusyId.value !== null) return;
  applicationBusyId.value = application.id;
  applicationsError.value = '';
  approvedSetupLink.value = '';
  try {
    const response = await api.reissueRegistrationSetupToken(application.id);
    approvedSetupLink.value = `${window.location.origin}/login#setupToken=${encodeURIComponent(response.data.setupToken)}`;
    Object.assign(application, response.data);
  } catch (cause: unknown) {
    applicationsError.value = cause instanceof Error ? cause.message : '一次性链接重新签发失败';
  } finally { applicationBusyId.value = null; }
}

async function changePassword() {
  passwordMessage.value = ''; passwordError.value = '';
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    passwordError.value = '两次输入的新密码不一致。';
    return;
  }
  passwordSaving.value = true;
  try {
    passwordMessage.value = await auth.changePassword(passwordForm.currentPassword, passwordForm.newPassword);
    passwordForm.currentPassword = ''; passwordForm.newPassword = ''; passwordForm.confirmPassword = '';
  } catch (cause: unknown) {
    passwordError.value = cause instanceof Error ? cause.message : '密码更新失败，请稍后重试。';
  } finally { passwordSaving.value = false; }
}

async function loadModelReleases() {
  if (!canManageUsers.value) { modelReleases.value = []; return; }
  modelLoading.value = true; modelError.value = '';
  try { modelReleases.value = (await api.twinModels({ page: 1, pageSize: 100 })).data.items; }
  catch (cause: unknown) { modelError.value = cause instanceof Error ? cause.message : '模型版本加载失败'; }
  finally { modelLoading.value = false; }
}

function chooseModel(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null;
  modelUpload.file = file;
  modelError.value = '';
  if (file && !file.name.toLowerCase().endsWith('.glb')) modelError.value = '请选择 Blender 导出的 .glb 文件。';
  else if (file && file.size > 32 * 1024 * 1024) modelError.value = '模型文件不能超过 32 MB。';
}

async function uploadModel() {
  modelError.value = ''; modelMessage.value = '';
  if (!modelUpload.file) { modelError.value = '请先选择 GLB 模型文件。'; return; }
  if (!modelUpload.file.name.toLowerCase().endsWith('.glb')) { modelError.value = '请选择 Blender 导出的 .glb 文件。'; return; }
  if (modelUpload.file.size > 32 * 1024 * 1024) { modelError.value = '模型文件不能超过 32 MB。'; return; }
  if (!modelUpload.version.trim()) { modelError.value = '请填写模型版本号。'; return; }
  modelBusyId.value = 'upload';
  try {
    const payload = new FormData();
    payload.append('version', modelUpload.version.trim());
    payload.append('notes', modelUpload.notes.trim());
    payload.append('file', modelUpload.file);
    const release = (await api.uploadTwinModel(payload)).data as TwinModelRelease;
    modelUpload.version = ''; modelUpload.notes = ''; modelUpload.file = null;
    if (modelFileInput.value) modelFileInput.value.value = '';
    modelMessage.value = release.isCompatible
      ? `模型校验通过：${release.namedNodeCount} 个命名节点，已覆盖全部设备，可启用。`
      : `文件结构有效，但有 ${release.missingAssetCodes.length} 个设备未映射；修正 Blender 节点名称后再启用。`;
    await loadModelReleases();
  } catch (cause: unknown) { modelError.value = cause instanceof Error ? cause.message : '模型上传失败'; }
  finally { modelBusyId.value = null; }
}

async function activateModel(release: TwinModelRelease) {
  modelError.value = ''; modelMessage.value = ''; modelBusyId.value = release.id;
  try {
    await api.activateTwinModel(release.id);
    modelMessage.value = `模型 ${release.version} 已启用；历史版本仍可随时回滚。`;
    await loadModelReleases();
  } catch (cause: unknown) { modelError.value = cause instanceof Error ? cause.message : '模型版本切换失败'; }
  finally { modelBusyId.value = null; }
}

function formatBytes(bytes: number) { return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`; }

function modelContractSummary(release: TwinModelRelease) {
  if (release.isCompatible) return '设备节点映射完整，可以安全启用';
  const problems = [];
  if (release.missingAssetCodes.length) problems.push(`${release.missingAssetCodes.length} 个设备未映射`);
  if (release.duplicateNodeNames.length) problems.push(`${release.duplicateNodeNames.length} 个节点名称重复`);
  return problems.join('，') || '该历史模型需要重新校验';
}

function changeRole(user: AdminUser, event: Event) {
  const value = (event.target as HTMLSelectElement | null)?.value;
  if (value) void updateUser(user, { role: value });
}

watch([() => store.source, () => auth.user?.role], () => { void loadUsers(); void loadApplications(); void loadModelReleases(); }, { immediate: true });
</script>

<template>
  <AppShell>
    <section class="section-title"><div><span class="eyebrow light">平台管理</span><h1>系统配置</h1><p>管理告警阈值与数据服务，管理员变更会写入审计日志。</p></div><span class="config-source"><i />{{ store.offline ? '离线数据快照' : '数据服务在线' }}</span></section>
    <nav class="settings-sections" aria-label="配置分区导航">
      <a href="#threshold-settings">告警阈值</a><a href="#password-settings">账户安全</a>
      <template v-if="auth.user?.role === 'administrator'"><a href="#approval-settings">账号审批</a><a href="#model-settings">三维模型</a><a href="#account-settings">已开通账号</a></template>
    </nav>
    <section id="threshold-settings" class="settings-panel" aria-label="告警阈值">
      <div class="settings-head"><span>阈值策略</span><small>报警值必须高于预警值</small></div>
      <div v-for="item in store.thresholds" :key="item.key" class="threshold-row">
        <div><b>{{ item.label }}</b><small>计量单位：{{ item.unit || '无单位' }}</small><template v-if="thresholdDraftConflicts(draft(item), item)"><small role="status">配置已更新，请核对最新值后再修改。</small><button :disabled="thresholdBusyKey !== null" @click="drafts[item.key] = createThresholdDraft(item)">放弃草稿，载入最新值</button></template></div>
        <label>预警值<input v-model.number="draft(item).warning" :disabled="!canWrite || thresholdBusyKey !== null" type="number" min="0" step="any" :aria-label="`${item.label}预警值`" /></label>
        <label>报警值<input v-model.number="draft(item).alarm" :disabled="!canWrite || thresholdBusyKey !== null" type="number" min="0" step="any" :aria-label="`${item.label}报警值`" /></label>
        <button :disabled="!canWrite || thresholdBusyKey !== null || thresholdDraftConflicts(draft(item), item)" @click="save(item)">{{ thresholdBusyKey === item.key ? '保存中…' : '保存设置' }}</button>
      </div>
      <p v-if="store.offline" class="inline-message">数据服务离线，当前配置只读；重新连接后可继续修改。</p>
      <p v-else-if="!canWrite" class="inline-message">仅管理员可修改告警阈值。</p>
      <p v-else-if="message" class="inline-message" role="status">{{ message }}</p>
    </section>
    <section id="password-settings" class="settings-panel password-settings-panel" aria-label="账户安全">
      <div class="settings-head"><span>账户安全</span><small>更新密码后，其他已登录设备会自动失效</small></div>
      <form class="password-form" @submit.prevent="changePassword">
        <input type="text" name="username" autocomplete="username" :value="auth.user?.email || ''" readonly hidden />
        <label>当前密码<input v-model="passwordForm.currentPassword" :disabled="store.source !== 'api' || passwordSaving" required type="password" autocomplete="current-password" /></label>
        <label>新密码<input v-model="passwordForm.newPassword" :disabled="store.source !== 'api' || passwordSaving" required minlength="8" type="password" autocomplete="new-password" placeholder="至少 8 位，避免使用常见密码" /></label>
        <label>确认新密码<input v-model="passwordForm.confirmPassword" :disabled="store.source !== 'api' || passwordSaving" required minlength="8" type="password" autocomplete="new-password" /></label>
        <button class="primary-button compact-button" :disabled="store.source !== 'api' || passwordSaving" type="submit">{{ passwordSaving ? '正在更新…' : '更新密码' }}</button>
      </form>
      <p v-if="store.source !== 'api'" class="inline-message">演示模式不保存真实账号；连接数据服务后可更新自己的登录密码。</p>
      <p v-else-if="passwordError" class="inline-message error-message" role="alert">{{ passwordError }}</p>
      <p v-else-if="passwordMessage" class="inline-message" role="status">{{ passwordMessage }}</p>
    </section>
    <section v-if="auth.user?.role === 'administrator'" id="approval-settings" class="settings-panel user-settings-panel" aria-label="账号申请审批">
      <div class="settings-head"><span>账号申请审批</span><small>仅管理员可批准运维员和查看者账号</small></div>
      <div v-if="approvedSetupLink" class="inline-message" role="status">一次性密码设置链接（仅显示本次）：<a :href="approvedSetupLink">{{ approvedSetupLink }}</a></div>
      <div v-if="applicationsLoading" class="empty-state">正在加载账号申请…</div>
      <div v-else-if="applicationsError" class="inline-message error-message" role="alert">{{ applicationsError }}</div>
      <div v-else-if="!applications.length" class="empty-state">当前没有待审批或待设置密码的账号申请。</div>
      <p v-if="applicationBusyId !== null" class="inline-message" role="status">正在处理账号申请，请稍候…</p>
      <div v-for="application in applications" :key="application.id" class="registration-request-row" :aria-busy="applicationBusyId === application.id">
        <div><b>{{ application.display_name }}</b><small>申请账号：{{ application.account }} · 申请时间：{{ new Date(application.createdAt).toLocaleString('zh-CN') }}</small></div>
        <span :class="['role-badge', application.requestedRole]">{{ application.requestedRole === 'operator' ? '申请运维员' : '申请查看者' }}</span>
        <template v-if="application.status === 'pending'">
          <label class="review-note">审批说明（不予批准必填）<input v-model="reviewNotes[application.id]" :disabled="!canManageUsers || applicationBusyId !== null" maxlength="300" placeholder="例如：请使用单位分配的账号名称后重新申请" /></label>
          <div class="registration-actions">
            <button class="approve-button" :disabled="!canManageUsers || applicationBusyId !== null" @click="reviewApplication(application, 'approved')">批准并创建账号</button>
            <button class="reject-button" :disabled="!canManageUsers || applicationBusyId !== null || !reviewNotes[application.id]?.trim()" @click="reviewApplication(application, 'rejected')">不予批准</button>
          </div>
        </template>
        <template v-else>
          <p class="inline-message">账号已批准但尚未设置密码。{{ application.setupExpiresAt && new Date(application.setupExpiresAt) <= new Date() ? '原链接已过期。' : '可重新签发一次性链接。' }}</p>
          <div class="registration-actions"><button class="approve-button" :disabled="!canManageUsers || applicationBusyId !== null" @click="reissueSetupLink(application)">重新签发密码设置链接</button></div>
        </template>
      </div>
    </section>
    <section v-if="auth.user?.role === 'administrator'" id="model-settings" class="settings-panel model-release-panel" aria-label="三维模型版本">
      <div class="settings-head"><span>三维模型版本</span><small>上传 GLB、完整性校验、启用和历史版本回滚</small></div>
      <form class="model-upload-form" @submit.prevent="uploadModel">
        <label>版本号<input v-model.trim="modelUpload.version" required maxlength="40" pattern="[A-Za-z0-9][A-Za-z0-9._\x2D]{0,39}" title="仅使用字母、数字、点、短横线和下划线" placeholder="例如：2026.08-r1" /></label>
        <label>GLB 模型<input ref="modelFileInput" required type="file" accept=".glb,model/gltf-binary" @change="chooseModel" /></label>
        <label class="model-notes">版本说明<input v-model.trim="modelUpload.notes" maxlength="500" placeholder="说明本次模型结构、节点或材质调整" /></label>
        <button class="primary-button compact-button" :disabled="modelBusyId === 'upload' || !canManageUsers" type="submit">{{ modelBusyId === 'upload' ? '正在校验上传…' : '上传并校验' }}</button>
      </form>
      <p v-if="modelError" class="inline-message error-message" role="alert">{{ modelError }}</p>
      <p v-else-if="modelMessage" class="inline-message" role="status">{{ modelMessage }}</p>
      <div v-if="modelLoading" class="empty-state">正在读取模型版本…</div>
      <div v-else-if="!modelReleases.length" class="empty-state">尚未上传模型版本；当前三维页面继续使用随系统发布的基础模型。</div>
      <div v-else class="model-release-list">
        <article v-for="release in modelReleases" :key="release.id" :class="['model-release-row', release.status]">
          <div><span :class="['model-release-status', release.status]">{{ release.status === 'active' ? '当前使用' : release.status === 'draft' ? '待启用' : '历史版本' }}</span><b>{{ release.version }}</b><small>{{ release.originalName }} · {{ formatBytes(release.sizeBytes) }} · {{ new Date(release.createdAt).toLocaleString('zh-CN') }}</small></div>
          <div class="model-contract-result">
            <strong :class="release.isCompatible ? 'compatible' : 'blocked'">{{ release.isCompatible ? '校验通过' : '需要修订' }}</strong>
            <span>{{ modelContractSummary(release) }}</span>
            <small v-if="release.nodeCount">场景 {{ release.nodeCount }} 个节点 · {{ release.meshCount }} 个网格 · {{ release.namedNodeCount }} 个节点已命名</small>
            <small v-if="release.missingAssetCodes.length" :title="release.missingAssetCodes.join('、')">未映射：{{ release.missingAssetCodes.join('、') }}</small>
          </div>
          <p>{{ release.notes || '未填写版本说明' }}</p>
          <code :title="release.sha256">文件校验码 {{ release.sha256.slice(0, 12) }}</code>
          <button v-if="release.status !== 'active'" class="outline-button" :disabled="modelBusyId === release.id || !release.isCompatible" :title="release.isCompatible ? '' : '请修正设备节点映射后重新上传'" @click="activateModel(release)">{{ modelBusyId === release.id ? '正在切换…' : !release.isCompatible ? '校验未通过' : release.status === 'retired' ? '回滚到此版本' : '启用此版本' }}</button>
          <span v-else class="active-release-note">三维页面已自动使用</span>
        </article>
      </div>
    </section>
    <section v-if="auth.user?.role === 'administrator'" id="account-settings" class="settings-panel user-settings-panel" aria-label="已开通账号">
      <div class="settings-head"><span>已开通账号</span><small>系统仅保留一个管理员账号</small></div>
      <div v-if="usersLoading" class="empty-state">正在加载用户…</div>
      <div v-else-if="usersError" class="inline-message error-message" role="alert">{{ usersError }}</div>
      <div v-else-if="!users.length" class="empty-state">当前没有可管理的用户。</div>
      <div v-for="user in users" :key="user.id" class="user-row">
        <div><b>{{ user.displayName }}</b><small>登录账号：{{ user.email }}</small></div>
        <span v-if="user.role === 'administrator'" class="role-badge administrator">唯一管理员</span>
        <select v-else :value="user.role" :disabled="!canManageUsers || userBusyId !== null" :aria-label="`${user.displayName} 的角色`" @change="changeRole(user, $event)"><option value="operator">运维员</option><option value="viewer">查看者</option></select>
        <button v-if="user.role !== 'administrator'" class="compact-button" :disabled="!canManageUsers || userBusyId !== null" @click="updateUser(user, { isActive: !user.isActive })">{{ userBusyId === user.id ? '正在保存…' : user.isActive ? '暂停使用' : '恢复使用' }}</button>
        <span v-else class="account-protected">管理员账号受保护</span>
      </div>
      <p v-if="!canManageUsers && !store.offline" class="inline-message">当前账号没有用户管理权限。</p>
    </section>
  </AppShell>
</template>

<style scoped>
.settings-sections { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.settings-sections a { padding: 11px 16px; border: 1px solid var(--ops-line); color: var(--ops-muted); font-size: 13px; text-decoration: none; }
.settings-sections a:hover, .settings-sections a:focus-visible { color: var(--ops-signal); border-color: var(--ops-signal); }
.settings-panel { margin-bottom: 24px; scroll-margin-top: 100px; }
.settings-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; padding: 20px 24px; }
.settings-head small { color: var(--ops-muted); font-size: 12px; line-height: 1.6; }
.threshold-row { display: grid; grid-template-columns: minmax(150px, 1.4fr) repeat(2, minmax(100px, 1fr)) auto; gap: 18px; align-items: end; padding: 20px 24px; }
.threshold-row label, .password-form label, .model-upload-form label { display: grid; min-width: 0; gap: 8px; color: var(--ops-muted); font-size: 12px; }
.threshold-row small { display: block; margin-top: 8px; font-size: 12px; color: var(--ops-muted); }
.threshold-row input, .password-form input, .model-upload-form input { width: 100%; min-width: 0; min-height: 44px; }
.threshold-row button { min-height: 44px; padding: 10px 16px; border: 1px solid var(--ops-line); color: var(--ops-signal); background: var(--ops-panel); white-space: nowrap; }
.password-form, .model-upload-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; padding: 24px; align-items: end; }
.model-upload-form .model-notes { grid-column: auto; }
.registration-request-row, .user-row, .model-release-row { padding: 20px 24px; gap: 18px; min-width: 0; }
.registration-request-row > *, .user-row > *, .model-release-row > * { min-width: 0; overflow-wrap: anywhere; }
.registration-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.registration-actions button { min-height: 44px; }
.user-row small { display: block; color: var(--ops-muted); margin-top: 8px; }
.inline-message a { overflow-wrap: anywhere; }
@container (max-width: 850px) {
  .threshold-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .threshold-row > div { grid-column: 1 / -1; }
  .threshold-row > button { grid-column: 1 / -1; justify-self: end; }
  .registration-request-row, .model-release-row { display: grid; grid-template-columns: minmax(0, 1fr); }
}
@container (max-width: 480px) {
  .password-form, .model-upload-form, .user-row { grid-template-columns: minmax(0, 1fr); }
  .settings-sections a { flex: 1 1 40%; text-align: center; }
}
</style>
