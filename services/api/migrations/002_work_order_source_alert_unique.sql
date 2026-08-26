CREATE UNIQUE INDEX IF NOT EXISTS work_order_source_alert_unique_idx
  ON work_order (source_alert_id)
  WHERE source_alert_id IS NOT NULL;
