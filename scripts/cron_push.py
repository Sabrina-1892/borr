#!/usr/bin/env python3
"""Cron-friendly push: push 5,000 papers to Turso borr."""
import sqlite3, subprocess, os, time, sys

TURSO = os.path.expanduser("~/.turso/turso")
DB = "/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db"
BATCH = 100  # rows per INSERT
MAX_TO_PUSH = 5000  # push at most this many per run
TMP = "/tmp/borr_cron_push.sql"

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# Get Turso state
r = subprocess.run(["sh", "-c", 'echo "SELECT COALESCE(MAX(rowid),0) FROM papers;" | ' + TURSO + ' db shell borr'],
    capture_output=True, text=True, timeout=30)
last_rowid = 0
for line in r.stdout.strip().split("\n"):
    if line.strip().isdigit():
        last_rowid = int(line.strip())
        break

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
total_rem = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last_rowid,)).fetchone()[0]
total_local = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1").fetchone()[0]
print("Turso max rowid: " + str(last_rowid), flush=True)
print("Remaining: " + str(total_rem) + " of " + str(total_local), flush=True)

if total_rem == 0:
    print("DONE - all synced!", flush=True)
    conn.close()
    sys.exit(0)

limit = min(MAX_TO_PUSH, total_rem)
t0 = time.time()
pushed = 0
errs = 0
batch_rows = []

cursor = conn.execute("SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid LIMIT ?", (last_rowid, limit))

for row in cursor:
    search = (row["title"] + " " + (row["abstract"] or "") + " " + (row["authors_text"] or "")).lower()
    vals = ",".join([
        q(row["id"]), q(row["openalex_id"]), q(row["title"]),
        q(row["authors"]), q(row["abstract"]), q(row["doi"]),
        q(row["url"]), q(row["journal"]),
        q(row["year"]), q(row["institution"]), q(row["fields"]),
        q(row["paper_type"]), q(row["access_type"]), q(row["source"]),
        q(row["verified"]), q(row["citation_count"]),
        q(row["created_at"]), q(row["updated_at"]),
        q(row["external_ids"] or "{}"), q(row["sources"] or "[]"),
        q(row["last_harvested_at"]), q(row["authors_text"]),
        q(row["institution_text"]), q(search),
    ])
    batch_rows.append("(" + vals + ")")
    
    if len(batch_rows) >= BATCH:
        sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";
"
        with open(TMP, "w") as f:
            f.write(sql)
        r2 = subprocess.run(["sh", "-c", TURSO + " db shell borr < " + TMP],
            capture_output=True, text=True, timeout=120)
        if r2.returncode == 0:
            pushed += len(batch_rows)
        else:
            errs += 1
            if errs <= 3:
                e = (r2.stderr or "")[:150]
                print("  ERR r" + str(row["rowid"]) + ": " + e, flush=True)
        batch_rows = []
        elapsed = time.time() - t0
        rate = pushed / elapsed if elapsed > 0 else 0
        eta = (limit - pushed) / rate if rate > 0 else 0
        pct = pushed * 100 // limit if limit else 100
        print("  " + str(pushed) + "/" + str(limit) + " (" + str(pct) + "%) " + str(int(rate)) + "r/s ETA" + str(round(eta/60,1)) + "m", flush=True)

if batch_rows:
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";
"
    with open(TMP, "w") as f:
        f.write(sql)
    r2 = subprocess.run(["sh", "-c", TURSO + " db shell borr < " + TMP],
        capture_output=True, text=True, timeout=120)
    if r2.returncode == 0:
        pushed += len(batch_rows)

conn.close()
os.unlink(TMP)
elapsed = time.time() - t0
print("Pushed " + str(pushed) + " in " + str(int(elapsed)) + "s (" + str(int(pushed/elapsed if elapsed>0 else 0)) + "r/s) errs=" + str(errs), flush=True)

# Final check
r = subprocess.run(["sh", "-c", 'echo "SELECT COUNT(*), MAX(rowid) FROM papers;" | ' + TURSO + ' db shell borr'],
    capture_output=True, text=True, timeout=30)
for line in r.stdout.strip().split("\n"):
    if line.strip().isdigit():
print("LOCAL_TOTAL:" + str(total_local), flush=True)
