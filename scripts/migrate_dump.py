#!/usr/bin/env python3
"""Dump remaining papers to SQL file then pipe to Turso."""
import sqlite3, sys, os, time, subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "borr.db")
TURSO = os.path.expanduser("~/.turso/turso")
SQL_FILE = "/tmp/borr_remaining.sql"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Get current max rowid in Turso
r = subprocess.run(TURSO.split() + ["db", "shell", "borr",
    "SELECT COALESCE(MAX(rowid), 0) FROM papers;"],
    capture_output=True, text=True, timeout=60)
last_rowid = 0
for line in r.stdout.strip().split("\n"):
    line = line.strip()
    if line.isdigit():
        last_rowid = int(line)
        break
print(f"Resuming from rowid: {last_rowid}")

total = conn.execute("SELECT COUNT(*) FROM papers WHERE verified = 1 AND rowid > ?", (last_rowid,)).fetchone()[0]
print(f"Remaining: {total} papers")

# Dump to SQL file
t0 = time.time()
written = 0
with open(SQL_FILE, "w") as f:
    offset = 0
    while True:
        rows = conn.execute("SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT 1000", (last_rowid,)).fetchall()
        if not rows: break
        
        for row in rows:
            def q(v):
                if v is None: return "NULL"
                if isinstance(v, int): return str(v)
                return f"'{str(v).replace(chr(39), chr(39)+chr(39))}'"
            search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
            f.write(f"INSERT OR IGNORE INTO papers VALUES({q(row['id'])},{q(row['openalex_id'])},{q(row['title'])},{q(row['authors'])},{q(row['abstract'])},{q(row['doi'])},{q(row['url'])},{q(row['journal'])},{row['year'] or 'NULL'},{q(row['institution'])},{q(row['fields'])},{q(row['paper_type'])},{q(row['access_type'])},{q(row['source'])},{row['verified']},{row['citation_count'] or 'NULL'},{q(row['created_at'])},{q(row['updated_at'])},{q(row['external_ids'] or '{}')},{q(row['sources'] or '[]')},{q(row['last_harvested_at'])},{q(row['authors_text'])},{q(row['institution_text'])},{q(search)});\n")
            last_rowid = row["rowid"]
            written += 1
        
        elapsed = time.time() - t0
        pct = written * 100 // total if total else 100
        print(f"  Dumping: {written}/{total} ({pct}%) - {elapsed:.0f}s", file=sys.stderr)

print(f"SQL file: {SQL_FILE} ({os.path.getsize(SQL_FILE)/1024/1024:.1f} MB)")
print(f"Now piping to Turso...")

# Pipe file to turso shell
t0 = time.time()
with open(SQL_FILE, "r") as f:
    r = subprocess.run(TURSO.split() + ["db", "shell", "borr"],
                      stdin=f, capture_output=True, text=True, timeout=3600)

elapsed = time.time() - t0
print(f"Turso shell returned: {r.returncode}")
if r.stderr:
    print(f"Stderr: {r.stderr[:500]}")
os.unlink(SQL_FILE)

# Verify
r2 = subprocess.run(TURSO.split() + ["db", "shell", "borr",
    "SELECT COUNT(*) FROM papers;"],
    capture_output=True, text=True, timeout=60)
print(f"Import took {elapsed:.0f}s")
print(f"Turso count output:\n{r2.stdout.strip()[-200:]}")
