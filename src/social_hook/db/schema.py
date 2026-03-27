"""Database schema definitions and migrations."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 20260326071918

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
    paused                INTEGER NOT NULL DEFAULT 0,
    discovery_files       TEXT DEFAULT NULL,
    prompt_docs           TEXT DEFAULT NULL,
    trigger_branch        TEXT DEFAULT NULL,
    brief_section_metadata TEXT DEFAULT '{}',
    analysis_commit_count INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_origin ON projects(repo_origin);

-- Per-platform introduction tracking
CREATE TABLE IF NOT EXISTS platform_introduced (
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    platform            TEXT NOT NULL,
    introduced          INTEGER NOT NULL DEFAULT 0,
    introduced_at       TEXT,
    PRIMARY KEY (project_id, platform)
);

-- Decisions
CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip', 'imported', 'deferred_eval', 'evaluating')),
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
    reference_posts TEXT DEFAULT NULL,
    branch        TEXT DEFAULT NULL,
    trigger_source TEXT DEFAULT 'commit',
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
CREATE INDEX IF NOT EXISTS idx_decisions_deferred ON decisions(project_id, created_at)
    WHERE decision = 'deferred_eval' AND processed = 0;

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
    target_id       TEXT,
    evaluation_cycle_id TEXT,
    topic_id        TEXT,
    suggestion_id   TEXT,
    pattern_id      TEXT,
    preview_mode    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_target ON drafts(target_id) WHERE target_id IS NOT NULL;

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
    target_id    TEXT,
    topic_tags   TEXT DEFAULT '[]',
    feature_tags TEXT DEFAULT '[]',
    is_thread_head INTEGER DEFAULT 0,
    posted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_project_time ON posts(project_id, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_target ON posts(target_id) WHERE target_id IS NOT NULL;
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
    strategy     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('proposed', 'active', 'completed', 'abandoned')),
    reasoning    TEXT,
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
    trigger_source        TEXT DEFAULT 'auto',
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

-- File Summaries (Per-file Discovery Summaries)
CREATE TABLE IF NOT EXISTS file_summaries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_path  TEXT NOT NULL,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_file_summaries_project ON file_summaries(project_id);

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

-- OAuth 2.0 token storage (per-account user tokens)
CREATE TABLE IF NOT EXISTS oauth_tokens (
    account_name TEXT PRIMARY KEY,
    platform     TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);


-- Content topic queue
CREATE TABLE IF NOT EXISTS content_topics (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    strategy TEXT NOT NULL,
    topic TEXT NOT NULL,
    description TEXT,
    priority_rank INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'uncovered'
        CHECK (status IN ('uncovered', 'holding', 'partial', 'covered', 'dismissed')),
    commit_count INTEGER NOT NULL DEFAULT 0,
    last_commit_at TEXT,
    last_posted_at TEXT,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Operator content suggestions
CREATE TABLE IF NOT EXISTS content_suggestions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    strategy TEXT,
    idea TEXT NOT NULL,
    media_refs TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'evaluated', 'drafted', 'dismissed')),
    source TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT DEFAULT (datetime('now')),
    evaluated_at TEXT
);

-- Evaluation cycle grouping
CREATE TABLE IF NOT EXISTS evaluation_cycles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    trigger_type TEXT NOT NULL,
    trigger_ref TEXT,
    commit_analysis_id TEXT,
    commit_analysis_json TEXT DEFAULT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Observational content format patterns
CREATE TABLE IF NOT EXISTS draft_patterns (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    pattern_name TEXT NOT NULL,
    description TEXT,
    example_draft_id TEXT,
    created_by TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Topic-commit junction (which commits contributed to each topic)
CREATE TABLE IF NOT EXISTS topic_commits (
    topic_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    matched_tag TEXT,
    matched_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (topic_id, commit_hash)
);

-- System error persistence
CREATE TABLE IF NOT EXISTS system_errors (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    message TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    source TEXT DEFAULT '',
    component TEXT DEFAULT '',
    run_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_system_errors_severity ON system_errors(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_errors_component ON system_errors(component, created_at DESC);
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


# Mapping from old sequential versions to their timestamp equivalents.
_SEQ_TO_TIMESTAMP: dict[int, tuple[int, str]] = {
    3: (20260209131940, "20260209131940_add_paused"),
    4: (20260210092556, "20260210092556_add_usage_commit_hash"),
    5: (20260220040116, "20260220040116_add_media_fields"),
    6: (20260221002005, "20260221002005_add_web_events"),
    7: (20260221030802, "20260221030802_add_commit_message"),
    8: (20260225034301, "20260225034301_add_chat_messages"),
    9: (20260226010320, "20260226010320_add_consolidation_fields"),
    10: (20260226135811, "20260226135811_add_web_events_session_id"),
    11: (20260226135812, "20260226135812_add_discovery_files"),
    12: (20260227023135, "20260227023135_add_trigger_branch"),
    13: (20260305052203, "20260305052203_evaluator_rework"),
    14: (20260305102638, "20260305102638_add_media_spec_used"),
    15: (20260306065100, "20260306065100_add_background_tasks"),
    16: (20260308160115, "20260308160115_add_deferred_status"),
    17: (20260310125911, "20260310125911_add_decision_reference_posts"),
    18: (20260312132055, "20260312132055_add_file_summaries"),
    19: (20260313060258, "20260313060258_rate_limits_and_merge"),
}

# 016_add_decision_branch_and_imported shares seq 16 with deferred_status.
# Both were applied when seq 16 was current, so both need timestamp entries.
_SEQ_16_EXTRA = (20260308160114, "20260308160114_add_decision_branch_and_imported")


def _bridge_to_timestamp_versions(conn: sqlite3.Connection, current_seq: int) -> None:
    """One-time bridge from sequential (3-19) to timestamp version numbers."""
    for seq_ver in range(3, current_seq + 1):
        if seq_ver not in _SEQ_TO_TIMESTAMP:
            continue
        ts_ver, desc = _SEQ_TO_TIMESTAMP[seq_ver]
        exists = conn.execute(
            "SELECT 1 FROM schema_version WHERE version = ?", (ts_ver,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (ts_ver, desc),
            )
        # Insert the extra 016 migration too
        if seq_ver == 16:
            ts_extra, desc_extra = _SEQ_16_EXTRA
            exists_extra = conn.execute(
                "SELECT 1 FROM schema_version WHERE version = ?", (ts_extra,)
            ).fetchone()
            if not exists_extra:
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (ts_extra, desc_extra),
                )
    conn.commit()


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

    # Bridge: migrate from sequential (3-19) to timestamp versioning.
    # If max version is sequential (<1000), map old versions to their
    # timestamp equivalents so renamed migrations aren't re-applied.
    if 0 < current < 1000:
        _bridge_to_timestamp_versions(conn, current)
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
