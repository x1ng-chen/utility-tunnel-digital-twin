-- The web client presents the operational maintainer as the "operator" role.
-- Keep the legacy database role aligned with the same alert acknowledgement capability.
INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM app_role AS role
JOIN permission ON permission.code = 'alert.acknowledge'
WHERE role.code = 'maintainer'
ON CONFLICT DO NOTHING;
