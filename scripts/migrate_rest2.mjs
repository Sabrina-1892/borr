// Fast migration using Turso REST API with column-named inserts.
import { createClient } from "@libsql/client";
import https from "https";

const REMOTE = "https://borr-borrbd.aws-ap-south-1.turso.io";
const TOKEN = process.env.TURSO_AUTH_TOKEN;
const CONCUR = 20;

if (!TOKEN) { console.error("Missing TURSO_AUTH_TOKEN"); process.exit(1); }

function restQuery(sql) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ requests: [{ type: "execute", stmt: { sql } }] });
    const req = https.request(REMOTE + "/v2/pipeline", {
      method: "POST",
      headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" },
    }, res => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => resolve(JSON.parse(data)));
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function sq(v) {
  if (v == null) return "NULL";
  if (typeof v === "number") return String(v);
  return "'" + String(v).replace(/'/g, "''") + "'";
}

function insertSQL(row) {
  const s = [row.title, row.abstract || "", row.authors_text || ""].join(" ").toLowerCase();
  return `INSERT OR IGNORE INTO papers(
    id,openalex_id,title,authors,abstract,doi,url,journal,year,
    institution,fields,paper_type,access_type,source,verified,
    citation_count,created_at,updated_at,external_ids,sources,
    last_harvested_at,authors_text,institution_text,search_text
  )VALUES(
    ${sq(row.id)},${sq(row.openalex_id)},${sq(row.title)},${sq(row.authors)},
    ${sq(row.abstract)},${sq(row.doi)},${sq(row.url)},${sq(row.journal)},
    ${row.year ?? "NULL"},${sq(row.institution)},${sq(row.fields)},
    ${sq(row.paper_type)},${sq(row.access_type)},${sq(row.source)},${row.verified},
    ${row.citation_count ?? "NULL"},${sq(row.created_at)},${sq(row.updated_at)},
    ${sq(row.external_ids || "{}")},${sq(row.sources || "[]")},
    ${sq(row.last_harvested_at)},${sq(row.authors_text)},${sq(row.institution_text)},
    ${sq(s)}
  )`;
}

async function main() {
  const local = createClient({ url: "file:borr.db" });

  // Resume from current max rowid
  const maxRes = await restQuery("SELECT COALESCE(MAX(rowid), 0) AS n FROM papers");
  const lastRowid = Number(maxRes.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0);
  console.log("Last rowid:", lastRowid);

  const count = await local.execute(
    "SELECT COUNT(*) AS n FROM papers WHERE verified = 1 AND rowid > ?", [lastRowid]);
  const remaining = Number(count.rows[0].n);
  console.log("Remaining:", remaining);

  let done = 0, errors = 0;
  let currentRowid = lastRowid;
  const start = Date.now();

  while (true) {
    const rows = await local.execute({
      sql: "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?",
      args: [currentRowid, 1000],
    });
    if (rows.rows.length === 0) break;

    // Process in concurrent batches
    for (let i = 0; i < rows.rows.length; i += CONCUR) {
      const chunk = rows.rows.slice(i, i + CONCUR);
      const results = await Promise.allSettled(
        chunk.map(row => restQuery(insertSQL(row)))
      );
      for (const r of results) {
        if (r.status === "fulfilled" && r.value.results?.[0]?.type === "ok") done++;
        else errors++;
      }
      currentRowid = chunk[chunk.length - 1].rowid;
    }

    const elapsed = ((Date.now() - start) / 1000).toFixed(0);
    const rate = (done / Math.max(1, (Date.now() - start) / 1000)).toFixed(0);
    process.stdout.write(`\r  ${done}/${remaining} (${errors} err) — ${rate} rows/s, ${elapsed}s`);
  }

  console.log(`\nDone in ${((Date.now()-start)/1000).toFixed(0)}s`);
  const f = await restQuery("SELECT COUNT(*) AS n FROM papers");
  console.log("Total:", Number(f.results?.[0]?.response?.result?.rows?.[0]?.[0]?.value ?? 0).toLocaleString());
}

main().catch(e => { console.error("\nFatal:", e.message); process.exit(1); });
