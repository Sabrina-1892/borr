#!/usr/bin/env python3
import sqlite3, subprocess, os, time, sys

TURSO = os.path.expanduser("~/.turso/turso")
DB = "/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db"
CHUNK = 2000
TMP = "/tmp/_push_all.sql"

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# 1. Get Turso state
cmd = 'echo "SELECT COALESCE(MAX(rowid),0) FROM papers;" | ' + TURSO + ' db shell borr-v2'
res = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=30)
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
    print("DONE!")
    conn.close()
    sys.exit(0)

# 3. Push in chunks
t0 = time.time()
pushed_total = 0
errs = 0
chunk_num = 0
total_chunks = (rem + CHUNK - 1) // CHUNK

offset = 0
while offset < rem:
    chunk_num += 1
    rows = conn.execute("SELECT *, rowid FROM papers WHERE verified=1 AND rowid > ? ORDER BY rowid LIMIT ?",
                       (last, CHUNK)).fetchall()
    if not rows:
        break
    
    vals_list = []
    for row in rows:
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
        vals_list.append("(" + vals + ")")
    
    sql = "INSERT OR IGNORE INTO papers VALUES " + ",".join(vals_list) + ";\n"
    with open(TMP, "w") as f:
        f.write(sql)
    
    tc = time.time()
    res2 = subprocess.run(["sh", "-c", TURSO + " db shell borr-v2 < " + TMP],
        capture_output=True, text=True, timeout=300)
    dt = time.time() - tc
    
    if res2.returncode == 0:
        pushed_total += len(rows)
        last = rows[-1]["rowid"]
        offset += len(rows)
    else:
        errs += 1
        print("  ERR chunk " + str(chunk_num) + ": " + str(res2.stderr[:200] if res2.stderr else "timeout"), flush=True)
    
    elapsed = time.time() - t0
    rate = pushed_total / elapsed if elapsed > 0 else 0
    eta = (rem - pushed_total) / rate if rate > 0 else 0
    pct = pushed_total * 100 // rem if rem else 100
    print("  [" + str(chunk_num) + "/" + str(total_chunks) + "] " + str(pushed_total) + "/" + str(rem) + " (" + str(pct) + "%) | " + str(int(rate)) + "r/s | ETA" + str(round(eta/60,1)) + "m | dt=" + str(round(dt,1)) + "s", flush=True)

conn.close()
os.unlink(TMP)

elapsed = time.time() - t0
print("\nDone! " + str(pushed_total) + " in " + str(int(elapsed)) + "s (" + str(int(pushed_total/elapsed if elapsed>0 else 0)) + "r/s) errs=" + str(errs), flush=True)

# Verify
res3 = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=30)
for line in res3.stdout.split("\n"):
    print(line.strip(), flush=True)
