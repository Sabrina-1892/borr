#!/usr/bin/env python3
"""Fast migration using concurrent curl calls to Turso REST API."""
import sqlite3, os, subprocess, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DB = "borr.db"
TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
URL = "https://borr-borrbd.aws-ap-south-1.turso.io/v2/pipeline"
CONCUR = 15

if not TOKEN:
    print("Missing TURSO_AUTH_TOKEN", file=sys.stderr)
    sys.exit(1)

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    # Escape single quotes for SQL by doubling them
    return "'" + str(v).replace("'", "''") + "'"

def insert_sql(row):
    s = f"{row['title']} {row['abstract'] or ''} {row['authors_text'] or ''}".lower()
    cols = "id,openalex_id,title,authors,abstract,doi,url,journal,year,"
    cols += "institution,fields,paper_type,access_type,source,verified,"
    cols += "citation_count,created_at,updated_at,external_ids,sources,"
    cols += "last_harvested_at,authors_text,institution_text,search_text"
    vals = f"{q(row['id'])},{q(row['openalex_id'])},{q(row['title'])},{q(row['authors'])},"
    vals += f"{q(row['abstract'])},{q(row['doi'])},{q(row['url'])},{q(row['journal'])},"
    vals += f"{row['year'] or 'NULL'},{q(row['institution'])},{q(row['fields'])},"
    vals += f"{q(row['paper_type'])},{q(row['access_type'])},{q(row['source'])},{row['verified']},"
    vals += f"{row['citation_count'] or 'NULL'},{q(row['created_at'])},{q(row['updated_at'])},"
    vals += f"{q(row['external_ids'] or '{}')},{q(row['sources'] or '[]')},"
    vals += f"{q(row['last_harvested_at'])},{q(row['authors_text'])},{q(row['institution_text'])},{q(s)}"
    return f"INSERT OR IGNORE INTO papers({cols})VALUES({vals})"

def send(sql):
    body = '{"requests":[{"type":"execute","stmt":{"sql":' + json.dumps(sql) + '}}]}'
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "30", "-X", "POST", URL,
             "-H", f"Authorization: Bearer {TOKEN}",
             "-H", "Content-Type: application/json", "-d", body],
            capture_output=True, text=True, timeout=35)
        if r.returncode == 0 and '"type":"ok"' in r.stdout:
            return True
        return False
    except:
        return False

import json

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Get max rowid from Turso
r = subprocess.run(
    ["curl", "-s", "--max-time", "15", "-X", "POST", URL,
     "-H", f"Authorization: Bearer {TOKEN}",
     "-H", "Content-Type: application/json",
     "-d", '{"requests":[{"type":"execute","stmt":{"sql":"SELECT COALESCE(MAX(rowid),0) AS n FROM papers"}}]}'],
    capture_output=True, text=True)
try:
    d = json.loads(r.stdout)
    last_rowid = int(d["results"][0]["response"]["result"]["rows"][0][0]["value"])
except:
    last_rowid = 0

print(f"Last rowid: {last_rowid}", file=sys.stderr)

total = conn.execute("SELECT COUNT(*) FROM papers WHERE verified = 1 AND rowid > ?", (last_rowid,)).fetchone()[0]
print(f"Remaining: {total}", file=sys.stderr)

done = 0
errors = 0
t0 = time.time()

executor = ThreadPoolExecutor(max_workers=CONCUR)

while True:
    rows = conn.execute(
        "SELECT *, rowid FROM papers WHERE verified = 1 AND rowid > ? ORDER BY rowid LIMIT 500",
        (last_rowid,)).fetchall()
    if not rows: break
    
    # Submit concurrent inserts
    futures = []
    for row in rows:
        sql = insert_sql(row)
        futures.append(executor.submit(send, sql))
        last_rowid = row["rowid"]
    
    for f in as_completed(futures):
        if f.result():
            done += 1
        else:
            errors += 1
    
    elapsed = time.time() - t0
    rate = done / elapsed if elapsed > 0 else 0
    pct = done * 100 // total if total else 100
    print(f"\r{done}/{total} ({errors} err) {pct}% {rate:.0f}/s {elapsed:.0f}s", end="", file=sys.stderr)

print(f"\nDone in {time.time()-t0:.0f}s", file=sys.stderr)

# Final count
r = subprocess.run(
    ["curl", "-s", "--max-time", "15", "-X", "POST", URL,
     "-H", f"Authorization: Bearer {TOKEN}",
     "-H", "Content-Type: application/json",
     "-d", '{"requests":[{"type":"execute","stmt":{"sql":"SELECT COUNT(*) AS n FROM papers"}}]}'],
    capture_output=True, text=True)
try:
    d = json.loads(r.stdout)
    print(f"Turso total: {d['results'][0]['response']['result']['rows'][0][0]['value']}", file=sys.stderr)
except:
    pass
