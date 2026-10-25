"""Versioned internal retrieval, shipped with the API image; no arbitrary URLs."""
import json
from pathlib import Path

RUNBOOKS = json.loads((Path(__file__).parent / 'agent_catalog/agent-runbooks.json').read_text(encoding='utf-8'))
