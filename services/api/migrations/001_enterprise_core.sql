BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_role (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  name varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT app_role_code_format CHECK (code ~ '^[a-z][a-z_]*$')
);

CREATE TABLE permission (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(128) NOT NULL UNIQUE,
  description varchar(256) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT permission_code_format CHECK (code ~ '^[a-z][a-z0-9_.]*$')
);

CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email varchar(320) NOT NULL UNIQUE,
  display_name varchar(128) NOT NULL,
  password_hash text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT app_user_email_lowercase CHECK (email = lower(email))
);

CREATE TABLE user_role (
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES app_role(id) ON DELETE RESTRICT,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  assigned_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permission (
  role_id uuid NOT NULL REFERENCES app_role(id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE zone (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(32) NOT NULL UNIQUE,
  name varchar(128) NOT NULL,
  description text,
  sequence smallint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT zone_code_format CHECK (code ~ '^UT-Z[A-Z0-9_-]+$')
);

CREATE TABLE asset (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  name varchar(160) NOT NULL,
  zone_id uuid NOT NULL REFERENCES zone(id) ON DELETE RESTRICT,
  asset_type varchar(64) NOT NULL,
  lifecycle_status varchar(32) NOT NULL DEFAULT 'active',
  operational_status varchar(32) NOT NULL DEFAULT 'unknown',
  model_mesh_code varchar(128),
  location_x numeric(12, 3),
  location_y numeric(12, 3),
  location_z numeric(12, 3),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT asset_code_format CHECK (code ~ '^[A-Z][A-Z0-9-]*[A-Z0-9]$'),
  CONSTRAINT asset_lifecycle_status CHECK (lifecycle_status IN ('active', 'maintenance', 'retired')),
  CONSTRAINT asset_operational_status CHECK (operational_status IN ('normal', 'warning', 'alarm', 'offline', 'unknown'))
);

CREATE TABLE telemetry_reading (
  recorded_at timestamptz NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,
  metric_code varchar(96) NOT NULL,
  numeric_value numeric(18, 6),
  text_value text,
  unit varchar(32) NOT NULL,
  quality varchar(32) NOT NULL DEFAULT 'good',
  source varchar(32) NOT NULL DEFAULT 'simulator',
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (recorded_at, id),
  CONSTRAINT telemetry_value_present CHECK (numeric_value IS NOT NULL OR text_value IS NOT NULL),
  CONSTRAINT telemetry_quality CHECK (quality IN ('good', 'suspect', 'bad', 'missing')),
  CONSTRAINT telemetry_source CHECK (source IN ('simulator', 'device', 'manual'))
) PARTITION BY RANGE (recorded_at);

CREATE TABLE telemetry_reading_default PARTITION OF telemetry_reading DEFAULT;

CREATE TABLE alert (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  asset_id uuid NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,
  severity varchar(16) NOT NULL,
  category varchar(64) NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'open',
  title varchar(240) NOT NULL,
  detail text,
  opened_at timestamptz NOT NULL DEFAULT now(),
  acknowledged_at timestamptz,
  acknowledged_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  resolved_at timestamptz,
  closed_at timestamptz,
  closed_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT alert_severity CHECK (severity IN ('info', 'warning', 'critical')),
  CONSTRAINT alert_status CHECK (status IN ('open', 'acknowledged', 'resolved', 'closed')),
  CONSTRAINT alert_version_positive CHECK (version > 0)
);

CREATE TABLE alert_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id uuid NOT NULL REFERENCES alert(id) ON DELETE CASCADE,
  event_type varchar(64) NOT NULL,
  from_status varchar(32),
  to_status varchar(32),
  note text,
  actor_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work_order (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  source_alert_id uuid REFERENCES alert(id) ON DELETE SET NULL,
  asset_id uuid REFERENCES asset(id) ON DELETE SET NULL,
  title varchar(240) NOT NULL,
  description text,
  priority varchar(16) NOT NULL DEFAULT 'normal',
  status varchar(32) NOT NULL DEFAULT 'open',
  created_by uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  assigned_to uuid REFERENCES app_user(id) ON DELETE SET NULL,
  due_at timestamptz,
  completed_at timestamptz,
  reviewed_at timestamptz,
  reviewed_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT work_order_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
  CONSTRAINT work_order_status CHECK (status IN ('draft', 'open', 'assigned', 'in_progress', 'pending_review', 'completed', 'cancelled')),
  CONSTRAINT work_order_version_positive CHECK (version > 0)
);

CREATE TABLE work_order_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id uuid NOT NULL REFERENCES work_order(id) ON DELETE CASCADE,
  event_type varchar(64) NOT NULL,
  from_status varchar(32),
  to_status varchar(32),
  note text,
  actor_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE system_setting (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  setting_key varchar(128) NOT NULL UNIQUE,
  value jsonb NOT NULL,
  version integer NOT NULL DEFAULT 1,
  updated_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT system_setting_key_format CHECK (setting_key ~ '^[a-z][a-z0-9_.]*$'),
  CONSTRAINT system_setting_version_positive CHECK (version > 0)
);

CREATE TABLE report_export (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_type varchar(64) NOT NULL,
  requested_by uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(32) NOT NULL DEFAULT 'queued',
  file_name varchar(256),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CONSTRAINT report_export_status CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
);

CREATE TABLE audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  action varchar(128) NOT NULL,
  resource_type varchar(64) NOT NULL,
  resource_id uuid,
  request_id uuid,
  ip_address inet,
  before_value jsonb,
  after_value jsonb,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX asset_zone_id_idx ON asset(zone_id);
CREATE INDEX asset_operational_status_idx ON asset(operational_status);
CREATE INDEX telemetry_asset_metric_time_idx ON telemetry_reading(asset_id, metric_code, recorded_at DESC);
CREATE INDEX alert_status_opened_at_idx ON alert(status, opened_at DESC);
CREATE INDEX alert_asset_id_idx ON alert(asset_id);
CREATE INDEX alert_event_alert_time_idx ON alert_event(alert_id, occurred_at DESC);
CREATE INDEX work_order_status_due_at_idx ON work_order(status, due_at);
CREATE INDEX work_order_assigned_to_idx ON work_order(assigned_to);
CREATE INDEX work_order_event_order_time_idx ON work_order_event(work_order_id, occurred_at DESC);
CREATE INDEX audit_log_resource_time_idx ON audit_log(resource_type, resource_id, occurred_at DESC);
CREATE INDEX audit_log_actor_time_idx ON audit_log(actor_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER app_user_set_updated_at BEFORE UPDATE ON app_user FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER zone_set_updated_at BEFORE UPDATE ON zone FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER asset_set_updated_at BEFORE UPDATE ON asset FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER alert_set_updated_at BEFORE UPDATE ON alert FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER work_order_set_updated_at BEFORE UPDATE ON work_order FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER system_setting_set_updated_at BEFORE UPDATE ON system_setting FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION prevent_audit_log_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

INSERT INTO app_role (code, name) VALUES
  ('administrator', '管理员'),
  ('operator', '值班员'),
  ('maintainer', '运维员'),
  ('viewer', '查看者');

INSERT INTO permission (code, description) VALUES
  ('dashboard.read', '查看运行总览与数据洞察'),
  ('asset.read', '查看资产台账与孪生定位'),
  ('asset.write', '维护资产主数据与模型映射'),
  ('alert.read', '查看告警'),
  ('alert.acknowledge', '确认与恢复告警'),
  ('work_order.read', '查看工单'),
  ('work_order.write', '创建、派发和处置工单'),
  ('work_order.review', '复核与关闭工单'),
  ('audit.read', '查看审计记录'),
  ('setting.read', '查看系统配置'),
  ('setting.write', '修改阈值、策略与权限');

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM app_role AS role
CROSS JOIN permission
WHERE role.code = 'administrator'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM app_role AS role
JOIN permission ON permission.code IN ('dashboard.read', 'asset.read', 'alert.read', 'alert.acknowledge', 'work_order.read', 'work_order.write', 'audit.read', 'setting.read')
WHERE role.code = 'operator'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM app_role AS role
JOIN permission ON permission.code IN ('dashboard.read', 'asset.read', 'alert.read', 'work_order.read', 'work_order.write', 'audit.read')
WHERE role.code = 'maintainer'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM app_role AS role
JOIN permission ON permission.code IN ('dashboard.read', 'asset.read', 'alert.read', 'work_order.read', 'audit.read', 'setting.read')
WHERE role.code = 'viewer'
ON CONFLICT DO NOTHING;

COMMIT;
