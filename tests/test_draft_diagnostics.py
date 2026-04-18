"""Tests for draft diagnostics registrations.

Covers the two registrations Agent 4 owns:

* ``partial_media_failure`` — any vehicle when ``media_errors`` has non-null entries
* ``media_token_reference`` — article-only, emits ``orphaned_media_spec`` and
  ``broken_media_reference`` codes independently from one registration

The other two registrations (``manual_posting_required``, ``advisory_created``)
are covered elsewhere; we don't re-test them here.
"""

from __future__ import annotations

from social_hook.draft_diagnostics import draft_diagnostics_registry


def _codes(ctx: dict) -> list[str]:
    return [d.code for d in draft_diagnostics_registry.run(ctx)]


def _by_code(ctx: dict) -> dict[str, dict]:
    return {d.code: d.to_dict() for d in draft_diagnostics_registry.run(ctx)}


# ---------------------------------------------------------------------------
# partial_media_failure
# ---------------------------------------------------------------------------


def test_partial_media_failure_no_errors_returns_empty():
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "media_errors": [None, None, None],
        "media_specs": [],
        "content": "",
    }
    assert "partial_media_failure" not in _codes(ctx)


def test_partial_media_failure_empty_list_returns_empty():
    ctx = {
        "vehicle": "single",
        "auto_postable": True,
        "status": "draft",
        "media_errors": [],
        "media_specs": [],
        "content": "",
    }
    assert "partial_media_failure" not in _codes(ctx)


def test_partial_media_failure_missing_key_returns_empty():
    # Registry should treat missing media_errors as no failures
    ctx = {"vehicle": "single", "auto_postable": True, "status": "draft"}
    assert "partial_media_failure" not in _codes(ctx)


def test_partial_media_failure_fires_when_any_error():
    ctx = {
        "vehicle": "single",
        "auto_postable": True,
        "status": "draft",
        "media_errors": [None, "Gemini timeout", None],
        "media_specs": [],
        "content": "",
    }
    diags = _by_code(ctx)
    assert "partial_media_failure" in diags
    d = diags["partial_media_failure"]
    assert d["severity"] == "warning"
    assert d["context"]["failed_indexes"] == [1]
    assert "1 of 3" in d["message"]


def test_partial_media_failure_fires_for_any_vehicle():
    # Same diagnostic for article, thread, single — not gated by vehicle
    for vehicle in ("single", "thread", "article"):
        ctx = {
            "vehicle": vehicle,
            "auto_postable": True,
            "status": "draft",
            "media_errors": ["Adapter crashed"],
            "media_specs": [],
            "content": "",
        }
        assert "partial_media_failure" in _codes(ctx), f"vehicle={vehicle}"


# ---------------------------------------------------------------------------
# media_token_reference — article-only gate
# ---------------------------------------------------------------------------


def test_media_token_reference_non_article_returns_empty():
    # Even with clearly-broken refs on a single-post draft, no diagnostic
    ctx = {
        "vehicle": "single",
        "auto_postable": True,
        "status": "draft",
        "content": "intro ![cap](media:missing_abc) tail",
        "media_specs": [{"id": "media_abc", "tool": "mermaid", "spec": {}}],
        "media_errors": [None],
    }
    codes = _codes(ctx)
    assert "orphaned_media_spec" not in codes
    assert "broken_media_reference" not in codes


def test_media_token_reference_thread_vehicle_returns_empty():
    ctx = {
        "vehicle": "thread",
        "auto_postable": True,
        "status": "draft",
        "content": "1/ intro\n\n2/ ![bad](media:nope)",
        "media_specs": [{"id": "media_solo", "tool": "mermaid", "spec": {}}],
        "media_errors": [None],
    }
    codes = _codes(ctx)
    assert "orphaned_media_spec" not in codes
    assert "broken_media_reference" not in codes


# ---------------------------------------------------------------------------
# media_token_reference — article, independent emissions
# ---------------------------------------------------------------------------


def test_media_token_reference_all_aligned_returns_empty():
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "content": "intro ![cap](media:media_aaa) mid ![d](media:media_bbb) tail",
        "media_specs": [
            {"id": "media_aaa", "tool": "mermaid", "spec": {}},
            {"id": "media_bbb", "tool": "nano_banana_pro", "spec": {}},
        ],
        "media_errors": [None, None],
    }
    codes = _codes(ctx)
    assert "orphaned_media_spec" not in codes
    assert "broken_media_reference" not in codes


def test_media_token_reference_orphan_only():
    # spec exists for media_bbb but content never mentions it
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "content": "intro ![cap](media:media_aaa) end",
        "media_specs": [
            {"id": "media_aaa", "tool": "mermaid", "spec": {}},
            {"id": "media_bbb", "tool": "nano_banana_pro", "spec": {}},
        ],
        "media_errors": [None, None],
    }
    diags = _by_code(ctx)
    assert "orphaned_media_spec" in diags
    assert "broken_media_reference" not in diags
    ctx_out = diags["orphaned_media_spec"]["context"]
    assert ctx_out["orphan_ids"] == ["media_bbb"]
    assert ctx_out["orphan_indexes"] == [1]


def test_media_token_reference_broken_only():
    # content references media_xxx but no spec exists
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "content": "intro ![cap](media:media_xxx) end",
        "media_specs": [],
        "media_errors": [],
    }
    diags = _by_code(ctx)
    assert "broken_media_reference" in diags
    assert "orphaned_media_spec" not in diags
    assert diags["broken_media_reference"]["context"]["broken_ids"] == ["media_xxx"]


def test_media_token_reference_orphan_and_broken_independent():
    # Both codes emitted from the single registration entry
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "content": "intro ![x](media:missing_xyz) text",
        "media_specs": [{"id": "media_orphan", "tool": "mermaid", "spec": {}}],
        "media_errors": [None],
    }
    diags = _by_code(ctx)
    assert "orphaned_media_spec" in diags
    assert "broken_media_reference" in diags
    assert diags["orphaned_media_spec"]["context"]["orphan_ids"] == ["media_orphan"]
    assert diags["broken_media_reference"]["context"]["broken_ids"] == ["missing_xyz"]


def test_media_token_reference_empty_content_with_specs_is_orphan():
    # Article with specs but no content at all → all specs are orphans
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
        "content": "",
        "media_specs": [{"id": "media_only", "tool": "mermaid", "spec": {}}],
        "media_errors": [None],
    }
    diags = _by_code(ctx)
    assert "orphaned_media_spec" in diags
    assert "broken_media_reference" not in diags


def test_media_token_reference_missing_keys_safe():
    # Registry + pure function must handle missing content + specs
    ctx = {
        "vehicle": "article",
        "auto_postable": False,
        "status": "draft",
    }
    codes = _codes(ctx)
    assert "orphaned_media_spec" not in codes
    assert "broken_media_reference" not in codes


def test_media_token_reference_returns_list_not_none():
    # Defensive: explicit return [] on non-article path, not None
    from social_hook.draft_diagnostics import _check_media_token_reference

    out = _check_media_token_reference({"vehicle": "single"})
    assert out == []
    assert isinstance(out, list)


def test_partial_media_failure_returns_list_not_none():
    from social_hook.draft_diagnostics import _check_partial_media_failure

    out = _check_partial_media_failure({"media_errors": []})
    assert out == []
    assert isinstance(out, list)
