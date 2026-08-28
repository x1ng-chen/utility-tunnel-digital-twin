import type { AuditEntry } from '../types';

type AuditPresentation = { title: string; description: string };

function value(detail: Record<string, unknown>, key: string): string {
  const item = detail[key];
  if (Array.isArray(item)) return item.length ? item.map(String).join('、') : '';
  return item == null ? '' : String(item);
}

export function presentAudit(entry: AuditEntry): AuditPresentation {
  const code = value(entry.detail, 'code') || value(entry.detail, 'assetCode');
  const labels: Record<string, AuditPresentation> = {
    'auth.login': { title: '用户登录系统', description: '已完成身份验证并进入运维平台。' },
    'auth.logout': { title: '用户退出系统', description: '已安全结束本次会话。' },
    'alert.acknowledged': { title: '确认告警', description: code ? `已确认告警 ${code}。` : '已确认一条待处理告警。' },
    'work_order.created_from_alert': { title: '由告警生成工单', description: code ? `已为 ${code} 创建处置工单。` : '已创建告警处置工单。' },
    'work_order.created_manual': { title: '新建工单', description: code ? `已为设备 ${code} 新建工单。` : '已新建一张工单。' },
    'work_order.transitioned': { title: '更新工单进度', description: '已更新工单处理状态。' },
    'asset.created': { title: '新增设备', description: code ? `已登记设备 ${code}。` : '已新增设备台账。' },
    'asset.updated': { title: '更新设备信息', description: code ? `已更新设备 ${code} 的信息。` : '已更新设备台账信息。' },
    'gis.feature.created': { title: '新增空间对象', description: code ? `已登记空间对象 ${code}。` : '已新增空间对象。' },
    'gis.feature.updated': { title: '更新空间对象', description: code ? `已更新空间对象 ${code} 的信息。` : '已更新空间对象信息。' },
    'gis.feature.imported': { title: '批量导入空间对象', description: `已导入 ${value(entry.detail, 'count') || '多'} 个空间对象，等待审核。` },
    'hardware.binding.created': { title: '登记设备接入信息', description: code ? `已为设备 ${code} 登记接入信息。` : '已登记设备接入信息。' },
    'hardware.binding.updated': { title: '更新设备接入信息', description: code ? `已更新设备 ${code} 的接入信息。` : '已更新设备接入信息。' },
    'setting.threshold.update': { title: '更新告警阈值', description: '已保存一项告警阈值设置。' },
    'report.export': { title: '导出运行报告', description: '已生成运行数据报告。' },
    'registration.approved': { title: '批准账号申请', description: `已批准 ${value(entry.detail, 'account') || '一名用户'} 的账号申请。` },
    'registration.rejected': { title: '未通过账号申请', description: `未通过 ${value(entry.detail, 'account') || '一名用户'} 的账号申请。` },
    'admin.user.updated': { title: '更新用户权限', description: '已更新用户账号状态或角色。' },
  };
  return labels[entry.action] || { title: '完成系统操作', description: '已完成一项运维管理操作。' };
}
