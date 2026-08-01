#!/usr/bin/env python3
import sqlite3, os, time, sys

TOKEN=FILE = "/tmp/borr_turso_token"
TOKEN=*** = "libsql://borr-borrbd.aws-ap-south-1.turso.io"
DB = "borr.db"
BATCH = 50
TMP = "/tmp/_pt.sql"
TURSO = os.path.expanduser("~/.turso/turso")

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# Get Turso state
import subprocess
r = subprocess.run(["sh", "-c", 'echo "SELECT COALESCE(MAX(rowid),0) FROM papers;" | ' + TURSO + ' db shell borr'],
    capture_output=True, text=True, timeout=30)
last_rowid = 0
for line in r.stdout.strip().split("
"):
    if line.strip().isdigit():
        last_rowid = int(line.strip())
        break
print(f"Turso max rowid: {last_rowid}", flush=True)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
total_rem = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last_rowid,)).fetchone()[0]
print(f"Remaining: {total_rem}", flush=True)

if total_rem == 0:
    print("Already synced!")
    conn.close()
    sys.exit(0)

t0 = time.time()
pushed = 0
errs = 0
batch_rows = []
total_batches = (total_rem + BATCH - 1) // BATCH
batch_num = 0

cursor = conn.execute("SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid", (last_rowid,))

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
        batch_num += 1
        sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";"
        with open(TMP, "w") as f:
            f.write(sql)
        # Write file, then echo-pipe (more reliable than shell redirect)
        import subprocess as sp
        r2 = sp.run(["sh", "-c", TURSO + " db shell borr < " + TMP],
            capture_output=True, text=True, timeout=60)
        if r2.returncode == 0 and "Error" not in (r2.stdout or ""):
            pushed += len(batch_rows)
        else:
            errs += 1
            if errs <= 5:
                print(f"  ERR b{batch_num} r{row['rowid']}: {r2.stderr[:150] if r2.stderr else 'timeout'}", flush=True)
        batch_rows = []
        elapsed = time.time() - t0
        pct = pushed * 100 // total_rem if total_rem else 100
        rate = pushed / elapsed if elapsed > 0 else 0
        eta = (total_rem - pushed) / rate if rate > 0 else 0
        print(f"  [{batch_num}/{total_batches}] {pushed:,}/{total_rem:,} ({pct}%) | {rate:.0f} r/s | ETA {eta/60:.1f}m | errs={errs}", flush=True)

if batch_rows:
    batch_num += 1
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";"
    with open(TMP, "w") as f:
        f.write(sql)
    r2 = subprocess.run(["sh", "-c", TURSO + " db shell borr < " + TMP],
        capture_output=True, text=True, timeout=60)
    if r2.returncode == 0:
        pushed += len(batch_rows)

conn.close()
os.unlink(TMP)
elapsed = time.time() - t0
print(f"\nDone! {pushed:,} in {elapsed:.0f}s ({pushed/elapsed:.0f} r/s) errs={errs}", flush=True)

r = subprocess.run(["sh", "-c", 'echo "SELECT COUNT(*), MAX(rowid) FROM papers;" | ' + TURSO + ' db shell borr'],
    capture_output=True, text=True, timeout=30)
for line in r.stdout.strip().split("\n"):
    print(line.strip(), flush=True)
