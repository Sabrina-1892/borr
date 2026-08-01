// Migrate using Turso REST API (v2/pipeline) - most reliable method
// Usage: TURSO_URL=<url> TURSO_TOKEN=<token> node scripts/migrate_rest.mjs

const TURSO_URL = process.env.TURSO_URL || "https://borr-borrbd.aws-ap-south-1.turso.io";
const TURSO_TOKEN = process.env.TURSO_TOKEN;

if (!TURSO_TOKEN) { console.error("Missing TURSO_TOKEN"); process.exit(1); }

async function query(sql) {
  const res = await fetch(`${TURSO_URL}/v2/pipeline`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TURSO_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      requests: [{ type: "execute", stmt: { sql } }],
    }),
  });
  return res.json();
}

async function insertRow(row) {
  const search = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
  const sql = `INSERT OR IGNORE INTO papers VALUES(
    ${sq(row.id)},${sq(row.openalex_id)},${sq(row.title)},${sq(row.authors)},
    ${sq(row.abstract)},${sq(row.doi)},${sq(row.url)},${sq(row.journal)},
    ${row.year ?? "NULL"},${sq(row.institution)},${sq(row.fields)},
    ${sq(row.paper_type)},${sq(row.access_type)},${sq(row.source)},${row.verified},
    ${row.citation_count ?? "NULL"},${sq(row.created_at)},${sq(row.updated_at)},
    ${sq(row.external_ids || "{}")},${sq(row.sources || "[]")},
    ${sq(row.last_harvested_at)},${sq(row.authors_text)},${sq(row.institution_text)},
    ${sq(search)}
  )`;
  return query(sql);
}

function sq(v) {
  if (v == null) return "NULL";
  if (typeof v === "number") return String(v);
  return "'" + String(v).replace(/'/g, "''") + "'";
}

async function main() {
  // Import better-sqlite3 dynamically
  const Database = (await import("better-sqlite3")).default;
  const db = new Database("borr.db", { readonly: true });

  // Get max rowid from Turso
  const maxRes = await query("SELECT COALESCE(MAX(rowid), 0) AS n FROM papers");
  let lastRowid = Number(maxRes.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0);
  console.log(`Last Turso rowid: ${lastRowid}`);

  const total = db.prepare("SELECT COUNT(*) FROM papers WHERE verified = 1").pluck().get();
  const remaining = db.prepare("SELECT COUNT(*) FROM papers WHERE verified = 1 AND rowid > ?").pluck().get(lastRowid);
  console.log(`Total: ${total}, Remaining: ${remaining}`);

  const BATCH = 20; // concurrent REST calls
  let done = 0;
  let errors = 0;
  const start = Date.now();

  while (true) {
    const rows = db.prepare(
      "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?"
    ).all(lastRowid, 500);

    if (rows.length === 0) break;

    // Send BATCH requests concurrently
    for (let i = 0; i < rows.length; i += BATCH) {
      const chunk = rows.slice(i, i + BATCH);
      const results = await Promise.allSettled(chunk.map(r => insertRow(r)));
      for (const res of results) {
        if (res.status === "fulfilled") done++;
        else errors++;
      }
      lastRowid = chunk[chunk.length - 1].rowid;

      const elapsed = ((Date.now() - start) / 1000).toFixed(0);
      const rate = (done / Math.max(1, (Date.now() - start) / 1000)).toFixed(0);
      process.stdout.write(`\r  ${done}/${remaining} (${errors} err) — ${rate} rows/s, ${elapsed}s`);
    }
  }

  console.log(`\nDone! ${done} rows in ${((Date.now()-start)/1000).toFixed(0)}s`);

  const finalRes = await query("SELECT COUNT(*) AS n FROM papers");
  const final = Number(finalRes.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0);
  console.log(`Turso total: ${final.toLocaleString()}`);
}

main().catch(e => { console.error(e.message); process.exit(1); });
