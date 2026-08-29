import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export class Outbox {
  constructor(path = ':memory:', maxItems = 150) {
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
    `);
    this.insert = this.db.prepare('INSERT INTO django_outbox (batch_json, received_at) VALUES (?, ?)');
    this.head = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox ORDER BY id LIMIT 1');
    this.headExcept = this.db.prepare('SELECT id, batch_json, received_at FROM django_outbox WHERE id != ? ORDER BY id LIMIT 1');
    this.remove = this.db.prepare('DELETE FROM django_outbox WHERE id = ?');
    this.size = this.db.prepare('SELECT COUNT(*) AS count FROM django_outbox');
  }

  count() {
    return Number(this.size.get().count);
  }

  peek() {
    const row = this.head.get();
    return row ? { id: row.id, batch: JSON.parse(row.batch_json), receivedAt: row.received_at } : null;
  }

  enqueue(batch, receivedAt, protectedId = null) {
    this.insert.run(JSON.stringify(batch), receivedAt);
    const dropped = [];
    while (this.count() > this.maxItems) {
      const row = protectedId == null ? this.head.get() : this.headExcept.get(protectedId);
      const item = row ? { id: row.id, batch: JSON.parse(row.batch_json), receivedAt: row.received_at } : null;
      if (!item) break;
      this.remove.run(item.id);
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
