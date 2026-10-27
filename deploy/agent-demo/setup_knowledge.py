"""Explicit model download; inference itself remains local-only."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download,model_info
ROOT=Path(__file__).resolve().parents[2]
target=ROOT/'.agent-knowledge/bge-small-zh-v1.5'
revision=model_info('BAAI/bge-small-zh-v1.5').sha
snapshot_download('BAAI/bge-small-zh-v1.5',revision=revision,local_dir=target,
    allow_patterns=['*.json','*.safetensors','*.txt','1_Pooling/*'])
files={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and '.cache' not in p.parts}
(target.parent/'model-manifest.json').write_text(json.dumps({'model':'BAAI/bge-small-zh-v1.5','revision':revision,'sha256':files},indent=2),encoding='utf-8')
print('Local model prepared:',revision)
