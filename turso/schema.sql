-- Migration: BORR Turso Schema
-- Description: Creates the papers table, FTS index, and triggers for BORR.

-- Create Papers Table
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY, -- UUIDs stored as hex strings
    openalex_id TEXT UNIQUE,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]', -- JSON array
    abstract TEXT,
    doi TEXT,
    url TEXT,
    journal TEXT,
    year INTEGER,
    institution TEXT DEFAULT '[]', -- JSON array
    fields TEXT DEFAULT '[]', -- JSON array
    paper_type TEXT DEFAULT 'Other' CHECK (paper_type IN ('Journal Article', 'Review', 'Conference', 'Preprint', 'Thesis', 'Book Chapter', 'Other')),
    access_type TEXT DEFAULT 'Unknown' CHECK (access_type IN ('Open Access', 'Free', 'Paywalled', 'Unknown')),
    source TEXT DEFAULT 'Manual' CHECK (source IN ('OpenAlex', 'PubMed', 'Crossref', 'Manual', 'Community', 'Institutional Feed', 'Semantic Scholar', 'arXiv', 'DOAJ', 'BASE')),
    verified INTEGER DEFAULT 0 CHECK (verified IN (0, 1)),
    citation_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    external_ids TEXT NOT NULL DEFAULT '{}', -- JSON object
    sources TEXT NOT NULL DEFAULT '[]', -- JSON array
    last_harvested_at TEXT,
    authors_text TEXT, -- Space-separated author names for FTS
    institution_text TEXT -- Space-separated institution names for search
);

-- Indexes
CREATE INDEX IF NOT EXISTS papers_verified_year_idx ON papers (verified, year DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_verified_citations_idx ON papers (verified, citation_count DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_doi_lower_idx ON papers (lower(doi)) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS papers_verified_paper_type_idx ON papers (verified, paper_type, id ASC);
CREATE INDEX IF NOT EXISTS papers_verified_type_citations_idx ON papers (verified, paper_type, citation_count DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_verified_type_year_idx ON papers (verified, paper_type, year DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_verified_access_citations_idx ON papers (verified, access_type, citation_count DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_verified_access_year_idx ON papers (verified, access_type, year DESC, id ASC);
CREATE INDEX IF NOT EXISTS papers_openalex_short_idx ON papers (replace(openalex_id, 'https://openalex.org/', '')) WHERE openalex_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS papers_verified_id_idx ON papers (verified, id ASC);
CREATE INDEX IF NOT EXISTS papers_unverified_created_idx ON papers (verified, created_at DESC) WHERE verified = 0;

-- Create FTS Virtual Table
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title,
    abstract,
    authors_text,
    content='papers',
    content_rowid='rowid'
);

-- Triggers to keep FTS table in sync
CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, abstract, authors_text)
    VALUES (new.rowid, new.title, new.abstract, new.authors_text);
END;

CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors_text)
    VALUES ('delete', old.rowid, old.title, old.abstract, old.authors_text);
END;

CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE OF title, abstract, authors_text ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors_text)
    VALUES ('delete', old.rowid, old.title, old.abstract, old.authors_text);
    INSERT INTO papers_fts(rowid, title, abstract, authors_text)
    VALUES (new.rowid, new.title, new.abstract, new.authors_text);
END;

-- Trigger to auto-update updated_at on row modification
CREATE TRIGGER IF NOT EXISTS papers_updated_at
AFTER UPDATE OF openalex_id, title, authors, abstract, doi, url, journal, year,
                institution, fields, paper_type, access_type, source, verified,
                citation_count, external_ids, sources, last_harvested_at,
                authors_text, institution_text
ON papers
WHEN NEW.updated_at = OLD.updated_at BEGIN
    UPDATE papers SET updated_at = CURRENT_TIMESTAMP WHERE rowid = new.rowid;
END;

-- Tiny aggregate table used by the homepage and unfiltered result counts. This
-- avoids COUNT(*) over ~443k papers on every cold Vercel function instance.
CREATE TABLE IF NOT EXISTS paper_stats (
    paper_type TEXT PRIMARY KEY,
    total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0)
);

CREATE TRIGGER IF NOT EXISTS update_stats_after_insert
AFTER INSERT ON papers WHEN NEW.verified = 1 BEGIN
    INSERT INTO paper_stats (paper_type, total_count)
    VALUES (coalesce(NEW.paper_type, 'Other'), 1)
    ON CONFLICT(paper_type) DO UPDATE SET total_count = total_count + 1;
END;

CREATE TRIGGER IF NOT EXISTS update_stats_after_delete
AFTER DELETE ON papers WHEN OLD.verified = 1 BEGIN
    UPDATE paper_stats SET total_count = MAX(total_count - 1, 0)
    WHERE paper_type = coalesce(OLD.paper_type, 'Other');
END;

CREATE TRIGGER IF NOT EXISTS update_stats_after_update
AFTER UPDATE OF verified, paper_type ON papers
WHEN OLD.verified != NEW.verified OR coalesce(OLD.paper_type, 'Other') != coalesce(NEW.paper_type, 'Other') BEGIN
    UPDATE paper_stats SET total_count = MAX(total_count - 1, 0)
    WHERE paper_type = coalesce(OLD.paper_type, 'Other') AND OLD.verified = 1;
    INSERT INTO paper_stats (paper_type, total_count)
    SELECT coalesce(NEW.paper_type, 'Other'), 1 WHERE NEW.verified = 1
    ON CONFLICT(paper_type) DO UPDATE SET total_count = total_count + 1;
END;

-- Create Paper Source Records Table
CREATE TABLE IF NOT EXISTS paper_source_records (
    id TEXT PRIMARY KEY,
    paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('OpenAlex', 'PubMed', 'Crossref', 'Semantic Scholar', 'arXiv', 'DOAJ', 'BASE', 'Manual', 'Community', 'Institutional Feed')),
    source_record_id TEXT NOT NULL,
    doi TEXT,
    title TEXT,
    year INTEGER,
    url TEXT,
    raw_metadata TEXT, -- JSON
    harvested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, source_record_id)
);

CREATE INDEX IF NOT EXISTS paper_source_records_paper_id_idx ON paper_source_records (paper_id);
CREATE INDEX IF NOT EXISTS paper_source_records_doi_lower_idx ON paper_source_records (lower(doi)) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS paper_source_records_source_idx ON paper_source_records (source);
