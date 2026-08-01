#!/usr/bin/env python3
"""Push all papers from local borr.db to Turso borr-v2."""
import sqlite3, subprocess, time, sys, os

TURSO = os.path.expanduser("~/.turso/turso")
BATCH = 1000
TMP = "/tmp/_push_v2.sql"
total_errors = 0

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    s = str(v)
    return "'" + s.replace("'", "''") + "'"

print("Opening local borr.db...", flush=True)
conn = sqlite3.connect("/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db")
conn.row_factory = sqlite3.Row
total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
print(f"Total papers to push: {total:,}", flush=True)

t0 = time.time()
pushed = 0
batch_rows = []
batch_num = 0
total_batches = (total + BATCH - 1) // BATCH

cursor = conn.execute("SELECT *, rowid FROM papers ORDER BY rowid")
columns = [desc[0] for desc in cursor.description if desc[0] != 'rowid']
print(f"Columns: {len(columns)}", flush=True)

for row in cursor:
    vals = ",".join([q(row[col]) for col in columns])
    batch_rows.append(f"({vals})")
    
    if len(batch_rows) >= BATCH:
        batch_num += 1
        sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";\n"
        with open(TMP, "w") as f:
            f.write(sql)
        r = subprocess.run(["sh", "-c", f"{TURSO} db shell borr-v2 < {TMP}"],
            capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            total_errors += 1
            if total_errors <= 3:
                print(f"  ERR batch {batch_num}: {r.stderr[:200]}", flush=True)
        pushed += len(batch_rows)
        batch_rows = []
        elapsed = time.time() - t0
        pct = pushed * 100 // total if total else 100
        rate = pushed / elapsed if elapsed > 0 else 0
        eta = (total - pushed) / rate if rate > 0 else 0
        print(f"  [{batch_num}/{total_batches}] {pushed:,}/{total:,} ({pct}%) | {rate:.0f} r/s | ETA {eta/60:.1f}m | errs={total_errors}", flush=True)

# Final batch
if batch_rows:
    batch_num += 1
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";\n"
    with open(TMP, "w") as f:
        f.write(sql)
    r = subprocess.run(["sh", "-c", f"{TURSO} db shell borr-v2 < {TMP}"],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        total_errors += 1
    pushed += len(batch_rows)

conn.close()
if os.path.exists(TMP):
    os.unlink(TMP)

elapsed = time.time() - t0
print(f"\n=== DONE ===", flush=True)
print(f"Pushed {pushed:,} papers in {elapsed:.0f}s ({pushed/elapsed:.0f} r/s) errors={total_errors}", flush=True)

# Verify
r = subprocess.run(["sh", "-c", f'echo "SELECT COUNT(*) FROM papers;" | {TURSO} db shell borr-v2'],
    capture_output=True, text=True, timeout=30)
for line in r.stdout.strip().split("\n"):
    if line.strip().isdigit():
        print(f"Turso borr-v2 count: {line.strip()}", flush=True)
