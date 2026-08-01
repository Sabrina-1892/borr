-- BORR production migration: bound filter/sort reads and remove avoidable FTS churn.
--
-- Run ONCE against borr-v2 while BORR_SEARCH_ENABLED=0. Index creation and the
-- paper_stats rebuild intentionally read the corpus once during maintenance;
-- afterward public requests use point/range lookups instead of corpus scans.
-- Do not run this against the empty local borr.db or the obsolete `borr` name.

BEGIN;

CREATE INDEX IF NOT EXISTS papers_verified_type_citations_idx
ON papers (verified, paper_type, citation_count DESC, id ASC);

CREATE INDEX IF NOT EXISTS papers_verified_type_year_idx
ON papers (verified, paper_type, year DESC, id ASC);

CREATE INDEX IF NOT EXISTS papers_verified_access_citations_idx
ON papers (verified, access_type, citation_count DESC, id ASC);

CREATE INDEX IF NOT EXISTS papers_verified_access_year_idx
ON papers (verified, access_type, year DESC, id ASC);

CREATE INDEX IF NOT EXISTS papers_unverified_created_idx
ON papers (verified, created_at DESC) WHERE verified = 0;

-- The old trigger rebuilt an FTS row after any UPDATE, including moderation or
-- timestamp-only updates. Restrict it to columns actually indexed by FTS.
DROP TRIGGER IF EXISTS papers_au;
CREATE TRIGGER papers_au
AFTER UPDATE OF title, abstract, authors_text ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors_text)
    VALUES ('delete', old.rowid, old.title, old.abstract, old.authors_text);
    INSERT INTO papers_fts(rowid, title, abstract, authors_text)
    VALUES (new.rowid, new.title, new.abstract, new.authors_text);
END;

-- Timestamp maintenance no longer recursively invokes the FTS trigger.
DROP TRIGGER IF EXISTS papers_updated_at;
CREATE TRIGGER papers_updated_at
AFTER UPDATE OF openalex_id, title, authors, abstract, doi, url, journal, year,
                institution, fields, paper_type, access_type, source, verified,
                citation_count, external_ids, sources, last_harvested_at,
                authors_text, institution_text
ON papers
WHEN NEW.updated_at = OLD.updated_at BEGIN
    UPDATE papers SET updated_at = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid;
END;

CREATE TABLE IF NOT EXISTS paper_stats (
    paper_type TEXT PRIMARY KEY,
    total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0)
);

-- One controlled aggregate scan replaces COUNT(*) calls on public requests.
DELETE FROM paper_stats;
INSERT INTO paper_stats (paper_type, total_count)
SELECT coalesce(paper_type, 'Other'), count(*)
FROM papers
WHERE verified = 1
GROUP BY coalesce(paper_type, 'Other');

DROP TRIGGER IF EXISTS update_stats_after_insert;
CREATE TRIGGER update_stats_after_insert
AFTER INSERT ON papers WHEN NEW.verified = 1 BEGIN
    INSERT INTO paper_stats (paper_type, total_count)
    VALUES (coalesce(NEW.paper_type, 'Other'), 1)
    ON CONFLICT(paper_type) DO UPDATE SET total_count = total_count + 1;
END;

DROP TRIGGER IF EXISTS update_stats_after_delete;
CREATE TRIGGER update_stats_after_delete
AFTER DELETE ON papers WHEN OLD.verified = 1 BEGIN
    UPDATE paper_stats SET total_count = MAX(total_count - 1, 0)
    WHERE paper_type = coalesce(OLD.paper_type, 'Other');
END;

DROP TRIGGER IF EXISTS update_stats_after_update;
CREATE TRIGGER update_stats_after_update
AFTER UPDATE OF verified, paper_type ON papers
WHEN OLD.verified != NEW.verified
  OR coalesce(OLD.paper_type, 'Other') != coalesce(NEW.paper_type, 'Other') BEGIN
    UPDATE paper_stats SET total_count = MAX(total_count - 1, 0)
    WHERE paper_type = coalesce(OLD.paper_type, 'Other') AND OLD.verified = 1;
    INSERT INTO paper_stats (paper_type, total_count)
    SELECT coalesce(NEW.paper_type, 'Other'), 1 WHERE NEW.verified = 1
    ON CONFLICT(paper_type) DO UPDATE SET total_count = total_count + 1;
END;

COMMIT;
