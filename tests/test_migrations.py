"""Tests for social_hook.migrations — generic SQL migration runner."""

import sqlite3

import pytest

from social_hook.migrations import (
    apply_sql_migrations,
    ensure_version_table,
    get_current_version,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def migrations_dir(tmp_path):
    return tmp_path


class TestEnsureVersionTable:
    def test_creates_table(self, db):
        ensure_version_table(db)
        tables = {
            r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "schema_version" in tables

    def test_idempotent(self, db):
        ensure_version_table(db)
        ensure_version_table(db)  # Should not raise

    def test_custom_table_name(self, db):
        ensure_version_table(db, version_table="my_versions")
        tables = {
            r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "my_versions" in tables


class TestGetCurrentVersion:
    def test_no_table_returns_zero(self, db):
        assert get_current_version(db) == 0

    def test_empty_table_returns_zero(self, db):
        ensure_version_table(db)
        assert get_current_version(db) == 0

    def test_returns_max_version(self, db):
        ensure_version_table(db)
        db.execute("INSERT INTO schema_version (version, description) VALUES (5, 'v5')")
        db.execute("INSERT INTO schema_version (version, description) VALUES (10, 'v10')")
        db.commit()
        assert get_current_version(db) == 10


class TestApplySqlMigrations:
    def test_applies_in_order(self, db, migrations_dir):
        ensure_version_table(db)

        (migrations_dir / "001_create_users.sql").write_text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
        )
        (migrations_dir / "002_add_email.sql").write_text(
            "ALTER TABLE users ADD COLUMN email TEXT;"
        )

        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 2

        # Verify tables exist
        cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
        assert "name" in cols
        assert "email" in cols

        # Verify versions recorded
        assert get_current_version(db) == 2

    def test_skips_already_applied(self, db, migrations_dir):
        ensure_version_table(db)
        db.execute("INSERT INTO schema_version (version, description) VALUES (1, 'v1')")
        db.commit()

        (migrations_dir / "001_old.sql").write_text("CREATE TABLE old (id INTEGER);")
        (migrations_dir / "002_new.sql").write_text("CREATE TABLE new (id INTEGER);")

        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 1

        tables = {
            r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "new" in tables
        assert "old" not in tables

    def test_no_migrations_dir(self, db, tmp_path):
        ensure_version_table(db)
        applied = apply_sql_migrations(db, tmp_path / "nonexistent")
        assert applied == 0

    def test_no_version_table(self, db, migrations_dir):
        (migrations_dir / "001_test.sql").write_text("CREATE TABLE t (id INTEGER);")
        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 0

    def test_skips_non_numeric_files(self, db, migrations_dir):
        ensure_version_table(db)
        (migrations_dir / "readme.sql").write_text("-- not a migration")
        (migrations_dir / "001_real.sql").write_text("CREATE TABLE t (id INTEGER);")

        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 1

    def test_timestamp_prefix(self, db, migrations_dir):
        ensure_version_table(db)
        (migrations_dir / "20260328120000_add_feature.sql").write_text(
            "CREATE TABLE feature (id INTEGER PRIMARY KEY);"
        )

        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 1
        assert get_current_version(db) == 20260328120000

    def test_pragma_migration(self, db, migrations_dir):
        ensure_version_table(db)

        # Create initial table
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        db.commit()

        # Migration with PRAGMA (table rebuild pattern)
        (migrations_dir / "001_rebuild.sql").write_text(
            "PRAGMA foreign_keys = OFF;\n"
            "CREATE TABLE items_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
            "INSERT INTO items_new SELECT * FROM items;\n"
            "DROP TABLE items;\n"
            "ALTER TABLE items_new RENAME TO items;\n"
            "PRAGMA foreign_keys = ON;\n"
        )

        applied = apply_sql_migrations(db, migrations_dir)
        assert applied == 1

    def test_custom_version_table(self, db, migrations_dir):
        ensure_version_table(db, version_table="my_v")
        (migrations_dir / "001_test.sql").write_text("CREATE TABLE t (id INTEGER);")

        applied = apply_sql_migrations(db, migrations_dir, version_table="my_v")
        assert applied == 1
        assert get_current_version(db, version_table="my_v") == 1
