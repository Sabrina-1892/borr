# BORR - Bangladesh Open Research Repository

**"Research for a Better Bangladesh."**

BORR is an open-source, metadata-only repository indexing research papers by Bangladeshi authors, institutions, or about Bangladesh. It functions like Google Scholar scoped to Bangladesh, aiming to centralize and make discoverable the nation's research output.

## Features
- **Centralized Search**: Search by title, author, institution, and keyword across all Bangladeshi research.
- **Automated Harvester**: Operator-run indexing from OpenAlex and other scholarly APIs.
- **Community Submissions**: Researchers can submit their DOIs to have their work indexed.
- **Open Metadata**: Metadata is free and open to all (CC0).
- **Structured Metadata**: Semantic HTML and Schema.org markup on paper records.

## Tech Stack
- Next.js 16 (App Router)
- Tailwind CSS
- Turso/libSQL (SQLite + FTS5)
- Python (Harvester Script)

## Local Setup

### 1. Prerequisites
- Node.js 20+
- Python 3.11+
- A Turso database

### 2. Install Dependencies
```bash
npm install
```

### 3. Environment Variables
Copy the example file and populate it with your Turso credentials:
```bash
cp .env.example .env.local
```
Add:
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `BORR_SEARCH_ENABLED=0` (safe default; set to `1` only after the production migration below)
- `ADMIN_SECRET_KEY`

### 4. Database Setup
For a fresh database, apply `turso/schema.sql`.

For the existing `borr-v2` production database, keep public search disabled and run:

```bash
npm run migrate:read-quota
```

The runner refuses any database URL that does not contain `borr-v2`. The migration adds filter/sort indexes, rebuilds the tiny `paper_stats` aggregate, and prevents non-search updates from rebuilding FTS rows.

### 5. Run Development Server
```bash
npm run dev
```

## Turso Read-Quota Safety

BORR is designed for a low-traffic deployment on Turso's free allowance:

- A naked `/search` request never queries the database.
- Next.js prefetch is disabled on database-backed links; standard browser prefetch requests are rejected by `proxy.ts`.
- Public search is limited to 5 requests per IP per minute and 20 pages.
- Each FTS request selects at most 128 candidate rowids before loading/sorting paper rows.
- Field and affiliation filters require an FTS keyword; they cannot scan the full corpus by themselves.
- Paper data is cached for one day and search responses for ten minutes.
- Crawlers and known scraper user agents are blocked from database-backed routes.

Run the regression suite before deployment:

```bash
npm run lint
npm run test:read-budget
BORR_SEARCH_ENABLED=0 npm run build
npm audit
```

## Contributing
Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to the codebase.

## License
MIT License. The data itself is released under the CC0 Public Domain Dedication.
