import { execFileSync } from 'node:child_process';
import { readFileSync, statSync } from 'node:fs';
import { extname, basename } from 'node:path';

// Include tracked and untracked (but non-ignored) worktree files so the check
// also protects newly-created migrations and scripts before the first commit.
const tracked = execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], { encoding: 'utf8' })
  .split('\0')
  .filter(Boolean);

const textExtensions = new Set([
  '.c', '.cc', '.cpp', '.css', '.env', '.html', '.js', '.json', '.mjs', '.md',
  '.py', '.ps1', '.s', '.sql', '.ts', '.tsx', '.vue', '.yml', '.yaml', '.toml',
]);
const failures = [];
let scanned = 0;

function isExampleEnv(file) {
  return /(^|[.])env[.]example$/i.test(basename(file));
}

function isCommittedSecretConfig(file) {
  const name = basename(file).toLowerCase();
  return /^secrets[.]/.test(name) && !/^secrets[.]example[.]/.test(name);
}

for (const file of tracked) {
  const lower = file.toLowerCase();
  if (lower.endsWith('.env') && !isExampleEnv(file)) {
    failures.push(`${file}: environment files must not be committed`);
    continue;
  }
  if (isCommittedSecretConfig(file)) {
    failures.push(`${file}: local secret configuration must not be committed`);
    continue;
  }
  let size;
  try {
    size = statSync(file).size;
  } catch {
    failures.push(`${file}: tracked file is not readable`);
    continue;
  }
  if (size > 5 * 1024 * 1024 || !textExtensions.has(extname(file).toLowerCase())) continue;
  const text = readFileSync(file, 'utf8');
  scanned += 1;
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(text)) {
    failures.push(`${file}: private key material detected`);
  }
  if (/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/.test(text)) {
    failures.push(`${file}: AWS access key pattern detected`);
  }
  if (/gh[pousr]_[A-Za-z0-9_]{30,}/.test(text)) {
    failures.push(`${file}: GitHub token pattern detected`);
  }
  if (basename(file) === 'package-lock.json' && /registry[.]npmmirror[.]com/i.test(text)) {
    failures.push(`${file}: dependency tarballs must resolve from the canonical npm registry`);
  }
  if (lower.startsWith('.github/workflows/')) {
    for (const match of text.matchAll(/\buses:\s*["']?([^@\s"']+)@([^\s#"']+)/g)) {
      if (!/^[0-9a-f]{40}$/i.test(match[2])) {
        failures.push(`${file}: third-party action ${match[1]} must be pinned to a full commit SHA`);
      }
    }
  }
}

if (failures.length) {
  console.error(`Quality scan failed (${failures.length} finding${failures.length === 1 ? '' : 's'}):`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`Quality scan passed: ${scanned} text files checked, no committed secret material found.`);
}
