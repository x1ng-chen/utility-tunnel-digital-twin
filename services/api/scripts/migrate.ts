import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { db } from '../src/db.js';

const migrationsDirectory = fileURLToPath(new URL('../migrations/', import.meta.url));

try {
  await db.query(`
    CREATE TABLE IF NOT EXISTS schema_migration (
      version varchar(255) PRIMARY KEY,
      applied_at timestamptz NOT NULL DEFAULT now()
    )
  `);

  const files = (await readdir(migrationsDirectory))
    .filter((file) => file.endsWith('.sql'))
    .sort((left, right) => left.localeCompare(right));

  for (const file of files) {
    const applied = await db.query<{ version: string }>('SELECT version FROM schema_migration WHERE version = $1', [file]);
    if (applied.rowCount) continue;
    const sql = await readFile(join(migrationsDirectory, file), 'utf8');
    await db.query(sql);
    await db.query('INSERT INTO schema_migration (version) VALUES ($1)', [file]);
    console.log(`Applied ${file}`);
  }
} finally {
  await db.end();
}
