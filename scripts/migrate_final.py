#!/usr/bin/env python3
"""
Final migration: pipes INSERT statements directly through turso db shell.
Usage: python3 scripts/migrate_final.py | ~/.turso/turso db shell borr
"""
import sqlite3, sys, os, json, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "borr.db")
CHUNK = 500

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

last_id = None
total = conn.execute("SELECT COUNT(*) FROM papers WHERE verified = 1").fetchone()[0]
done = 0
t0 = time.time()

# First get the max rowid already in Turso via a passed rowid from the resume script
last_rowid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
# We'll track by paper id instead
cursor = conn.execute("SELECT id, MAX(rowid) as r FROM papers WHERE verified = 1 GROUP BY id ORDER BY r")
print(f"-- Skipping rows up to rowid {last_rowid}", file=sys.stderr)

while True:
    rows = conn.execute(
        "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT ?",
        (last_rowid, CHUNK)
    ).fetchall()
    if not rows: break

    for row in rows:
        def q(v):
            if v is None: return "NULL"
            if isinstance(v, int): return str(v)
            s = str(v).replace("'", "''")
            return f"'{s}'"
        
        search = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
        
        print(f"""INSERT OR IGNORE INTO papers (
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
);""")
        last_rowid = row["rowid"]
        done += 1
    
    pct = min(100, done * 100 // (total - (int(sys.argv[1]) if len(sys.argv) > 1 else 0) or 1))
    elapsed = time.time() - t0
    rate = done / elapsed if elapsed > 0 else 0
    print(f"-- {done} rows ({pct}%), {rate:.0f} rows/s, {elapsed:.0f}s", file=sys.stderr)

print(f"-- COMPLETE: {done} rows migrated", file=sys.stderr)
