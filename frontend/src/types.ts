export type Role = 'administrator' | 'operator' | 'viewer';
export type Status = 'normal' | 'warning' | 'alarm' | 'offline' | 'unknown';
export type AlertStatus = 'open' | 'acknowledged' | 'resolved' | 'closed';
export type WorkOrderStatus = 'draft' | 'open' | 'assigned' | 'in_progress' | 'pending_review' | 'completed' | 'cancelled';
export type IntegrationStatus = 'verified' | 'firmware_connected' | 'calibration_required' | 'pending_verification' | 'optional' | 'non_operational';
export type LocationSource = 'unassigned' | 'demo_anchor' | 'configured' | 'surveyed' | 'gps';

export interface User { id: number; email: string; displayName: string; role: Role; }
export interface AdminUser extends User { isActive: boolean; lastLogin: string | null; createdAt: string; }
export interface RegistrationRequest { id: number; account: string; display_name: string; requestedRole: Exclude<Role, 'administrator'>; status: 'pending' | 'approved' | 'rejected'; reviewNote: string; reviewerName: string | null; reviewedAt: string | null; setupExpiresAt: string | null; passwordSetAt: string | null; createdAt: string; }
export interface Asset { id: number; code: string; name: string; zone: string; type: string; status: Status; hardwareCode: string | null; integrationStatus: IntegrationStatus; interface: string; capabilities: string[]; mesh: string; position: Record<string, number>; latitude: number | null; longitude: number | null; locationSource: LocationSource; installationNote: string; lastSeenAt: string | null; isActive: boolean; version: number; }
export interface AssetMutation { code: string; name: string; zone: string; type: string; status: Status; hardwareCode: string | null; integrationStatus: IntegrationStatus; interface: string; capabilities: string[]; mesh: string; position: Record<string, number>; latitude: number | null; longitude: number | null; locationSource: LocationSource; installationNote: string; isActive: boolean; }
export type SpatialLayerType = 'tunnel_segment' | 'chamber' | 'manhole' | 'inspection_route' | 'risk_zone' | 'installation_point';
export type SpatialFeatureStatus = 'draft' | 'published' | 'retired';
export type SpatialSource = 'surveyed' | 'cad_import' | 'configured';
export type GeoJsonGeometry = { type: 'Point'; coordinates: [number, number] } | { type: 'LineString'; coordinates: [number, number][] } | { type: 'Polygon'; coordinates: [number, number][][] };
export interface SpatialFeature { id: number; code: string; name: string; layerType: SpatialLayerType; geometry: GeoJsonGeometry; crs: 'EPSG:4326'; source: SpatialSource; sourceReference: string; accuracyM: string | null; capturedAt: string | null; verifiedAt: string | null; status: SpatialFeatureStatus; description: string; version: number; }
export type HardwareProtocol = 'mqtt' | 'http' | 'serial' | 'manual';
export type HardwareBindingStatus = 'reserved' | 'connected' | 'inactive' | 'error';
export type HardwareConnectivity = 'online' | 'offline' | 'awaiting_data' | 'inactive' | 'error';
export interface HardwareBinding { id: number; assetCode: string; protocol: HardwareProtocol; deviceIdentifier: string; endpoint: string; expectedIntervalSeconds: number; status: HardwareBindingStatus; connectivity: HardwareConnectivity; lastHeartbeatAt: string | null; heartbeatAgeSeconds: number | null; heartbeatDueAt: string | null; version: number; }
export interface Alert { id: number; code: string; assetCode: string | null; ruleKey?: string | null; lastObservedValue?: number | null; severity: 'info' | 'warning' | 'critical'; category: string; status: AlertStatus; title: string; detail: string; openedAt: string; acknowledgedAt?: string | null; acknowledgedBy?: string | null; resolvedAt?: string | null; }
export type WorkOrderSlaStatus = 'on_track' | 'due_soon' | 'overdue' | 'closed' | 'not_set';
export interface WorkOrder { id: number; code: string; sourceAlertId?: number | null; assetCode: string; title: string; description?: string; priority: 'low' | 'normal' | 'high' | 'urgent'; status: WorkOrderStatus; assigneeName?: string | null; dueAt?: string | null; completedAt?: string | null; slaStatus?: WorkOrderSlaStatus; remainingMinutes?: number | null; createdAt: string; updatedAt: string; version: number; }
export interface Telemetry { id: number; eventId?: string | null; assetCode: string; metricKey?: string; metric: string; value: number; unit: string; quality: 'good' | 'suspect' | 'bad' | 'missing'; recordedAt: string; ingestedAt?: string; }
export interface TelemetryReading { eventId: string; assetCode: string; metricKey: string; metric: string; value: number; unit: string; quality?: Telemetry['quality']; recordedAt: string; }
export interface TelemetryIngestResult { items: Telemetry[]; created: number; duplicates: number; rules: Record<string, number>; }
export interface TelemetryQuery { assetCode?: string; metricKey?: string; quality?: Telemetry['quality']; recordedFrom?: string; recordedTo?: string; }
export interface TelemetrySummary { sampleCount: number; comparable: boolean; minimum: number | null; maximum: number | null; average: number | null; startedAt: string | null; endedAt: string | null; qualityCounts: Record<Telemetry['quality'], number>; latest: Telemetry | null; }
export interface Threshold { key: string; label: string; warning: number; alarm: number; unit: string; version: number; }
export interface TwinModelRelease { id: number; version: string; originalName: string; sha256: string; sizeBytes: number; notes: string; status: 'draft' | 'active' | 'retired'; uploadedBy: string; activatedBy: string | null; activatedAt: string | null; createdAt: string; fileUrl: string | null; }
export interface AuditEntry { id: number; actorName: string; action: string; resourceType: string; resourceId: string; detail: Record<string, unknown>; requestId: string; occurredAt: string; }
export interface Dashboard { assets: { total: number; online: number }; health: { value: number }; openAlerts: number; activeWorkOrders: number; workOrderSla?: { overdue: number; dueSoon: number }; connections?: { total: number; online: number; offline: number; awaitingData: number; error: number }; telemetry: Telemetry | null; }
