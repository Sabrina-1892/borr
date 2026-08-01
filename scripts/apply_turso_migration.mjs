#!/usr/bin/env node
// Apply a reviewed SQL migration to BORR production.
// Usage: TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... node scripts/apply_turso_migration.mjs [sql-file]

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createClient } from "@libsql/client";

const url = process.env.TURSO_DATABASE_URL || "";
const authToken = process.env.TURSO_AUTH_TOKEN || "";
const migrationPath = resolve(process.argv[2] || "turso/read_quota_hardening.sql");

if (!url || !authToken) {
  throw new Error("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required");
}
if (!url.toLowerCase().includes("borr-v2")) {
  throw new Error("Refusing migration: TURSO_DATABASE_URL is not the borr-v2 database");
}

const sql = await readFile(migrationPath, "utf8");
if (!sql.includes("BEGIN;") || !sql.includes("COMMIT;")) {
  throw new Error("Refusing migration without explicit BEGIN/COMMIT transaction");
}

const client = createClient({ url, authToken });
try {
  await client.executeMultiple(sql);
  console.log(`Applied migration to borr-v2: ${migrationPath}`);
} finally {
  client.close();
}
