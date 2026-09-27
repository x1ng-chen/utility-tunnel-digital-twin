import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export class Outbox {
  constructor(path = ':memory:', maxItems = 43200) {
    this.path = path;
    this.maxItems = maxItems;
    if (path !== ':memory:') mkdirSync(dirname(resolve(path)), { recursive: true });
    this.db = new DatabaseSync(path);
    if (path !== ':memory:') this.db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS django_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_json TEXT NOT NULL,
        received_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS django_dead_letter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id INTEGER,
        batch_json TEXT NOT NULL,
        received_at TEXT NOT NULL,
        reason TEXT NOT NULL,
        dead_lettered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);
    this.insert = this.db.prepare('INSERT INTO django_outbox (batch_json, received_at) VALUES (?, ?)');
    this.head = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox ORDER BY id LIMIT 1');
    this.headExcept = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox WHERE id != ? ORDER BY id LIMIT 1');
    this.remove = this.db.prepare('DELETE FROM django_outbox WHERE id = ?');
    this.updateBatch = this.db.prepare('UPDATE django_outbox SET batch_json = ? WHERE id = ?');
    this.size = this.db.prepare('SELECT COUNT(*) AS count FROM django_outbox');
    this.deadLetterSize = this.db.prepare('SELECT COUNT(*) AS count FROM django_dead_letter');
    this.insertDeadLetter = this.db.prepare('INSERT INTO django_dead_letter (original_id, batch_json, received_at, reason) VALUES (?, ?, ?, ?)');
    this.deadLetterRows = this.db.prepare('SELECT id, original_id, batch_json, received_at, reason, dead_lettered_at FROM django_dead_letter ORDER BY id DESC LIMIT ?');
  }

  count() {
    return Number(this.size.get().count);
  }

  peek() {
    const row = this.head.get();
    return row ? { id: row.id, batch: JSON.parse(row.batch_json), receivedAt: row.received_at } : null;
  }

  deadLetterCount() {
    return Number(this.deadLetterSize.get().count);
  }

  listDeadLetters(limit = 100) {
    return this.deadLetterRows.all(Math.max(1, Math.min(Number(limit) || 100, 1000))).map((row) => ({
      id: row.id,
      originalId: row.original_id,
      batch: JSON.parse(row.batch_json),
      receivedAt: row.received_at,
      reason: row.reason,
      deadLetteredAt: row.dead_lettered_at,
    }));
  }

  deadLetter(id, reason) {
    const row = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox WHERE id = ?').get(id);
    if (!row) return null;
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.insertDeadLetter.run(row.id, row.batch_json, row.received_at, String(reason).slice(0, 2000));
      this.remove.run(row.id);
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
    return { id: row.id, batch: JSON.parse(row.batch_json), receivedAt: row.received_at };
  }

  rejectReadings(id, rejectedCodes, reason) {
    const row = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox WHERE id = ?').get(id);
    if (!row) return { rejected: 0, retained: 0 };
    const batch = JSON.parse(row.batch_json);
    const rejected = batch.readings.filter((reading) => rejectedCodes.has(reading.assetCode));
    const retained = batch.readings.filter((reading) => !rejectedCodes.has(reading.assetCode));
    if (!rejected.length) return { rejected: 0, retained: batch.readings.length };
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.insertDeadLetter.run(row.id, JSON.stringify({ readings: rejected }), row.received_at, String(reason).slice(0, 2000));
      if (retained.length) this.updateBatch.run(JSON.stringify({ readings: retained }), row.id);
      else this.remove.run(row.id);
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
    return { rejected: rejected.length, retained: retained.length };
  }

  enqueue(batch, receivedAt, protectedId = null) {
    this.insert.run(JSON.stringify(batch), receivedAt);
    const dropped = [];
    while (this.count() > this.maxItems) {
      const row = protectedId == null ? this.head.get() : this.headExcept.get(protectedId);
      const item = row ? { id: row.id, batch: JSON.parse(row.batch_json), receivedAt: row.received_at } : null;
      if (!item) break;
      this.deadLetter(item.id, 'queue_overflow');
      dropped.push(item);
    }
    return dropped;
  }

  delete(id) {
    this.remove.run(id);
  }

  close() {
    this.db.close();
  }
}
