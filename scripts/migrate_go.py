#!/usr/bin/env python3
import sqlite3, os, time, sys
from libsql_experimental import connect

DB = "borr.db"
with open("/tmp/borr_turso_token") as f:
    TOKEN=*** = "libsql://borr-borrbd.aws-ap-south-1.turso.io"

turso = connect(URL, auth_token=TOKEN)

r = turso.execute("SELECT COALESCE(MAX(rowid),0) FROM papers")
last_rowid = r.fetchall()[0][0]
r = turso.execute("SELECT COUNT(*) FROM papers")
print(f"Turso: {r.fetchall()[0][0]:,} papers, max rowid {last_rowid}", flush=True)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
total_rem = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last_rowid,)).fetchone()[0]
print(f"Remaining: {total_rem:,}", flush=True)

if total_rem == 0:
    print("Done!")
    conn.close()
    sys.exit(0)

BATCH = 100
COLS = 23
t0 = time.time()
pushed = 0
errs = 0
bp = []

cursor = conn.execute("SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid", (last_rowid,))
for row in cursor:
    s = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
    bp.append((
        row["id"], row["openalex_id"], row["title"], row["authors"], row["abstract"],
        row["doi"], row["url"], row["journal"], row["year"], row["institution"],
        row["fields"], row["paper_type"], row["access_type"], row["source"],
        row["verified"], row["citation_count"], row["created_at"], row["updated_at"],
        row["external_ids"] or "{}", row["sources"] or "[]",
        row["last_harvested_at"], row["authors_text"], row["institution_text"], s,
    ))
    if len(bp) >= BATCH:
        ph = ",".join(["(" + ",".join(["?"] * COLS) + ")"] * len(bp))
        sql = f"INSERT OR IGNORE INTO papers VALUES {ph}"
        try:
            turso.execute(sql, bp)
        except Exception as e:
            errs += 1
            if errs <= 3:
                print(f"  ERR ~{row['rowid']}: {str(e)[:200]}", flush=True)
        pushed += len(bp)
        bp = []
        el = time.time() - t0
        rt = pushed / el if el > 0 else 0
        eta = (total_rem - pushed) / rt if rt > 0 else 0
        print(f"  {pushed:,}/{total_rem:,} | {rt:.0f} r/s | ETA {eta/60:.1f}m | errs={errs}", flush=True)

if bp:
    ph = ",".join(["(" + ",".join(["?"] * COLS) + ")"] * len(bp))
    sql = f"INSERT OR IGNORE INTO papers VALUES {ph}"
    try:
        turso.execute(sql, bp)
    except Exception as e:
        errs += 1
    pushed += len(bp)

conn.close()
el = time.time() - t0
print(f"\nDone! {pushed:,} in {el:.0f}s ({pushed/el:.0f} r/s) errs={errs}", flush=True)
r = turso.execute("SELECT COUNT(*) FROM papers")
print(f"Turso: {r.fetchall()[0][0]:,}", flush=True)
