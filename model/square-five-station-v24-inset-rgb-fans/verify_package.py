"""Verify actual delivery bytes; fail if Git LFS pointers replace binary assets."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'delivery-manifest.json').read_text(encoding='utf-8'))
for item in manifest['files']:
    relative=Path(item['path']);assert not relative.is_absolute() and '..' not in relative.parts
    data=(ROOT/relative).read_bytes()
    assert not data.startswith(b'version https://git-lfs.github.com/spec/v1'),f'Missing LFS object: {relative}'
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],f'Package changed: {relative}'
print(json.dumps({'status':'PASS','verifiedFiles':len(manifest['files']),'revision':manifest['revision']}))
