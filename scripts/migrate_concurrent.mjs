// Concurrent individual inserts using @libsql/client execute() (batch is broken)
import { createClient } from "@libsql/client";

const CONCUR = 15;

async function main() {
  const TURSO_URL = process.env.TURSO_DATABASE_URL;
  const TURSO_TOKEN = process.env.TURSO_AUTH_TOKEN;
  if (!TURSO_URL || !TURSO_TOKEN) { console.error("Missing env"); process.exit(1); }

  const local = createClient({ url: "file:borr.db" });
  const remote = createClient({ url: TURSO_URL, authToken: TURSO_TOKEN });

  const max = await remote.execute("SELECT COALESCE(MAX(rowid),0) AS n FROM papers");
  const lastRowid = Number(max.rows[0].n);
  console.error(`Last rowid: ${lastRowid}`);

  const cnt = await local.execute(
    "SELECT COUNT(*) AS n FROM papers WHERE verified = 1 AND rowid > ?", [lastRowid]);
  const total = Number(cnt.rows[0].n);
  console.error(`Remaining: ${total}`);

  if (total === 0) { console.error("Nothing to do"); process.exit(0); }

  let done = 0, errors = 0, currentRowid = lastRowid;
  const t0 = Date.now();

  async function insertOne(row) {
    const s = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
    try {
      await remote.execute({
        sql: `INSERT OR IGNORE INTO papers(
          id, openalex_id, title, authors, abstract, doi, url, journal, year,
          institution, fields, paper_type, access_type, source, verified,
          citation_count, created_at, updated_at, external_ids, sources,
          last_harvested_at, authors_text, institution_text, search_text
        )VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
        args: [
          row.id, row.openalex_id, row.title, row.authors, row.abstract,
          row.doi, row.url, row.journal, row.year, row.institution,
          row.fields, row.paper_type, row.access_type, row.source,
          row.verified, row.citation_count, row.created_at, row.updated_at,
          row.external_ids || "{}", row.sources || "[]", row.last_harvested_at,
          row.authors_text, row.institution_text, s,
        ],
      });
      return true;
    } catch {
      return false;
    }
  }

  while (true) {
    const rows = await local.execute({
      sql: "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT 500",
      args: [currentRowid],
    });
    if (rows.rows.length === 0) break;

    // Execute CONCUR inserts at a time
    for (let i = 0; i < rows.rows.length; i += CONCUR) {
      const chunk = rows.rows.slice(i, i + CONCUR);
      const results = await Promise.all(chunk.map(r => insertOne(r)));
      currentRowid = Number(chunk[chunk.length - 1].rowid);
      done += results.filter(Boolean).length;
      errors += results.filter(r => !r).length;

      const elapsed = (Date.now() - t0) / 1000;
      const rate = done / elapsed;
      process.stdout.write(`\r  ${done}/${total} (${errors} err) — ${rate.toFixed(0)} rows/s, ${elapsed.toFixed(0)}s`);
    }
  }

  console.error(`\nDone in ${(Date.now()-t0)/1000|0}s`);
  const f = await remote.execute("SELECT COUNT(*) AS n FROM papers");
  console.error(`Turso total: ${Number(f.rows[0].n).toLocaleString()}`);
  process.exit(errors > 0 ? 1 : 0);
}

main().catch(e => { console.error("\nFatal:", e.message); process.exit(1); });
