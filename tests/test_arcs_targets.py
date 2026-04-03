"""Tests for arcs rework: strategy-scoped, proposed lifecycle, reasoning."""

import pytest

from social_hook.db import operations as ops
from social_hook.errors import MaxArcsError
from social_hook.models.core import Project
from social_hook.models.enums import ArcStatus
from social_hook.models.narrative import Arc
from social_hook.narrative.arcs import (
    abandon_arc,
    activate_arc,
    create_arc,
    get_active_arcs,
    get_arc,
    propose_arc,
    resume_arc,
)

# ---------------------------------------------------------------------------
# ArcStatus enum
# ---------------------------------------------------------------------------


def test_arc_status_proposed_exists():
    """PROPOSED is a valid ArcStatus."""
    assert ArcStatus.PROPOSED.value == "proposed"


def test_arc_model_accepts_proposed():
    """Arc dataclass accepts proposed status."""
    arc = Arc(id="a1", project_id="p1", theme="test", status="proposed")
    assert arc.status == "proposed"


# ---------------------------------------------------------------------------
# Arc model: strategy + reasoning fields
# ---------------------------------------------------------------------------


def test_arc_model_strategy_default():
    """Arc strategy defaults to empty string."""
    arc = Arc(id="a1", project_id="p1", theme="test")
    assert arc.strategy == ""


def test_arc_model_reasoning_default():
    """Arc reasoning defaults to None."""
    arc = Arc(id="a1", project_id="p1", theme="test")
    assert arc.reasoning is None


def test_arc_to_dict_includes_new_fields():
    """to_dict() includes strategy and reasoning."""
    arc = Arc(
        id="a1",
        project_id="p1",
        theme="test",
        strategy="brand-primary",
        reasoning="good fit for brand",
    )
    d = arc.to_dict()
    assert d["strategy"] == "brand-primary"
    assert d["reasoning"] == "good fit for brand"


def test_arc_from_dict_with_new_fields():
    """from_dict() extracts strategy and reasoning."""
    d = {
        "id": "a1",
        "project_id": "p1",
        "theme": "test",
        "strategy": "product-news",
        "reasoning": "timely release",
    }
    arc = Arc.from_dict(d)
    assert arc.strategy == "product-news"
    assert arc.reasoning == "timely release"


def test_arc_from_dict_backward_compat():
    """from_dict() works without strategy/reasoning (old rows)."""
    d = {"id": "a1", "project_id": "p1", "theme": "test"}
    arc = Arc.from_dict(d)
    assert arc.strategy == ""
    assert arc.reasoning is None


def test_arc_to_row_includes_new_fields():
    """to_row() includes strategy and reasoning in correct order."""
    arc = Arc(
        id="a1",
        project_id="p1",
        theme="test",
        strategy="brand",
        status="active",
        reasoning="because",
    )
    row = arc.to_row()
    # (id, project_id, theme, strategy, status, reasoning, post_count, last_post_at, notes)
    assert row[0] == "a1"
    assert row[3] == "brand"
    assert row[4] == "active"
    assert row[5] == "because"


# ---------------------------------------------------------------------------
# create_arc: strategy-scoped
# ---------------------------------------------------------------------------


def test_create_arc_with_strategy(temp_db):
    """Create a strategy-scoped arc."""
    ops.insert_project(
        temp_db,
        _make_project("p1"),
    )
    arc_id = create_arc(temp_db, "p1", "OAuth migration", strategy="product-news")
    arc = get_arc(temp_db, arc_id)
    assert arc is not None
    assert arc.strategy == "product-news"
    assert arc.status == "active"


def test_create_arc_default_strategy(temp_db):
    """create_arc() defaults to strategy='' for backward compat."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme A")
    arc = get_arc(temp_db, arc_id)
    assert arc.strategy == ""


# ---------------------------------------------------------------------------
# Max arcs enforced per strategy, not per project
# ---------------------------------------------------------------------------


def test_max_arcs_per_strategy_not_project(temp_db):
    """Can create arcs in different strategies even when one strategy is full."""
    ops.insert_project(temp_db, _make_project("p1"))

    # Fill strategy A
    for i in range(3):
        create_arc(temp_db, "p1", f"A-{i}", strategy="strategy-a")

    # Strategy B should still allow creation
    arc_id = create_arc(temp_db, "p1", "B-0", strategy="strategy-b")
    assert arc_id is not None

    # Strategy A should be full
    with pytest.raises(MaxArcsError):
        create_arc(temp_db, "p1", "A-extra", strategy="strategy-a")


def test_max_arcs_configurable(temp_db):
    """max_arcs parameter controls the limit."""
    ops.insert_project(temp_db, _make_project("p1"))
    create_arc(temp_db, "p1", "T1", strategy="s1", max_arcs=1)
    with pytest.raises(MaxArcsError):
        create_arc(temp_db, "p1", "T2", strategy="s1", max_arcs=1)


# ---------------------------------------------------------------------------
# Proposed -> active -> completed lifecycle
# ---------------------------------------------------------------------------


def test_propose_arc(temp_db):
    """propose_arc() creates an arc with proposed status and reasoning."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = propose_arc(
        temp_db, "p1", "New feature arc", "brand-primary", "Strong brand alignment"
    )
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "proposed"
    assert arc.strategy == "brand-primary"
    assert arc.reasoning == "Strong brand alignment"


def test_activate_proposed_arc(temp_db):
    """activate_arc() moves proposed -> active."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = propose_arc(temp_db, "p1", "Theme", "s1", "reasoning")
    result = activate_arc(temp_db, arc_id)
    assert result is True
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "active"


def test_activate_enforces_max_arcs(temp_db):
    """activate_arc() raises MaxArcsError when limit would be exceeded."""
    ops.insert_project(temp_db, _make_project("p1"))
    # Fill strategy with active arcs
    for i in range(3):
        create_arc(temp_db, "p1", f"Active-{i}", strategy="s1")
    # Propose another
    arc_id = propose_arc(temp_db, "p1", "Extra", "s1", "reason")
    with pytest.raises(MaxArcsError):
        activate_arc(temp_db, arc_id)


def test_activate_non_proposed_raises(temp_db):
    """activate_arc() raises ValueError if arc is not proposed."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Active arc", strategy="s1")
    with pytest.raises(ValueError, match="must be proposed"):
        activate_arc(temp_db, arc_id)


def test_activate_not_found_raises(temp_db):
    """activate_arc() raises ValueError for nonexistent arc."""
    with pytest.raises(ValueError, match="not found"):
        activate_arc(temp_db, "nonexistent")


def test_complete_active_arc(temp_db):
    """Active arc can be completed via update_arc."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme", strategy="s1")
    ops.update_arc(temp_db, arc_id, status="completed")
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "completed"
    assert arc.ended_at is not None


# ---------------------------------------------------------------------------
# Proposed -> abandoned lifecycle
# ---------------------------------------------------------------------------


def test_abandon_proposed_arc(temp_db):
    """abandon_arc() moves proposed -> abandoned."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = propose_arc(temp_db, "p1", "Theme", "s1", "reason")
    result = abandon_arc(temp_db, arc_id)
    assert result is True
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "abandoned"


def test_abandon_active_arc(temp_db):
    """abandon_arc() moves active -> abandoned."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme", strategy="s1")
    result = abandon_arc(temp_db, arc_id)
    assert result is True
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "abandoned"


def test_abandon_already_terminal_raises(temp_db):
    """abandon_arc() raises ValueError for already-terminal arcs."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme", strategy="s1")
    abandon_arc(temp_db, arc_id)
    with pytest.raises(ValueError, match="already"):
        abandon_arc(temp_db, arc_id)


def test_abandon_not_found_raises(temp_db):
    """abandon_arc() raises ValueError for nonexistent arc."""
    with pytest.raises(ValueError, match="not found"):
        abandon_arc(temp_db, "nonexistent")


# ---------------------------------------------------------------------------
# Reasoning stored and retrievable
# ---------------------------------------------------------------------------


def test_reasoning_roundtrip(temp_db):
    """Reasoning survives insert -> read cycle."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = propose_arc(temp_db, "p1", "Theme", "s1", "This is the rationale")
    arc = get_arc(temp_db, arc_id)
    assert arc.reasoning == "This is the rationale"


def test_update_reasoning(temp_db):
    """Reasoning can be updated after creation."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme", strategy="s1")
    ops.update_arc(temp_db, arc_id, reasoning="Updated reason")
    arc = get_arc(temp_db, arc_id)
    assert arc.reasoning == "Updated reason"


# ---------------------------------------------------------------------------
# Backward compat: existing project-scoped arcs still load
# ---------------------------------------------------------------------------


def test_legacy_arcs_load_with_empty_strategy(temp_db):
    """Arcs with strategy='' (legacy) still work via get_active_arcs(strategy=None)."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Legacy theme")
    arcs = get_active_arcs(temp_db, "p1")  # strategy=None -> filters strategy=""
    assert len(arcs) == 1
    assert arcs[0].id == arc_id
    assert arcs[0].strategy == ""


def test_get_active_arcs_filters_by_strategy(temp_db):
    """get_active_arcs with explicit strategy only returns matching arcs."""
    ops.insert_project(temp_db, _make_project("p1"))
    create_arc(temp_db, "p1", "A", strategy="brand")
    create_arc(temp_db, "p1", "B", strategy="product")
    create_arc(temp_db, "p1", "C", strategy="brand")

    brand_arcs = get_active_arcs(temp_db, "p1", strategy="brand")
    assert len(brand_arcs) == 2
    assert all(a.strategy == "brand" for a in brand_arcs)

    product_arcs = get_active_arcs(temp_db, "p1", strategy="product")
    assert len(product_arcs) == 1


def test_get_arcs_by_project_strategy_filter(temp_db):
    """get_arcs_by_project() supports strategy filter."""
    ops.insert_project(temp_db, _make_project("p1"))
    create_arc(temp_db, "p1", "A", strategy="brand")
    create_arc(temp_db, "p1", "B", strategy="product")

    arcs = ops.get_arcs_by_project(temp_db, "p1", strategy="brand")
    assert len(arcs) == 1
    assert arcs[0].strategy == "brand"


# ---------------------------------------------------------------------------
# resume_arc backward compat
# ---------------------------------------------------------------------------


def test_resume_arc_per_strategy(temp_db):
    """resume_arc() enforces max arcs per strategy."""
    ops.insert_project(temp_db, _make_project("p1"))
    # Create and abandon an arc in strategy s1
    arc_id = create_arc(temp_db, "p1", "Abandoned", strategy="s1")
    abandon_arc(temp_db, arc_id)
    # Fill s1
    for i in range(3):
        create_arc(temp_db, "p1", f"Active-{i}", strategy="s1")
    # Should fail to resume
    with pytest.raises(MaxArcsError):
        resume_arc(temp_db, arc_id, "p1", strategy="s1")


def test_resume_arc_backward_compat(temp_db):
    """resume_arc() works with default strategy=''."""
    ops.insert_project(temp_db, _make_project("p1"))
    arc_id = create_arc(temp_db, "p1", "Theme")
    ops.update_arc(temp_db, arc_id, status="abandoned")
    result = resume_arc(temp_db, arc_id, "p1")
    assert result is True
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "active"


# ---------------------------------------------------------------------------
# Proposed arcs not counted toward active limit
# ---------------------------------------------------------------------------


def test_proposed_not_counted_toward_limit(temp_db):
    """Proposed arcs don't count toward the active arc limit."""
    ops.insert_project(temp_db, _make_project("p1"))
    # Create 3 active arcs
    for i in range(3):
        create_arc(temp_db, "p1", f"Active-{i}", strategy="s1")
    # Proposing should still work (proposed != active)
    arc_id = propose_arc(temp_db, "p1", "Proposed", "s1", "reason")
    arc = get_arc(temp_db, arc_id)
    assert arc.status == "proposed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(project_id: str) -> Project:
    return Project(
        id=project_id,
        name=f"Test Project {project_id}",
        repo_path=f"/tmp/{project_id}",
    )
