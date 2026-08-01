// Fast migration via REST API with concurrency.
// Uses @libsql/client for local reads, fetch() for remote writes.
import { createClient } from "@libsql/client";

const REMOTE_URL = "https://borr-borrbd.aws-ap-south-1.turso.io";
const TOKEN = process.env.TURSO_AUTH_TOKEN;
const CONCURRENCY = 50;

if (!TOKEN) { console.error("Missing TURSO_AUTH_TOKEN"); process.exit(1); }

async function restQuery(sql) {
  const res = await fetch(`${REMOTE_URL}/v2/pipeline`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ requests: [{ type: "execute", stmt: { sql } }] }),
  });
  return res.json();
}

function sq(v) {
  if (v == null) return "NULL";
  if (typeof v === "number") return String(v);
  return "'" + String(v).replace(/'/g, "''") + "'";
}

function buildInsert(row) {
  const search = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
  return `INSERT OR IGNORE INTO papers VALUES(
    ${sq(row.id)},${sq(row.openalex_id)},${sq(row.title)},${sq(row.authors)},
    ${sq(row.abstract)},${sq(row.doi)},${sq(row.url)},${sq(row.journal)},
    ${row.year ?? "NULL"},${sq(row.institution)},${sq(row.fields)},
    ${sq(row.paper_type)},${sq(row.access_type)},${sq(row.source)},${row.verified},
    ${row.citation_count ?? "NULL"},${sq(row.created_at)},${sq(row.updated_at)},
    ${sq(row.external_ids || "{}")},${sq(row.sources || "[]")},
    ${sq(row.last_harvested_at)},${sq(row.authors_text)},${sq(row.institution_text)},
    ${sq(search)}
  )`;
}

async function main() {
  const local = createClient({ url: "file:borr.db" });

  // Get current max rowid from remote
  const maxRes = await restQuery("SELECT COALESCE(MAX(rowid), 0) AS n FROM papers");
  const lastRowid = Number(maxRes.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0);
  console.log(`Last rowid in Turso: ${lastRowid}`);

  const total = await local.execute("SELECT COUNT(*) AS n FROM papers WHERE verified = 1 AND rowid > ?", [lastRowid]);
  const remaining = Number(total.rows[0].n);
  console.log(`Remaining: ${remaining}`);

  let done = 0;
  let errors = 0;
  let currentRowid = lastRowid;
  const start = Date.now();

  while (true) {
    const rows = await local.execute({
      sql: `SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?`,
      args: [currentRowid, 2000],
    });

    if (rows.rows.length === 0) break;

    // Process in concurrent batches
    for (let i = 0; i < rows.rows.length; i += CONCURRENCY) {
      const chunk = rows.rows.slice(i, i + CONCURRENCY);
      const inserts = chunk.map(row =>
        restQuery(buildInsert(row))
          .then(r => {
            const ok = r.results?.[0]?.type === "ok";
            if (!ok) errors++;
            return ok;
          })
          .catch(() => { errors++; return false; })
      );
      const results = await Promise.all(inserts);
      done += results.filter(Boolean).length;
      currentRowid = chunk[chunk.length - 1].rowid;

      const elapsed = ((Date.now() - start) / 1000).toFixed(0);
      const rate = (done / Math.max(1, (Date.now() - start) / 1000)).toFixed(0);
      process.stdout.write(`\r  ${done}/${remaining} (${errors} err) — ${rate} rows/s, ${elapsed}s`);
    }
  }

  console.log(`\nDone in ${((Date.now()-start)/1000).toFixed(0)}s`);

  const finalRes = await restQuery("SELECT COUNT(*) AS n FROM papers");
  const final = Number(finalRes.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0);
  console.log(`Turso total: ${final.toLocaleString()}`);
}

main().catch(e => { console.error("\nFatal:", e.message); process.exit(1); });
