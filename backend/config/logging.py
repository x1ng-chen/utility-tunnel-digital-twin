import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter suitable for ECS/cloud log ingestion."""

    def format(self, record):
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key in ('request_id', 'method', 'path', 'status_code', 'duration_ms'):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
