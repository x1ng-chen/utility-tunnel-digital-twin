import { Pool, type PoolClient, type QueryResultRow } from 'pg';
import { config } from './config.js';

export const db = new Pool({
  connectionString: config.DATABASE_URL,
  max: 10,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 5_000,
  // CI and local development use an internal PostgreSQL service without TLS;
  // managed production databases must present a valid certificate.
  ssl: config.NODE_ENV === 'production' ? { rejectUnauthorized: true } : false,
});

export async function query<Row extends QueryResultRow>(text: string, values: unknown[] = []) {
  return db.query<Row>(text, values);
}

export async function inTransaction<T>(work: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await db.connect();
  try {
    await client.query('BEGIN');
    const result = await work(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}
