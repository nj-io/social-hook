"""Database schema definitions and migrations."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 16

# All DDL statements for initial schema
SCHEMA_DDL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    repo_path             TEXT NOT NULL,
    repo_origin           TEXT,
    summary               TEXT,
    summary_updated_at    TEXT,
    audience_introduced   INTEGER NOT NULL DEFAULT 0,
    paused                INTEGER NOT NULL DEFAULT 0,
    discovery_files       TEXT DEFAULT NULL,
    trigger_branch        TEXT DEFAULT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_origin ON projects(repo_origin);

-- Decisions
CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip', 'imported')),
    reasoning     TEXT NOT NULL,
    angle         TEXT,
    episode_type  TEXT CHECK (episode_type IN ('decision', 'before_after', 'demo_proof', 'milestone', 'postmortem', 'launch', 'synthesis')),
    episode_tags  TEXT DEFAULT '[]',
    post_category TEXT CHECK (post_category IN ('arc', 'opportunistic', 'experiment')),
    arc_id        TEXT REFERENCES arcs(id),
    media_tool    TEXT,
    platforms     TEXT NOT NULL DEFAULT '{}',
    targets       TEXT NOT NULL DEFAULT '{}',
    commit_summary TEXT,
    consolidate_with TEXT,
    branch        TEXT DEFAULT NULL,
    processed     INTEGER NOT NULL DEFAULT 0,
    processed_at  TEXT,
    batch_id      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(project_id, commit_hash)
);

CREATE INDEX IF NOT EXISTS idx_decisions_project_time ON decisions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_commit ON decisions(project_id, commit_hash);
CREATE INDEX IF NOT EXISTS idx_decisions_arc ON decisions(arc_id) WHERE arc_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_unprocessed ON decisions(project_id, created_at)
    WHERE decision = 'hold' AND processed = 0;
CREATE INDEX IF NOT EXISTS idx_decisions_branch ON decisions(project_id, branch)
    WHERE branch IS NOT NULL;

-- Drafts
CREATE TABLE IF NOT EXISTS drafts (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    decision_id     TEXT NOT NULL REFERENCES decisions(id),
    platform        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'posted', 'rejected', 'failed', 'superseded', 'cancelled', 'deferred')),
    content         TEXT NOT NULL,
    media_paths     TEXT NOT NULL DEFAULT '[]',
    media_type      TEXT,
    media_spec      TEXT DEFAULT '{}',
    media_spec_used TEXT,
    suggested_time  TEXT,
    scheduled_time  TEXT,
    reasoning       TEXT,
    superseded_by   TEXT REFERENCES drafts(id),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    is_intro        INTEGER NOT NULL DEFAULT 0,
    post_format     TEXT DEFAULT NULL CHECK (post_format IN ('single', 'thread', 'quote', 'reply')),
    reference_post_id TEXT DEFAULT NULL REFERENCES posts(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;

-- Draft Tweets (Thread Support)
CREATE TABLE IF NOT EXISTS draft_tweets (
    id          TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    media_paths TEXT NOT NULL DEFAULT '[]',
    external_id TEXT,
    posted_at   TEXT,
    error       TEXT,

    UNIQUE(draft_id, position)
);

CREATE INDEX IF NOT EXISTS idx_draft_tweets_draft ON draft_tweets(draft_id, position);
CREATE INDEX IF NOT EXISTS idx_draft_tweets_external ON draft_tweets(external_id) WHERE external_id IS NOT NULL;

-- Draft Changes (Audit Trail)
CREATE TABLE IF NOT EXISTS draft_changes (
    id          TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES drafts(id),
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT NOT NULL CHECK (changed_by IN ('gatekeeper', 'human', 'expert')),
    changed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_draft_changes_draft ON draft_changes(draft_id, changed_at DESC);

-- Posts (Published Content)
CREATE TABLE IF NOT EXISTS posts (
    id           TEXT PRIMARY KEY,
    draft_id     TEXT NOT NULL REFERENCES drafts(id),
    project_id   TEXT NOT NULL REFERENCES projects(id),
    platform     TEXT NOT NULL,
    external_id  TEXT,
    external_url TEXT,
    content      TEXT NOT NULL,
    posted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_project_time ON posts(project_id, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_draft_id ON posts(draft_id);

-- Lifecycles
CREATE TABLE IF NOT EXISTS lifecycles (
    project_id            TEXT PRIMARY KEY REFERENCES projects(id),
    phase                 TEXT NOT NULL DEFAULT 'research' CHECK (phase IN ('research', 'build', 'demo', 'launch', 'post_launch')),
    confidence            REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence              TEXT NOT NULL DEFAULT '[]',
    last_strategy_moment  TEXT,
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Arcs (Narrative Threads)
CREATE TABLE IF NOT EXISTS arcs (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    theme        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
    post_count   INTEGER NOT NULL DEFAULT 0,
    last_post_at TEXT,
    notes        TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at     TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_arcs_project_status ON arcs(project_id, status);

-- Narrative Debt
CREATE TABLE IF NOT EXISTS narrative_debt (
    project_id        TEXT PRIMARY KEY REFERENCES projects(id),
    debt_counter      INTEGER NOT NULL DEFAULT 0,
    last_synthesis_at TEXT
);

-- Usage Log (Token Tracking)
CREATE TABLE IF NOT EXISTS usage_log (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT REFERENCES projects(id),
    operation_type        TEXT NOT NULL,
    model                 TEXT NOT NULL,
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_cents            REAL NOT NULL DEFAULT 0.0,
    commit_hash           TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_project_time ON usage_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_time ON usage_log(created_at DESC);

-- Milestone Summaries (Compacted Historical Context)
CREATE TABLE IF NOT EXISTS milestone_summaries (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    milestone_type  TEXT NOT NULL CHECK (milestone_type IN ('post', 'release', 'weekly', 'monthly')),
    summary         TEXT NOT NULL,
    items_covered   TEXT NOT NULL DEFAULT '[]',  -- JSON array of item IDs
    token_count     INTEGER NOT NULL DEFAULT 0,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_milestone_summaries_project ON milestone_summaries(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_milestone_summaries_type ON milestone_summaries(project_id, milestone_type);

-- Web Events (Web Dashboard Message Store)
CREATE TABLE IF NOT EXISTS web_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL,
    data       TEXT NOT NULL,
    session_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_web_events_created ON web_events(created_at);
CREATE INDEX IF NOT EXISTS idx_web_events_session ON web_events(session_id);

-- Chat Messages (Platform-Agnostic Chat History for LLM Context)
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_lookup
    ON chat_messages(chat_id, created_at DESC);

-- Background Tasks (Long-running operations tracked for web UI)
CREATE TABLE IF NOT EXISTS background_tasks (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    ref_id     TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'running',
    result     TEXT,
    error      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_background_tasks_status ON background_tasks(status);
CREATE INDEX IF NOT EXISTS idx_background_tasks_ref ON background_tasks(type, ref_id, status);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes.

    This is idempotent - safe to run multiple times.
    """
    conn.executescript(SCHEMA_DDL)

    # Record schema version only for brand-new databases.
    # Existing databases (current > 0) get updated by apply_migrations().
    current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]

    if current == 0:
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (SCHEMA_VERSION, "initial_schema"),
        )
        conn.commit()


def _apply_pragma_migration(conn: sqlite3.Connection, sql: str) -> None:
    """Apply a migration containing PRAGMA statements.

    PRAGMA statements must execute outside transactions. This splits them
    from DDL/DML statements and handles each appropriately.
    """
    pragmas_before: list[str] = []
    pragmas_after: list[str] = []
    other_lines: list[str] = []

    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("PRAGMA"):
            # PRAGMAs before DDL go first, PRAGMAs after go last
            if other_lines:
                pragmas_after.append(stripped)
            else:
                pragmas_before.append(stripped)
        else:
            other_lines.append(line)

    # Execute pre-DDL PRAGMAs outside transaction
    for pragma in pragmas_before:
        conn.execute(pragma)

    # Execute DDL/DML as a script
    ddl_sql = "\n".join(other_lines).strip()
    if ddl_sql:
        conn.executescript(ddl_sql)

    # Execute post-DDL PRAGMAs outside transaction
    for pragma in pragmas_after:
        conn.execute(pragma)


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str | Path) -> None:
    """Apply pending migrations from the migrations directory.

    Args:
        conn: Database connection
        migrations_dir: Directory containing .sql migration files
    """
    migrations_dir = Path(migrations_dir)

    if not migrations_dir.exists():
        return

    # Fresh DB: schema_version table doesn't exist yet — nothing to migrate.
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "schema_version" not in tables:
        return

    # Get current version
    current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]

    # Apply pending migrations
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        try:
            version = int(migration_file.stem.split("_")[0])
        except (ValueError, IndexError):
            continue

        if version > current:
            sql = migration_file.read_text()

            # Check if migration contains PRAGMA statements (table rebuild)
            if "PRAGMA" in sql:
                _apply_pragma_migration(conn, sql)
            else:
                conn.executescript(sql)

            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, migration_file.stem),
            )
            conn.commit()
