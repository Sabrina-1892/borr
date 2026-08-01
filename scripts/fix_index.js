import { createClient } from "@libsql/client";

const dbUrl = process.env.TURSO_DATABASE_URL;
const token = process.env.TURSO_AUTH_TOKEN;

if (!dbUrl || !token) {
  console.error("Missing TURSO_DATABASE_URL or TURSO_AUTH_TOKEN in .env.production");
  process.exit(1);
}

const client = createClient({
  url: dbUrl,
  authToken: token,
});

async function main() {
  console.log("Creating missing indexes...");
  
  await client.execute("CREATE INDEX IF NOT EXISTS papers_verified_citations_idx2 ON papers (verified, citation_count DESC, id ASC);");
  await client.execute("CREATE INDEX IF NOT EXISTS papers_verified_year_idx2 ON papers (verified, year DESC, id ASC);");
  await client.execute("CREATE INDEX IF NOT EXISTS papers_verified_id_idx ON papers (verified, id ASC);");
  
  // Update existing index from fix_stats.sql as well just in case
  await client.execute("CREATE INDEX IF NOT EXISTS papers_verified_citations_year_idx2 ON papers (verified, citation_count DESC, year DESC, id ASC);");
  
  console.log("Indexes created successfully! Vercel searches will now be fast.");
}

main().catch(console.error);
