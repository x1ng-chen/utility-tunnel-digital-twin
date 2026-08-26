import { db, inTransaction } from '../src/db.js';
import { hashPassword } from '../src/password.js';

const email = process.env.SEED_ADMIN_EMAIL?.trim().toLowerCase();
const password = process.env.SEED_ADMIN_PASSWORD;

if (!email || !password || password.length < 12) {
  throw new Error('SEED_ADMIN_EMAIL and a 12-character minimum SEED_ADMIN_PASSWORD are required.');
}

try {
  await inTransaction(async (client) => {
    const passwordHash = await hashPassword(password);
    const userResult = await client.query<{ id: string }>(
      `INSERT INTO app_user (email, display_name, password_hash)
       VALUES ($1, '系统管理员', $2)
       ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name, password_hash = EXCLUDED.password_hash
       RETURNING id`,
      [email, passwordHash],
    );
    const user = userResult.rows[0];
    if (!user) throw new Error('Could not create seed administrator.');

    await client.query(
      `INSERT INTO user_role (user_id, role_id)
       SELECT $1, id FROM app_role WHERE code = 'administrator'
       ON CONFLICT DO NOTHING`,
      [user.id],
    );

    await client.query(
      `INSERT INTO zone (code, name, sequence) VALUES
         ('UT-ZA', 'A 区入口与控制区', 1),
         ('UT-ZB', 'B 区环境与排风区', 2),
         ('UT-ZC', 'C 区燃气管线区', 3)
       ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, sequence = EXCLUDED.sequence`,
    );

    await client.query(
      `INSERT INTO asset (code, name, zone_id, asset_type, operational_status, model_mesh_code, location_x, location_y, location_z, metadata)
       SELECT item.code, item.name, zone.id, item.asset_type, item.operational_status, item.model_mesh_code, item.x, item.y, item.z, item.metadata::jsonb
       FROM (VALUES
         ('CTRL-01', '现场控制器', 'UT-ZA', 'controller', 'normal', 'MESH_CTRL_01', 2.0, 1.0, 1.5, '{"nodeId":"CTRL-01"}'),
         ('FAN-01', '送风机 #01', 'UT-ZB', 'actuator', 'normal', 'MESH_FAN_01', 12.5, 1.0, 2.2, '{"nodeId":"FAN-01"}'),
         ('SEEP-W01', '渗水监测点', 'UT-ZB', 'sensor', 'warning', 'MESH_SEEP_W01', 14.0, 0.4, 0.2, '{"nodeId":"SEEP-W01"}'),
         ('GAS-01', '甲烷监测节点', 'UT-ZC', 'sensor', 'normal', 'MESH_GAS_01', 23.0, 1.0, 1.8, '{"nodeId":"GAS-01"}')
       ) AS item(code, name, zone_code, asset_type, operational_status, model_mesh_code, x, y, z, metadata)
       JOIN zone ON zone.code = item.zone_code
       ON CONFLICT (code) DO UPDATE SET
         name = EXCLUDED.name, zone_id = EXCLUDED.zone_id, asset_type = EXCLUDED.asset_type,
         operational_status = EXCLUDED.operational_status, model_mesh_code = EXCLUDED.model_mesh_code,
         location_x = EXCLUDED.location_x, location_y = EXCLUDED.location_y, location_z = EXCLUDED.location_z,
         metadata = EXCLUDED.metadata`,
    );

    await client.query(
      `INSERT INTO telemetry_reading (recorded_at, asset_id, metric_code, numeric_value, unit, quality, source)
       SELECT now(), asset.id, item.metric_code, item.numeric_value, item.unit, 'good', 'simulator'
       FROM (VALUES
         ('FAN-01', 'fan.speed', 1248.0, 'rpm'),
         ('SEEP-W01', 'water.level', 0.68, 'ratio'),
         ('GAS-01', 'gas.methane', 0.03, '%LEL'),
         ('CTRL-01', 'controller.latency', 132.0, 'ms')
       ) AS item(asset_code, metric_code, numeric_value, unit)
       JOIN asset ON asset.code = item.asset_code
       WHERE NOT EXISTS (SELECT 1 FROM telemetry_reading)`,
    );

    await client.query(
      `INSERT INTO system_setting (setting_key, value)
       VALUES
         ('threshold.temperature', '{"label":"环境温度","unit":"°C","warning":28,"alarm":32}'::jsonb),
         ('threshold.humidity', '{"label":"环境湿度","unit":"%RH","warning":75,"alarm":85}'::jsonb),
         ('threshold.water', '{"label":"水浸趋势","unit":"秒","warning":20,"alarm":45}'::jsonb)
       ON CONFLICT (setting_key) DO NOTHING`,
    );

    await client.query(
      `INSERT INTO alert (code, asset_id, severity, category, status, title, detail)
       SELECT 'ALM-260826-003', asset.id, 'warning', 'water_ingress', 'open', '水浸趋势异常', '渗水趋势上升，等待值班员确认。'
       FROM asset
       WHERE asset.code = 'SEEP-W01'
         AND NOT EXISTS (SELECT 1 FROM alert WHERE code = 'ALM-260826-003')`,
    );
  });
  console.log('Seed data is ready.');
} finally {
  await db.end();
}
