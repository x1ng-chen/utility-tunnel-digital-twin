export type Role = 'administrator' | 'operator' | 'viewer';
export type Status = 'normal' | 'warning' | 'alarm' | 'offline' | 'unknown';
export type AlertStatus = 'open' | 'acknowledged' | 'resolved' | 'closed';
export type WorkOrderStatus = 'draft' | 'open' | 'assigned' | 'in_progress' | 'pending_review' | 'completed' | 'cancelled';
export type IntegrationStatus = 'verified' | 'firmware_connected' | 'calibration_required' | 'pending_verification' | 'optional' | 'non_operational';
export type LocationSource = 'unassigned' | 'demo_anchor' | 'configured' | 'surveyed' | 'gps';

export interface User { id: number; email: string; displayName: string; role: Role; }
export interface AdminUser extends User { isActive: boolean; lastLogin: string | null; createdAt: string; }
export interface Asset { id: number; code: string; name: string; zone: string; type: string; status: Status; hardwareCode: string | null; integrationStatus: IntegrationStatus; interface: string; capabilities: string[]; mesh: string; position: Record<string, number>; latitude: number | null; longitude: number | null; locationSource: LocationSource; installationNote: string; lastSeenAt: string | null; }
export interface Alert { id: number; code: string; assetCode: string | null; severity: 'info' | 'warning' | 'critical'; category: string; status: AlertStatus; title: string; detail: string; openedAt: string; acknowledgedAt?: string | null; acknowledgedBy?: string | null; resolvedAt?: string | null; }
export interface WorkOrder { id: number; code: string; sourceAlertId?: number | null; assetCode: string; title: string; description?: string; priority: 'low' | 'normal' | 'high' | 'urgent'; status: WorkOrderStatus; assigneeName?: string | null; dueAt?: string | null; completedAt?: string | null; createdAt: string; updatedAt: string; version: number; }
export interface Telemetry { id: number; assetCode: string; metric: string; value: number; unit: string; quality: 'good' | 'suspect' | 'bad' | 'missing'; recordedAt: string; }
export interface Threshold { key: string; label: string; warning: number; alarm: number; unit: string; version: number; }
export interface AuditEntry { id: number; actorName: string; action: string; resourceType: string; resourceId: string; detail: Record<string, unknown>; requestId: string; occurredAt: string; }
export interface Dashboard { assets: { total: number; online: number }; health: { value: number }; openAlerts: number; activeWorkOrders: number; telemetry: Telemetry | null; }
