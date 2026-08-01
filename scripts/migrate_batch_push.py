#!/usr/bin/env python3
"""Push remaining papers to Turso - batch INSERTs via shell redirect."""
import sqlite3, os, time, subprocess, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "borr.db")
TURSO = os.path.expanduser("~/.turso/turso")
BATCH = 500
BATCH_FILE = "/tmp/borr_batch.sql"

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

def run_turso_query(sql_stmt):
    """Run a single SQL statement via Turso shell using echo pipe."""
    r = subprocess.run(
        f'echo "{sql_stmt}" | {TURSO} db shell borr',
        shell=True, capture_output=True, text=True, timeout=60
    )
    return r.stdout, r.stderr, r.returncode

# --- Step 1: Get current Turso state ---
print("Step 1: Checking Turso state...", flush=True)
stdout, stderr, rc = run_turso_query("SELECT COALESCE(MAX(rowid),0) FROM papers;")
if rc != 0:
    print(f"ERROR querying Turso: {stderr}", flush=True)
    sys.exit(1)

last_rowid = 0
for line in stdout.strip().split("\n"):
    if line.strip().isdigit():
        last_rowid = int(line.strip())
        break
print(f"  Turso max rowid: {last_rowid}", flush=True)

# --- Step 2: Count remaining ---
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
total_rem = conn.execute(
    "SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last_rowid,)
).fetchone()[0]
print(f"  Remaining to push: {total_rem} papers", flush=True)

if total_rem == 0:
    print("Nothing to push — already synced!", flush=True)
    conn.close()
    sys.exit(0)

# --- Step 3: Push batches ---
print("\nStep 2: Pushing batches...", flush=True)
t0 = time.time()
pushed = 0
batch_rows = []
errors = 0

cursor = conn.execute(
    "SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid",
    (last_rowid,)
)

for row in cursor:
    search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
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
    batch_rows.append(f"({vals})")

    if len(batch_rows) >= BATCH:
        sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";\n"
        with open(BATCH_FILE, "w") as f:
            f.write(sql)
        r = subprocess.run(
            f"{TURSO} db shell borr < {BATCH_FILE}",
            shell=True, capture_output=True, text=True, timeout=300
        )
        if r.returncode != 0:
            errors += 1
            if errors <= 3:
                print(f"  ERROR near rowid {row['rowid']}: {r.stderr[:200]}", flush=True)
        pushed += len(batch_rows)
        batch_rows = []
        elapsed = time.time() - t0
        pct = pushed * 100 // total_rem if total_rem else 100
        rate = pushed / elapsed if elapsed > 0 else 0
        eta = (total_rem - pushed) / rate if rate > 0 else 0
        print(f"  Pushed: {pushed:,}/{total_rem:,} ({pct}%) | {rate:.0f} r/s | ETA {eta/60:.1f}m | errs={errors}", flush=True)

# Final batch
if batch_rows:
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(batch_rows) + ";\n"
    with open(BATCH_FILE, "w") as f:
        f.write(sql)
    r = subprocess.run(
        f"{TURSO} db shell borr < {BATCH_FILE}",
        shell=True, capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        errors += 1
    pushed += len(batch_rows)

conn.close()
if os.path.exists(BATCH_FILE):
    os.unlink(BATCH_FILE)

elapsed = time.time() - t0
print(f"\nDone! Pushed {pushed:,} papers in {elapsed:.0f}s ({pushed/elapsed:.0f} r/s) errors={errors}", flush=True)

# --- Step 4: Verify ---
print("\nStep 3: Verifying...", flush=True)
stdout, stderr, rc = run_turso_query("SELECT COUNT(*) FROM papers;")
for line in stdout.strip().split("\n"):
    if line.strip().isdigit():
        print(f"  Turso final count: {line.strip()}", flush=True)

print(f"\nTotal wall time: {time.time()-t0:.0f}s", flush=True)
