"""Download only pinned, non-executable model assets into an external runtime.

This explicit preparation command is never imported by Django/CI. It does not
install packages or call a paid API. Interrupted downloads resume with Range.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / 'services' / 'decision-router' / 'model.lock.json'
FILES = ('LICENSE', 'config.json', 'generation_config.json', 'chat_template.jinja',
         'merges.txt', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'model.safetensors')


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def download(url, target, expected_bytes=None, expected_hash=None):
    if target.is_file() and (expected_bytes is None or target.stat().st_size == expected_bytes):
        found = sha256(target)
        if expected_hash is None or found == expected_hash:
            return {'bytes': target.stat().st_size, 'sha256': found}
        raise RuntimeError(f'Existing file hash mismatch: {target.name}; preserve it and inspect manually.')
    temporary = target.with_name(target.name + '.partial')
    for attempt in range(5):
        offset = temporary.stat().st_size if temporary.exists() else 0
        request = Request(url, headers={'User-Agent': 'utility-tunnel-model-preparer/1',
                                        **({'Range': f'bytes={offset}-'} if offset else {})})
        try:
            with urlopen(request, timeout=45) as response:
                append = offset > 0 and response.status == 206
                with temporary.open('ab' if append else 'wb') as output:
                    last_report = time.monotonic()
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        output.write(block)
                        if time.monotonic() - last_report >= 15:
                            print(json.dumps({'file': target.name, 'downloadedBytes': output.tell()}), flush=True)
                            last_report = time.monotonic()
            if expected_bytes is not None and temporary.stat().st_size != expected_bytes:
                raise OSError('incomplete_download')
            found = sha256(temporary)
            if expected_hash is not None and found != expected_hash:
                raise RuntimeError(f'Download hash mismatch: {target.name}; partial file preserved.')
            temporary.replace(target)
            return {'bytes': target.stat().st_size, 'sha256': found}
        except (TimeoutError, OSError, HTTPError, URLError) as exc:
            print(json.dumps({'file': target.name, 'retry': attempt + 1, 'errorType': type(exc).__name__}), flush=True)
            if attempt == 4:
                raise RuntimeError(f'Download incomplete: {target.name}; resumable partial preserved.') from None
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError('unreachable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--sources-only', action='store_true')
    args = parser.parse_args()
    lock = json.loads(LOCK_PATH.read_text(encoding='utf-8'))
    root = args.runtime_root.resolve()
    if root == REPO_ROOT or REPO_ROOT in root.parents:
        parser.error('Keep the model/runtime outside the Git checkout.')
    root.mkdir(parents=True, exist_ok=True)
    source_dir = root / 'sources'
    source_dir.mkdir(exist_ok=True)
    archive = source_dir / ('anyjev-' + lock['anyjevCommit'] + '.zip')
    record = download('https://codeload.github.com/nokia-applied-research/AnyJev/zip/' + lock['anyjevCommit'], archive,
                      expected_hash=lock['anyjevArchiveSha256'])
    source_manifest = {'repository': lock['anyjevRepository'], 'commit': lock['anyjevCommit'],
                       'file': archive.name, **record}
    (source_dir / 'source-manifest.json').write_text(json.dumps(source_manifest, indent=2), encoding='utf-8')
    print(json.dumps({'source': source_manifest}), flush=True)
    if args.sources_only:
        return 0
    target_dir = root / 'models' / 'Tacit-1.7B' / lock['modelRevision']
    target_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for name in FILES:
        weights = lock['modelWeights'] if name == lock['modelWeights']['name'] else {}
        url = f"https://huggingface.co/{lock['model']}/resolve/{lock['modelRevision']}/{name}"
        records[name] = download(url, target_dir / name, weights.get('bytes'), weights.get('sha256'))
        print(json.dumps({'verified': name, **records[name]}), flush=True)
    manifest = {'model': lock['model'], 'revision': lock['modelRevision'], 'files': records,
                'remotePythonExecuted': False, 'weightsLicense': lock['license']}
    (target_dir / 'model-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'prepared', 'modelDir': str(target_dir)}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
