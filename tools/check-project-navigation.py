"""Validate current local navigation; frozen historical documents are out of scope."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    'README.md', 'CONTRIBUTING.md', 'CHANGELOG.md', 'docs/README.md',
    'docs/PROJECT_STATUS.md', 'docs/releases/2026-10-31/README.md',
    'releases/firmware/2026-10-31/README.md', 'firmware/README.md', 'services/README.md',
]

errors = []
checked = 0
for relative in PAGES:
    page = ROOT / relative
    text = re.sub(r'```.*?```', '', page.read_text(encoding='utf-8'), flags=re.S)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', text):
        target = match[1].strip().strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith('#'):
            continue
        destination = (page.parent / unquote(parsed.path)).resolve()
        checked += 1
        if not destination.is_relative_to(ROOT) or not destination.exists():
            errors.append(f'{relative}: missing or out-of-repository target {target}')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Current navigation passed: {len(PAGES)} pages, {checked} local links.')
