#!/usr/bin/env python3
"""Generate batched INSERT SQL from local borr.db to stdout."""
import sqlite3, sys

def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    s = str(v)
    return "'" + s.replace("'", "''") + "'"

conn = sqlite3.connect("/Users/nehalhasnain/Desktop/BORR PROJECT/borr.db")
conn.row_factory = sqlite3.Row

cursor = conn.execute("SELECT *, rowid FROM papers ORDER BY rowid")
columns = [desc[0] for desc in cursor.description if desc[0] != 'rowid']

batch = []
i = 0
for i, row in enumerate(cursor, 1):
    vals = ",".join([q(row[col]) for col in columns])
    batch.append(f"({vals})")
    if len(batch) >= 1000:
        sys.stdout.write("INSERT OR IGNORE INTO papers VALUES " + ",".join(batch) + ";\n")
        batch = []
    if i % 10000 == 0:
        sys.stderr.write(f"  Generated {i:,}...\n")
        sys.stderr.flush()

if batch:
    sys.stdout.write("INSERT OR IGNORE INTO papers VALUES " + ",".join(batch) + ";\n")

conn.close()
sys.stderr.write(f"Done. Total: {i:,} rows.\n")
