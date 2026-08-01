#!/usr/bin/env python3
import sqlite3, subprocess, os, time, sys

TURSO = os.path.expanduser("~/.turso/turso")
DB = "/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db"
BATCH_SIZE = 500
TMP = "/tmp/_p500.sql"

# Quote helper
def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# 1. Get Turso state
cmd_check = 'echo "SELECT COALESCE(MAX(rowid),0) FROM papers;" | ' + TURSO + ' db shell borr'
res = subprocess.run(["sh", "-c", cmd_check], capture_output=True, text=True, timeout=30)
last = 0
for line in res.stdout.split("\n"):
    line = line.strip()
    if line.isdigit():
        last = int(line)
        break
print("Turso max rowid: " + str(last), flush=True)

# 2. Count
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rem = conn.execute("SELECT COUNT(*) FROM papers WHERE verified=1 AND rowid > ?", (last,)).fetchone()[0]
print("Remaining: " + str(rem), flush=True)
if rem == 0:
    print("DONE - all synced!")
    conn.close()
    sys.exit(0)

# 3. Build and push
pushed = 0
rows = []
batch_count = 0
cursor = conn.execute("SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid LIMIT ?", (last, BATCH_SIZE))

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
    rows.append("(" + vals + ")")

if rows:
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(rows) + ";\n"
    with open(TMP, "w") as f:
        f.write(sql)
    t0 = time.time()
    cmd_push = TURSO + " db shell borr < " + TMP
    res2 = subprocess.run(["sh", "-c", cmd_push], capture_output=True, text=True, timeout=300)
    elapsed = time.time() - t0
    if res2.returncode == 0:
        pushed = len(rows)
        print("Pushed " + str(pushed) + " rows in " + str(int(elapsed)) + "s", flush=True)
    else:
        print("ERROR: " + str(res2.stderr[:200] if res2.stderr else "timeout"), flush=True)

conn.close()
os.unlink(TMP)

# Final check
res3 = subprocess.run(["sh", "-c", cmd_check], capture_output=True, text=True, timeout=30)
for line in res3.stdout.split("\n"):
    print(line.strip(), flush=True)
