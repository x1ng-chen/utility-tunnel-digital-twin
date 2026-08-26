import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const directory = fileURLToPath(new URL('../migrations/', import.meta.url));
const files = (await readdir(directory)).filter((file) => file.endsWith('.sql')).sort((left, right) => left.localeCompare(right));
const expectedNames = new Set();

for (const file of files) {
  if (!/^\d{3,}_[a-z0-9_]+\.sql$/.test(file)) throw new Error(`Invalid migration file name: ${file}`);
  if (expectedNames.has(file)) throw new Error(`Duplicate migration file name: ${file}`);
  expectedNames.add(file);
  const content = await readFile(new URL(`../migrations/${file}`, import.meta.url), 'utf8');
  if (/\bDROP\s+(TABLE|SCHEMA|DATABASE)\b|\bTRUNCATE\b|\bDELETE\s+FROM\b/i.test(content)) {
    throw new Error(`Destructive statement detected in migration ${file}. Use an explicitly reviewed archival migration instead.`);
  }
}

if (!files.length) throw new Error('No SQL migrations found.');
console.log(`Migration safety check passed for ${files.length} migration(s).`);
