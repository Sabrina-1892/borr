#!/usr/bin/env python3
"""Push remaining ~90k papers to Turso: generate all SQL to a file, then pipe in one session."""
import sqlite3, sys, os, time, subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "borr.db")
TURSO = os.path.expanduser("~/.turso/turso")
SQL_FILE = "/tmp/borr_remaining_batch.sql"

def q(v):
    """SQL quote value."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# 1. Get Turso progress
proc = subprocess.Popen(
    [TURSO, "db", "shell", "borr"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)
stdout, _ = proc.communicate(input="SELECT COALESCE(MAX(rowid),0) FROM papers;\n", timeout=30)
last_rowid = 0
for line in stdout.strip().split("\n"):
    line = line.strip()
    if line.isdigit():
        last_rowid = int(line)
        break
print(f"Turso last rowid: {last_rowid}")

# 2. Count remaining
conn = sqlite3.connect(DB)
total_rem = conn.execute(
    "SELECT COUNT(*) FROM papers WHERE verified = 1 AND rowid > ?", (last_rowid,)
).fetchone()[0]
print(f"Remaining to push: {total_rem} papers")

if total_rem == 0:
    print("Nothing to do!")
    conn.close()
    sys.exit(0)

# 3. Generate all INSERTs to SQL file
t0 = time.time()
written = 0
batch = []
BATCH_SIZE = 500

with open(SQL_FILE, "w") as f:
    cursor = conn.execute(
        "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid",
        (last_rowid,)
    )
    for row in cursor:
        search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
        vals = ",".join([
            q(row['id']), q(row['openalex_id']), q(row['title']),
            q(row['authors']), q(row['abstract']), q(row['doi']),
            q(row['url']), q(row['journal']),
            q(row['year']), q(row['institution']), q(row['fields']),
            q(row['paper_type']), q(row['access_type']), q(row['source']),
            q(row['verified']), q(row['citation_count']),
            q(row['created_at']), q(row['updated_at']),
            q(row['external_ids'] or '{}'), q(row['sources'] or '[]'),
            q(row['last_harvested_at']), q(row['authors_text']),
            q(row['institution_text']), q(search),
        ])
        batch.append(f"({vals})")
        
        if len(batch) >= BATCH_SIZE:
            f.write("INSERT OR IGNORE INTO papers VALUES " + ",".join(batch) + ";\n")
            written += len(batch)
            batch = []
            elapsed = time.time() - t0
            pct = written * 100 // total_rem if total_rem else 100
            print(f"  Generating SQL: {written:,}/{total_rem:,} ({pct}%) - {elapsed:.0f}s", flush=True)
    
    # Final batch
    if batch:
        f.write("INSERT OR IGNORE INTO papers VALUES " + ",".join(batch) + ";\n")
        written += len(batch)

gen_time = time.time() - t0
file_size = os.path.getsize(SQL_FILE) / 1024 / 1024
print(f"SQL file generated: {SQL_FILE} ({file_size:.1f} MB) in {gen_time:.0f}s")
print(f"Total statements: {written:,}")
conn.close()

# 4. Pipe to Turso in one session
print(f"\nPiping to Turso...", flush=True)
t1 = time.time()

with open(SQL_FILE, "r") as f:
    proc = subprocess.Popen(
        [TURSO, "db", "shell", "borr"],
        stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = proc.communicate(timeout=3600)

pipe_time = time.time() - t1
print(f"Turso pipe done in {pipe_time:.0f}s (rc={proc.returncode})")
if stderr:
    print(f"Stderr: {stderr[:500]}")
os.unlink(SQL_FILE)

# 5. Verify
proc = subprocess.Popen(
    [TURSO, "db", "shell", "borr"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True
)
stdout, _ = proc.communicate(input="SELECT COUNT(*) FROM papers;\n", timeout=30)
print(f"\nTurso count: {stdout.strip()}")

total_time = time.time() - t0
print(f"Total time: {total_time:.0f}s")
