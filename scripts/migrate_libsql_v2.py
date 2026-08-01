#!/usr/bin/env python3
"""Push remaining papers to Turso via libsql-experimental (FTS triggers dropped)."""
import sqlite3, os, time, sys
from libsql_experimental import connect

DB = "borr.db"
with open("/tmp/borr_turso_token") as f:
    TOKEN=f.read...nURL = "libsql://borr-borrbd.aws-ap-south-1.turso.io"

turso = connect(URL, auth_token=TOKEN)

# Get current state
r = turso.execute("SELECT COALESCE(MAX(rowid),0) FROM papers")
last_rowid = r.fetchall()[0][0]
r = turso.execute("SELECT COUNT(*) FROM papers")
current_count = r.fetchall()[0][0]
print(f"Turso: {current_count:,} papers, max rowid {last_rowid}", flush=True)

# Count remaining locally
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
total_local = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1").fetchone()[0]
total_rem = conn.execute(
    "SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last_rowid,)
).fetchone()[0]
print(f"Local: {total_local:,} total, {total_rem:,} remaining", flush=True)

if total_rem == 0:
    print("Nothing to push!")
    conn.close()
    sys.exit(0)

# Push in batches
BATCH = 100  # smaller batch for reliability
COLUMNS = 23
t0 = time.time()
pushed = 0
errors = 0

cursor = conn.execute(
    "SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid",
    (last_rowid,)
)

batch_params = []
for row in cursor:
    search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
    batch_params.append((
        row["id"], row["openalex_id"], row["title"],
        row["authors"], row["abstract"], row["doi"],
        row["url"], row["journal"],
        row["year"], row["institution"], row["fields"],
        row["paper_type"], row["access_type"], row["source"],
        row["verified"], row["citation_count"],
        row["created_at"], row["updated_at"],
        row["external_ids"] or "{}", row["sources"] or "[]",
        row["last_harvested_at"], row["authors_text"],
        row["institution_text"], search,
    ))
    
    if len(batch_params) >= BATCH:
        placeholders = ",".join(["(" + ",".join(["?"] * COLUMNS) + ")"] * len(batch_params))
        sql = f"INSERT OR IGNORE INTO papers VALUES {placeholders}"
        try:
            turso.execute(sql, batch_params)
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  ERROR batch ~rowid {row['rowid']}: {str(e)[:200]}", flush=True)
        pushed += len(batch_params)
        batch_params = []
        elapsed = time.time() - t0
        pct = pushed * 100 // total_rem if total_rem else 100
        rate = pushed / elapsed if elapsed > 0 else 0
        eta = (total_rem - pushed) / rate if rate > 0 else 0
        print(f"  Pushed: {pushed:,}/{total_rem:,} ({pct}%) | {rate:.0f} r/s | ETA {eta/60:.1f}m | errs={errors}", flush=True)

# Final batch
if batch_params:
    placeholders = ",".join(["(" + ",".join(["?"] * COLUMNS) + ")"] * len(batch_params))
    sql = f"INSERT OR IGNORE INTO papers VALUES {placeholders}"
    try:
        turso.execute(sql, batch_params)
    except Exception as e:
        errors += 1
    pushed += len(batch_params)

conn.close()
elapsed = time.time() - t0
print(f"\nDone! Pushed {pushed:,} in {elapsed:.0f}s ({pushed/elapsed:.0f} r/s) errs={errors}", flush=True)

# Verify
r = turso.execute("SELECT COUNT(*) FROM papers")
print(f"Turso final: {r.fetchall()[0][0]:,}", flush=True)
print(f"Local total: {total_local:,}", flush=True)
