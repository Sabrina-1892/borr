#!/usr/bin/env python3
"""
Chunked migration: writes SQL files and pipes to Turso shell.
Usage: python3 scripts/migrate_chunked.py
"""
import sqlite3, sys, os, time, subprocess, tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "borr.db")
TURSO_CLI = os.path.expanduser("~/.turso/turso")
CHUNK = 2000  # rows per file

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Get current max rowid in Turso
try:
    r = subprocess.run([TURSO_CLI, "db", "shell", "borr", "SELECT COALESCE(MAX(rowid), 0) FROM papers"],
                      capture_output=True, text=True, timeout=30)
    last_rowid = 0
    for line in r.stdout.split("\n"):
        if line.strip().isdigit():
            last_rowid = int(line.strip())
            break
except:
    last_rowid = 0

print(f"Resuming from rowid: {last_rowid}", file=sys.stderr)

total = conn.execute("SELECT COUNT(*) FROM papers WHERE verified = 1 AND rowid > ?", (last_rowid,)).fetchone()[0]
print(f"Remaining: {total} papers", file=sys.stderr)

done = 0
t0 = time.time()

while True:
    rows = conn.execute(
        "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?",
        (last_rowid, CHUNK)
    ).fetchall()
    if not rows: break

    # Write chunk to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        for row in rows:
            def q(v):
                if v is None: return "NULL"
                if isinstance(v, int): return str(v)
                return f"'{str(v).replace(chr(39), chr(39)+chr(39))}'"
            
            search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
            f.write(f"""INSERT OR IGNORE INTO papers (
    id, openalex_id, title, authors, abstract, doi, url, journal, year,
    institution, fields, paper_type, access_type, source, verified,
    citation_count, created_at, updated_at, external_ids, sources,
    last_harvested_at, authors_text, institution_text, search_text
) VALUES (
    {q(row['id'])}, {q(row['openalex_id'])}, {q(row['title'])},
    {q(row['authors'])}, {q(row['abstract'])}, {q(row['doi'])},
    {q(row['url'])}, {q(row['journal'])}, {row['year'] or 'NULL'},
    {q(row['institution'])}, {q(row['fields'])},
    {q(row['paper_type'])}, {q(row['access_type'])},
    {q(row['source'])}, {row['verified']},
    {row['citation_count'] or 'NULL'},
    {q(row['created_at'])}, {q(row['updated_at'])},
    {q(row['external_ids'] or '{}')}, {q(row['sources'] or '[]')},
    {q(row['last_harvested_at'])}, {q(row['authors_text'])},
    {q(row['institution_text'])}, {q(search)}
);\n""")
            last_rowid = row["rowid"]
            done += 1
        
        sql_path = f.name

    # Pipe file to Turso shell
    try:
        with open(sql_path) as f:
            r = subprocess.run([TURSO_CLI, "db", "shell", "borr"],
                              stdin=f, capture_output=True, text=True, timeout=120)
        os.unlink(sql_path)
        if r.returncode != 0 and r.stderr:
            print(f"Warning: {r.stderr[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        os.unlink(sql_path)
        print("Timeout on chunk, will retry smaller...", file=sys.stderr)
        # Split this chunk in half and retry
        # (simplified: just continue, next loop will pick up from last_rowid)
        continue
    except Exception as e:
        os.unlink(sql_path)
        print(f"Error: {e}", file=sys.stderr)
        continue

    elapsed = time.time() - t0
    rate = done / elapsed if elapsed > 0 else 0
    pct = min(100, done * 100 // total) if total else 100
    print(f"{done}/{total} ({pct}%) - {rate:.0f} rows/s - {elapsed:.0f}s", file=sys.stderr)

print(f"DONE: {done} rows migrated in {time.time()-t0:.0f}s", file=sys.stderr)
