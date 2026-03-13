"""Tests for cleanup_orphaned_media in filesystem.py."""

import json
import sqlite3

import pytest

from social_hook.filesystem import cleanup_orphaned_media


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    """Set up a fake media-cache directory and a minimal DB."""
    # Override get_base_path to use tmp_path
    monkeypatch.setattr("social_hook.filesystem.get_base_path", lambda: tmp_path)

    media_root = tmp_path / "media-cache"
    media_root.mkdir()

    # Create a minimal in-memory DB with drafts table
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE drafts (
            id TEXT PRIMARY KEY,
            media_paths TEXT
        )
        """
    )
    conn.commit()

    return media_root, conn


def test_no_orphans(media_env):
    """No orphans when all dirs are referenced."""
    media_root, conn = media_env

    # Create a media dir with a file
    d = media_root / "draft_abc123"
    d.mkdir()
    img = d / "image.png"
    img.write_text("fake")

    # Reference it in DB
    conn.execute(
        "INSERT INTO drafts (id, media_paths) VALUES (?, ?)",
        ("draft_abc123", json.dumps([str(img)])),
    )
    conn.commit()

    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert removed == []
    assert d.exists()


def test_orphan_removed(media_env):
    """Unreferenced directories get removed."""
    media_root, conn = media_env

    orphan = media_root / "draft_orphan1"
    orphan.mkdir()
    (orphan / "old.png").write_text("stale")

    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert len(removed) == 1
    assert str(orphan) in removed[0]
    assert not orphan.exists()


def test_dry_run_preserves(media_env):
    """Dry run reports but doesn't delete."""
    media_root, conn = media_env

    orphan = media_root / "draft_dry"
    orphan.mkdir()
    (orphan / "keep.png").write_text("data")

    removed = cleanup_orphaned_media(conn, dry_run=True)
    assert len(removed) == 1
    assert orphan.exists()  # Not deleted


def test_uploads_subdir(media_env):
    """Handles media-cache/uploads/{draft_id}/ paths."""
    media_root, conn = media_env

    uploads = media_root / "uploads"
    uploads.mkdir()

    # Referenced upload
    kept = uploads / "draft_kept"
    kept.mkdir()
    img = kept / "photo.jpg"
    img.write_text("jpeg")
    conn.execute(
        "INSERT INTO drafts (id, media_paths) VALUES (?, ?)",
        ("draft_kept", json.dumps([str(img)])),
    )
    conn.commit()

    # Orphaned upload
    orphan = uploads / "draft_gone"
    orphan.mkdir()
    (orphan / "old.jpg").write_text("stale")

    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert len(removed) == 1
    assert "draft_gone" in removed[0]
    assert kept.exists()
    assert not orphan.exists()


def test_mixed_referenced_and_orphan(media_env):
    """Mix of referenced and orphaned top-level dirs."""
    media_root, conn = media_env

    # Referenced
    ref_dir = media_root / "draft_ref1"
    ref_dir.mkdir()
    ref_file = ref_dir / "out.png"
    ref_file.write_text("ok")
    conn.execute(
        "INSERT INTO drafts (id, media_paths) VALUES (?, ?)",
        ("draft_ref1", json.dumps([str(ref_file)])),
    )

    # Orphan
    orphan = media_root / "draft_orph"
    orphan.mkdir()
    (orphan / "x.png").write_text("gone")

    conn.commit()

    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert len(removed) == 1
    assert ref_dir.exists()
    assert not orphan.exists()


def test_empty_media_cache(media_env):
    """No error when media-cache is empty."""
    _, conn = media_env
    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert removed == []


def test_no_media_cache_dir(tmp_path, monkeypatch):
    """No error when media-cache dir doesn't exist."""
    monkeypatch.setattr("social_hook.filesystem.get_base_path", lambda: tmp_path)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE drafts (id TEXT, media_paths TEXT)")
    removed = cleanup_orphaned_media(conn, dry_run=False)
    assert removed == []
