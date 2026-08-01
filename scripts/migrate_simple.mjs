// Simple reliable migration using @libsql/client batch (proven to work)
import { createClient } from "@libsql/client";

async function main() {
  const TURSO_URL = process.env.TURSO_DATABASE_URL;
  const TURSO_TOKEN = process.env.TURSO_AUTH_TOKEN;
  if (!TURSO_URL || !TURSO_TOKEN) {
    console.error("Need TURSO_DATABASE_URL and TURSO_AUTH_TOKEN");
    process.exit(1);
  }

  const local = createClient({ url: "file:borr.db" });
  const remote = createClient({ url: TURSO_URL, authToken: TURSO_TOKEN });

  const max = await remote.execute("SELECT COALESCE(MAX(rowid), 0) AS n FROM papers");
  const lastRowid = Number(max.rows[0].n);
  console.log(`Last rowid: ${lastRowid}`);

  const cnt = await local.execute(
    "SELECT COUNT(*) AS n FROM papers WHERE verified = 1 AND rowid > ?", [lastRowid]);
  const remaining = Number(cnt.rows[0].n);
  console.log(`Remaining: ${remaining}`);

  const BATCH = 500;
  let done = 0, errors = 0, currentRowid = lastRowid;
  const start = Date.now();

  while (true) {
    const rows = await local.execute({
      sql: "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?",
      args: [currentRowid, BATCH * 2],
    });
    if (rows.rows.length === 0) break;

    // Build batch statements
    const stmts = [];
    for (const row of rows.rows) {
      const s = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
      stmts.push({
        sql: `INSERT OR IGNORE INTO papers(
            id,openalex_id,title,authors,abstract,doi,url,journal,year,
            institution,fields,paper_type,access_type,source,verified,
            citation_count,created_at,updated_at,external_ids,sources,
            last_harvested_at,authors_text,institution_text,search_text
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
      currentRowid = Number(row.rowid);
    }

    // Insert in small batches (500 proved reliable)
    for (let i = 0; i < stmts.length; i += BATCH) {
      const chunk = stmts.slice(i, i + BATCH);
      try {
        await remote.batch(chunk);
        done += chunk.length;
      } catch {
        errors += chunk.length;
      }
    }

    const elapsed = ((Date.now() - start) / 1000).toFixed(0);
    const rate = (done / Math.max(1, (Date.now() - start) / 1000)).toFixed(0);
    process.stdout.write(`\r  ${done}/${remaining} (${errors} err) — ${rate} rows/s, ${elapsed}s`);
  }

  console.log(`\nDone in ${((Date.now()-start)/1000).toFixed(0)}s`);
  const f = await remote.execute("SELECT COUNT(*) AS n FROM papers");
  console.log(`Turso total: ${Number(f.rows[0].n).toLocaleString()}`);
}

main().catch(e => { console.error("\nFatal:", e.message); process.exit(1); });
