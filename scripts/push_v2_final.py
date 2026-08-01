#!/usr/bin/env python3
"""Push papers to Turso borr-v2 with progress logged to file."""
import sqlite3, subprocess, time, os

TURSO = os.path.expanduser("~/.turso/turso")
BATCH = 2000
LOG = "/tmp/push_progress.log"

def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    print(msg, flush=True)

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

log("Opening local borr.db...")
conn = sqlite3.connect("/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db")
conn.row_factory = sqlite3.Row
total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
log(f"Total: {total:,}")

t0 = time.time()
pushed = 0
total_errors = 0
batch_rows = []
batch_num = 0
total_batches = (total + BATCH - 1) // BATCH

cursor = conn.execute("SELECT *, rowid FROM papers ORDER BY rowid")
columns = [d[0] for d in cursor.description if d[0] != 'rowid']

for row in cursor:
    vals = ",".join([q(row[c]) for c in columns])
    batch_rows.append(f"({vals})")
    
    if len(batch_rows) >= BATCH:
        batch_num += 1
        sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";"
        with open("/tmp/_push.sql", "w") as f:
            f.write(sql)
        r = subprocess.run(
            ["sh", "-c", f"{TURSO} db shell borr-v2 < /tmp/_push.sql"],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode != 0:
            total_errors += 1
            if total_errors <= 3:
                log(f"ERR batch {batch_num}: {r.stderr[:200]}")
        pushed += len(batch_rows)
        batch_rows = []
        
        if batch_num % 5 == 0:
            elapsed = time.time() - t0
            rate = pushed / elapsed if elapsed > 0 else 0
            pct = pushed * 100 // total
            eta = (total - pushed) / rate if rate > 0 else 0
            log(f"[{batch_num}/{total_batches}] {pushed:,}/{total:,} ({pct}%) | {rate:.0f} r/s | ETA {eta/60:.1f}m | errs={total_errors}")

# Final batch
if batch_rows:
    batch_num += 1
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";"
    with open("/tmp/_push.sql", "w") as f:
        f.write(sql)
    r = subprocess.run(
        ["sh", "-c", f"{TURSO} db shell borr-v2 < /tmp/_push.sql"],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        total_errors += 1
    pushed += len(batch_rows)

conn.close()
elapsed = time.time() - t0
log(f"DONE! {pushed:,} in {elapsed:.0f}s ({pushed/elapsed:.0f} r/s) errors={total_errors}")

# Verify
r = subprocess.run(
    ["sh", "-c", f'echo "SELECT COUNT(*) FROM papers;" | {TURSO} db shell borr-v2'],
    capture_output=True, text=True, timeout=30
)
for line in r.stdout.strip().split("\n"):
    if line.strip().isdigit():
        log(f"Turso count: {line.strip()}")
