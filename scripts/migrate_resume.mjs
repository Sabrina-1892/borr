// Resume migration with adaptive batch sizing.
// Usage: TURSO_DATABASE_URL=<url> TURSO_AUTH_TOKEN=<token> node scripts/migrate_resume.mjs

import { createClient } from "@libsql/client";

const TURSO_URL = process.env.TURSO_DATABASE_URL;
const TURSO_TOKEN = process.env.TURSO_AUTH_TOKEN;
if (!TURSO_URL) { console.error("Missing TURSO_DATABASE_URL"); process.exit(1); }

async function batchInsert(remote, statements, batchSize) {
  let inserted = 0;
  for (let i = 0; i < statements.length; i += batchSize) {
    const chunk = statements.slice(i, i + batchSize);
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const ctrl = new AbortController();
        setTimeout(() => ctrl.abort(), 120000);
        await remote.batch(chunk, { signal: ctrl.signal });
        inserted += chunk.length;
        break;
      } catch (e) {
        if (attempt === 2) {
          if (batchSize > 100) return { inserted, retry: true };
          // skip this chunk on last attempt
          break;
        }
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  }
  return { inserted, retry: false };
}

async function main() {
  const local = createClient({ url: "file:borr.db" });
  const remote = createClient({ url: TURSO_URL, authToken: TURSO_TOKEN });

  const maxResult = await remote.execute("SELECT COALESCE(MAX(rowid), 0) AS n FROM papers");
  const lastRowid = Number(maxResult.rows[0].n);
  console.log(`Last rowid: ${lastRowid}`);

  const totalResult = await local.execute("SELECT COUNT(*) AS n FROM papers WHERE verified = 1");
  const total = Number(totalResult.rows[0].n);
  console.log(`Total: ${total}`);

  let batchSize = 2000;
  let currentRowid = lastRowid;
  let inserted = 0;
  let errors = 0;
  let startTime = Date.now();

  while (true) {
    const rows = await local.execute({
      sql: `SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?`,
      args: [currentRowid, batchSize * 2],
    });

    if (rows.rows.length === 0) break;

    const statements = [];
    for (const row of rows.rows) {
      const searchText = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
      statements.push({
        sql: `INSERT OR IGNORE INTO papers (
          id, openalex_id, title, authors, abstract, doi, url, journal, year,
          institution, fields, paper_type, access_type, source, verified,
          citation_count, created_at, updated_at, external_ids, sources,
          last_harvested_at, authors_text, institution_text, search_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        args: [
          row.id, row.openalex_id, row.title, row.authors, row.abstract,
          row.doi, row.url, row.journal, row.year, row.institution,
          row.fields, row.paper_type, row.access_type, row.source,
          row.verified, row.citation_count, row.created_at, row.updated_at,
          row.external_ids || "{}", row.sources || "[]", row.last_harvested_at,
          row.authors_text, row.institution_text, searchText,
        ],
      });
      currentRowid = Number(row.rowid);
    }

    // Try insert with adaptive batch sizing
    const result = await batchInsert(remote, statements, batchSize);
    inserted += result.inserted;
    if (result.retry && batchSize > 100) {
      batchSize = Math.floor(batchSize / 2);
      console.log(`\nReducing batch to ${batchSize}...`);
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
    const rate = (inserted / Math.max(1, (Date.now() - startTime) / 1000)).toFixed(0);
    const pct = Math.min(100, Math.round(((lastRowid + inserted) / total) * 100));
    process.stdout.write(`\r  ${inserted} new (${lastRowid + inserted} total) — ${pct}% (${rate} rows/s, ${elapsed}s)`);
  }

  console.log(`\nDone!`);
  const final = await remote.execute("SELECT COUNT(*) AS n FROM papers");
  console.log(`Turso total: ${Number(final.rows[0].n).toLocaleString()}`);
}

main().catch(e => { console.error("\nFatal:", e.message); process.exit(1); });
