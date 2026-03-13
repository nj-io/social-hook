"""Tests for narrative helpers (T18, T19, T20, T20a, T20b)."""

from datetime import date

import pytest

from social_hook.config.project import (
    StrategyConfig,
    _parse_context_notes,
    _parse_memories,
    load_context_notes,
    save_context_note,
    save_memory,
)
from social_hook.constants import CONFIG_DIR_NAME
from social_hook.db import operations as ops
from social_hook.errors import MaxArcsError
from social_hook.models import Arc, Lifecycle, Project
from social_hook.narrative.arcs import create_arc, get_active_arcs, get_arc, update_arc
from social_hook.narrative.debt import (
    get_narrative_debt,
    increment_narrative_debt,
    is_debt_high,
    reset_narrative_debt,
)
from social_hook.narrative.lifecycle import (
    check_strategy_triggers,
    detect_lifecycle_phase,
    get_audience_introduced,
    record_strategy_moment,
)
from social_hook.narrative.memories import add_memory, parse_memories_file


def _setup_project(conn, project_id="proj_test1"):
    """Helper to insert a test project."""
    project = Project(id=project_id, name="test", repo_path="/tmp/test")
    ops.insert_project(conn, project)
    return project


# =============================================================================
# T18: Lifecycle Phase Detection
# =============================================================================


class TestDetectLifecyclePhase:
    """T18: Phase detection from signals."""

    def test_research_signals(self):
        lifecycle = detect_lifecycle_phase(
            {
                "high_file_churn": True,
                "new_directories": True,
                "docs_heavy": True,
            }
        )
        assert lifecycle.phase == "research"
        assert lifecycle.confidence >= 0.7

    def test_build_signals(self):
        lifecycle = detect_lifecycle_phase(
            {
                "tests_growing": True,
                "architecture_stabilizing": True,
            }
        )
        assert lifecycle.phase == "build"
        assert lifecycle.confidence >= 0.5

    def test_demo_signals(self):
        lifecycle = detect_lifecycle_phase(
            {
                "demo_scripts": True,
                "ux_polish": True,
                "readme_updates": True,
            }
        )
        assert lifecycle.phase == "demo"
        assert lifecycle.confidence >= 0.5

    def test_launch_signals(self):
        lifecycle = detect_lifecycle_phase(
            {
                "release_tags": True,
                "changelog": True,
                "deploy_automation": True,
            }
        )
        assert lifecycle.phase == "launch"
        assert lifecycle.confidence >= 0.7

    def test_post_launch_signals(self):
        lifecycle = detect_lifecycle_phase(
            {
                "bugfixes": True,
                "optimization": True,
            }
        )
        assert lifecycle.phase == "post_launch"
        assert lifecycle.confidence >= 0.5

    def test_no_signals_defaults_to_research(self):
        lifecycle = detect_lifecycle_phase({})
        assert lifecycle.phase == "research"
        assert lifecycle.confidence == 0.3

    def test_evidence_populated(self):
        lifecycle = detect_lifecycle_phase(
            {
                "tests_growing": True,
                "release_tags": True,
            }
        )
        assert "tests_growing" in lifecycle.evidence
        assert "release_tags" in lifecycle.evidence

    def test_confidence_capped_at_one(self):
        # Even with many signals, confidence shouldn't exceed 1.0
        lifecycle = detect_lifecycle_phase(
            {
                "release_tags": True,
                "changelog": True,
                "deploy_automation": True,
            }
        )
        assert lifecycle.confidence <= 1.0


# =============================================================================
# T18: Strategy Triggers
# =============================================================================


class TestStrategyTriggers:
    """T18: Strategy trigger detection."""

    def test_no_triggers_on_fresh_project(self, temp_db):
        _setup_project(temp_db)
        triggers = check_strategy_triggers(temp_db, "proj_test1")
        assert triggers == []

    def test_narrative_debt_trigger(self, temp_db):
        _setup_project(temp_db)
        # Increment debt past threshold (default 3)
        for _ in range(4):
            ops.increment_narrative_debt(temp_db, "proj_test1")

        config = StrategyConfig(narrative_debt_threshold=3)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "narrative_debt_high" in triggers

    def test_narrative_debt_at_threshold_not_triggered(self, temp_db):
        _setup_project(temp_db)
        # Exactly at threshold (3) should not trigger (> not >=)
        for _ in range(3):
            ops.increment_narrative_debt(temp_db, "proj_test1")

        config = StrategyConfig(narrative_debt_threshold=3)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "narrative_debt_high" not in triggers

    def test_arc_stagnation_trigger(self, temp_db):
        _setup_project(temp_db)
        # Create an arc with old last_post_at
        arc = Arc(id="arc_test1", project_id="proj_test1", theme="Test arc")
        ops.insert_arc(temp_db, arc)
        # Set last_post_at to 15 days ago
        temp_db.execute(
            "UPDATE arcs SET last_post_at = datetime('now', '-15 days') WHERE id = ?",
            ("arc_test1",),
        )
        temp_db.commit()

        config = StrategyConfig(arc_stagnation_days=14)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "arc_stagnation" in triggers

    def test_arc_stagnation_null_last_post(self, temp_db):
        """Arc with NULL last_post_at is stagnant (never posted)."""
        _setup_project(temp_db)
        arc = Arc(id="arc_test1", project_id="proj_test1", theme="Test arc")
        ops.insert_arc(temp_db, arc)

        config = StrategyConfig(arc_stagnation_days=14)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "arc_stagnation" in triggers

    def test_time_elapsed_trigger(self, temp_db):
        _setup_project(temp_db)
        # Insert lifecycle with old strategy moment
        lifecycle = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)
        temp_db.execute(
            "UPDATE lifecycles SET last_strategy_moment = datetime('now', '-8 days') WHERE project_id = ?",
            ("proj_test1",),
        )
        temp_db.commit()

        config = StrategyConfig(strategy_moment_max_gap_days=7)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "time_elapsed" in triggers

    def test_time_elapsed_null_strategy_moment(self, temp_db):
        """NULL last_strategy_moment should trigger time_elapsed."""
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        config = StrategyConfig(strategy_moment_max_gap_days=7)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "time_elapsed" in triggers

    def test_phase_transition_trigger(self, temp_db):
        """Phase change with high confidence triggers phase_transition."""
        _setup_project(temp_db)
        # Store current lifecycle as "research"
        lifecycle = Lifecycle(project_id="proj_test1", phase="research", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        # New detection says "build" with high confidence
        new_lc = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        triggers = check_strategy_triggers(
            temp_db,
            "proj_test1",
            new_lifecycle=new_lc,
        )
        assert "phase_transition" in triggers

    def test_phase_transition_low_confidence_no_trigger(self, temp_db):
        """Phase change with low confidence does not trigger."""
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="research", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        new_lc = Lifecycle(project_id="proj_test1", phase="build", confidence=0.5)
        triggers = check_strategy_triggers(
            temp_db,
            "proj_test1",
            new_lifecycle=new_lc,
        )
        assert "phase_transition" not in triggers

    def test_phase_transition_same_phase_no_trigger(self, temp_db):
        """Same phase (even high confidence) does not trigger."""
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        new_lc = Lifecycle(project_id="proj_test1", phase="build", confidence=0.9)
        triggers = check_strategy_triggers(
            temp_db,
            "proj_test1",
            new_lifecycle=new_lc,
        )
        assert "phase_transition" not in triggers

    def test_phase_transition_first_detection(self, temp_db):
        """First lifecycle detection (no stored phase) triggers transition."""
        _setup_project(temp_db)
        # No lifecycle inserted — first detection

        new_lc = Lifecycle(project_id="proj_test1", phase="research", confidence=0.8)
        triggers = check_strategy_triggers(
            temp_db,
            "proj_test1",
            new_lifecycle=new_lc,
        )
        assert "phase_transition" in triggers

    def test_no_new_lifecycle_skips_transition(self, temp_db):
        """Without new_lifecycle parameter, phase_transition not checked."""
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="research", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        triggers = check_strategy_triggers(temp_db, "proj_test1")
        assert "phase_transition" not in triggers

    def test_default_config_used(self, temp_db):
        _setup_project(temp_db)
        # Should work without passing config
        triggers = check_strategy_triggers(temp_db, "proj_test1")
        assert isinstance(triggers, list)


# =============================================================================
# T18: Audience Introduced
# =============================================================================


class TestAudienceIntroduced:
    """T18: Onboarding flag management — per-platform."""

    def test_default_false(self, temp_db):
        _setup_project(temp_db)
        assert get_audience_introduced(temp_db, "proj_test1") is False

    def test_set_true_per_platform(self, temp_db):
        from social_hook.db.operations import get_platform_introduced, set_platform_introduced

        _setup_project(temp_db)
        set_platform_introduced(temp_db, "proj_test1", "x", True)
        assert get_platform_introduced(temp_db, "proj_test1", "x") is True

    def test_set_back_to_false_per_platform(self, temp_db):
        from social_hook.db.operations import (
            get_platform_introduced,
            reset_platform_introduced,
            set_platform_introduced,
        )

        _setup_project(temp_db)
        set_platform_introduced(temp_db, "proj_test1", "x", True)
        reset_platform_introduced(temp_db, "proj_test1", "x")
        assert get_platform_introduced(temp_db, "proj_test1", "x") is False

    def test_nonexistent_project(self, temp_db):
        assert get_audience_introduced(temp_db, "nonexistent") is False

    def test_all_platform_introduced(self, temp_db):
        from social_hook.db.operations import get_all_platform_introduced, set_platform_introduced

        _setup_project(temp_db)
        set_platform_introduced(temp_db, "proj_test1", "x", True)
        set_platform_introduced(temp_db, "proj_test1", "linkedin", False)
        result = get_all_platform_introduced(temp_db, "proj_test1")
        assert result == {"x": True, "linkedin": False}

    def test_compat_audience_introduced_true_when_all(self, temp_db):
        from social_hook.db.operations import set_platform_introduced

        _setup_project(temp_db)
        set_platform_introduced(temp_db, "proj_test1", "x", True)
        assert get_audience_introduced(temp_db, "proj_test1") is True

    def test_compat_audience_introduced_false_when_mixed(self, temp_db):
        from social_hook.db.operations import set_platform_introduced

        _setup_project(temp_db)
        set_platform_introduced(temp_db, "proj_test1", "x", True)
        set_platform_introduced(temp_db, "proj_test1", "linkedin", False)
        assert get_audience_introduced(temp_db, "proj_test1") is False


# =============================================================================
# T19: Arc Management
# =============================================================================


class TestArcs:
    """T19: Arc CRUD with business rules."""

    def test_create_arc(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Building the brain")
        assert arc_id.startswith("arc_")
        arc = get_arc(temp_db, arc_id)
        assert arc is not None
        assert arc.theme == "Building the brain"
        assert arc.status == "active"

    def test_max_three_arcs(self, temp_db):
        _setup_project(temp_db)
        create_arc(temp_db, "proj_test1", "Arc 1")
        create_arc(temp_db, "proj_test1", "Arc 2")
        create_arc(temp_db, "proj_test1", "Arc 3")

        with pytest.raises(MaxArcsError):
            create_arc(temp_db, "proj_test1", "Arc 4")

    def test_completed_arc_allows_new(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Arc 1")
        create_arc(temp_db, "proj_test1", "Arc 2")
        create_arc(temp_db, "proj_test1", "Arc 3")

        # Complete one
        update_arc(temp_db, arc_id, status="completed")

        # Now should be able to create a 4th
        new_id = create_arc(temp_db, "proj_test1", "Arc 4")
        assert new_id.startswith("arc_")

    def test_get_active_arcs(self, temp_db):
        _setup_project(temp_db)
        create_arc(temp_db, "proj_test1", "Active 1")
        create_arc(temp_db, "proj_test1", "Active 2")

        arcs = get_active_arcs(temp_db, "proj_test1")
        assert len(arcs) == 2
        assert all(a.status == "active" for a in arcs)

    def test_get_arc_not_found(self, temp_db):
        assert get_arc(temp_db, "nonexistent") is None

    def test_update_arc_status(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Test arc")
        update_arc(temp_db, arc_id, status="abandoned")

        arc = get_arc(temp_db, arc_id)
        assert arc.status == "abandoned"


# =============================================================================
# T19: Narrative Debt
# =============================================================================


class TestNarrativeDebt:
    """T19: Debt tracking with threshold checks."""

    def test_no_record_returns_zero(self, temp_db):
        _setup_project(temp_db)
        assert get_narrative_debt(temp_db, "proj_test1") == 0

    def test_increment(self, temp_db):
        _setup_project(temp_db)
        result = increment_narrative_debt(temp_db, "proj_test1")
        assert result == 1
        assert get_narrative_debt(temp_db, "proj_test1") == 1

    def test_increment_multiple(self, temp_db):
        _setup_project(temp_db)
        for _ in range(5):
            increment_narrative_debt(temp_db, "proj_test1")
        assert get_narrative_debt(temp_db, "proj_test1") == 5

    def test_reset(self, temp_db):
        _setup_project(temp_db)
        for _ in range(3):
            increment_narrative_debt(temp_db, "proj_test1")
        reset_narrative_debt(temp_db, "proj_test1")
        assert get_narrative_debt(temp_db, "proj_test1") == 0

    def test_is_debt_high_true(self, temp_db):
        _setup_project(temp_db)
        for _ in range(4):
            increment_narrative_debt(temp_db, "proj_test1")
        assert is_debt_high(temp_db, "proj_test1") is True

    def test_is_debt_high_false(self, temp_db):
        _setup_project(temp_db)
        for _ in range(2):
            increment_narrative_debt(temp_db, "proj_test1")
        assert is_debt_high(temp_db, "proj_test1") is False

    def test_is_debt_high_custom_threshold(self, temp_db):
        _setup_project(temp_db)
        for _ in range(2):
            increment_narrative_debt(temp_db, "proj_test1")
        config = StrategyConfig(narrative_debt_threshold=1)
        assert is_debt_high(temp_db, "proj_test1", config) is True


# =============================================================================
# T20: Memories (existing implementation verification)
# =============================================================================


class TestMemories:
    """T20: Verify existing memory implementation in config/project.py."""

    def test_save_memory_creates_file(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        save_memory(project_dir, "Technical post", '"Too formal"', "draft_001")

        memories_path = project_dir / CONFIG_DIR_NAME / "memories.md"
        assert memories_path.exists()
        content = memories_path.read_text()
        assert "Technical post" in content
        assert '"Too formal"' in content
        assert "draft_001" in content

    def test_save_memory_appends(self, temp_dir):
        project_dir = temp_dir / "my-project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)

        save_memory(project_dir, "First", '"feedback1"', "draft_001")
        save_memory(project_dir, "Second", '"feedback2"', "draft_002")

        memories_path = config_dir / "memories.md"
        content = memories_path.read_text()
        assert "First" in content
        assert "Second" in content

    def test_save_memory_caps_at_100(self, temp_dir):
        project_dir = temp_dir / "my-project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)

        for i in range(105):
            save_memory(project_dir, f"memory_{i}", f'"fb_{i}"', f"draft_{i}")

        memories_path = config_dir / "memories.md"
        content = memories_path.read_text()
        memories = _parse_memories(content)
        assert len(memories) == 100
        # Should have the latest (memory_104) and not the oldest (memory_0)
        assert any(m["context"] == "memory_104" for m in memories)
        assert not any(m["context"] == "memory_0" for m in memories)

    def test_parse_memories_from_existing(self, temp_project_dir):
        """Verify parsing existing memories.md."""
        memories_path = temp_project_dir / CONFIG_DIR_NAME / "memories.md"
        content = memories_path.read_text()
        memories = _parse_memories(content)
        assert len(memories) == 1
        assert memories[0]["context"] == "Technical architecture"
        assert memories[0]["feedback"] == '"Too many emojis"'
        assert memories[0]["draft_id"] == "draft-001"

    def test_save_memory_preserves_existing(self, temp_project_dir):
        """New memory added to existing memories.md preserves old entries."""
        save_memory(temp_project_dir, "New post", '"Great job"', "draft_002")

        memories_path = temp_project_dir / CONFIG_DIR_NAME / "memories.md"
        content = memories_path.read_text()
        memories = _parse_memories(content)
        assert len(memories) == 2
        assert memories[0]["context"] == "Technical architecture"
        assert memories[1]["context"] == "New post"


# =============================================================================
# T18: Record Strategy Moment
# =============================================================================


class TestRecordStrategyMoment:
    """T18: Strategy moment recording and time_elapsed trigger reset."""

    def test_record_strategy_moment(self, temp_db):
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        record_strategy_moment(temp_db, "proj_test1")

        # After recording, time_elapsed should not trigger
        config = StrategyConfig(strategy_moment_max_gap_days=7)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "time_elapsed" not in triggers

    def test_record_clears_time_elapsed(self, temp_db):
        """Recording strategy moment clears time_elapsed trigger."""
        _setup_project(temp_db)
        lifecycle = Lifecycle(project_id="proj_test1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        # Set old strategy moment to trigger time_elapsed
        temp_db.execute(
            "UPDATE lifecycles SET last_strategy_moment = datetime('now', '-10 days') "
            "WHERE project_id = ?",
            ("proj_test1",),
        )
        temp_db.commit()

        config = StrategyConfig(strategy_moment_max_gap_days=7)
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "time_elapsed" in triggers

        # Record strategy moment
        record_strategy_moment(temp_db, "proj_test1")

        # Should no longer trigger
        triggers = check_strategy_triggers(temp_db, "proj_test1", config)
        assert "time_elapsed" not in triggers


# =============================================================================
# T20a: Project Summary Integration
# =============================================================================


class TestProjectSummaryIntegration:
    """T20a: Summary freshness and update integration with DB operations."""

    def test_summary_freshness_fresh_project(self, temp_db):
        """Fresh project returns None/zero freshness indicators."""
        _setup_project(temp_db)
        freshness = ops.get_summary_freshness(temp_db, "proj_test1")
        assert freshness["commits_since_summary"] == 0

    def test_summary_roundtrip(self, temp_db):
        """Update and retrieve project summary."""
        _setup_project(temp_db)
        assert ops.get_project_summary(temp_db, "proj_test1") is None

        ops.update_project_summary(temp_db, "proj_test1", "A CLI tool for devs.")
        summary = ops.get_project_summary(temp_db, "proj_test1")
        assert summary == "A CLI tool for devs."

    def test_summary_update_resets_freshness(self, temp_db):
        """Updating summary resets the freshness counter."""
        _setup_project(temp_db)
        ops.update_project_summary(temp_db, "proj_test1", "Initial summary.")

        freshness = ops.get_summary_freshness(temp_db, "proj_test1")
        assert freshness["days_since_summary"] == 0


# =============================================================================
# T20b: Milestone Summaries Integration
# =============================================================================


class TestMilestoneSummariesIntegration:
    """T20b: Milestone summary insertion and retrieval."""

    def test_insert_and_get_milestone(self, temp_db):
        from social_hook.filesystem import generate_id

        _setup_project(temp_db)
        summary = {
            "id": generate_id("ms"),
            "project_id": "proj_test1",
            "milestone_type": "post",
            "summary": "First post about auth module.",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
        }
        ms_id = ops.insert_milestone_summary(temp_db, summary)
        assert ms_id.startswith("ms_")

        summaries = ops.get_milestone_summaries(temp_db, "proj_test1")
        assert len(summaries) == 1
        assert summaries[0]["summary"] == "First post about auth module."

    def test_get_milestone_empty(self, temp_db):
        _setup_project(temp_db)
        summaries = ops.get_milestone_summaries(temp_db, "proj_test1")
        assert summaries == []


# =============================================================================
# Memories Wrapper (narrative.memories module)
# =============================================================================


class TestMemoriesWrapper:
    """Tests for the narrative.memories thin wrapper module."""

    def test_add_memory_creates_file(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        add_memory(project_dir, "Technical post", '"Too formal"', "draft_001")

        memories_path = project_dir / CONFIG_DIR_NAME / "memories.md"
        assert memories_path.exists()
        content = memories_path.read_text()
        assert "Technical post" in content

    def test_parse_memories_file_returns_list(self, temp_project_dir):
        memories = parse_memories_file(temp_project_dir)
        assert len(memories) == 1
        assert memories[0]["context"] == "Technical architecture"

    def test_parse_memories_file_missing_returns_empty(self, temp_dir):
        project_dir = temp_dir / "empty-project"
        project_dir.mkdir()
        memories = parse_memories_file(project_dir)
        assert memories == []

    def test_add_then_parse_roundtrip(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        add_memory(project_dir, "First", '"fb1"', "draft_001")
        add_memory(project_dir, "Second", '"fb2"', "draft_002")

        memories = parse_memories_file(project_dir)
        assert len(memories) == 2
        assert memories[0]["context"] == "First"
        assert memories[1]["context"] == "Second"

    def test_importable_from_narrative(self):
        """Verify imports work from social_hook.narrative."""
        from social_hook.narrative import add_memory, parse_memories_file

        assert callable(add_memory)
        assert callable(parse_memories_file)


# =============================================================================
# Context Notes Persistence
# =============================================================================


class TestContextNotes:
    """Tests for context note save/load functions."""

    def test_save_context_note_creates_file(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        save_context_note(project_dir, "User prefers casual tone", "expert:draft_001")

        notes_path = project_dir / CONFIG_DIR_NAME / "context-notes.md"
        assert notes_path.exists()
        content = notes_path.read_text()
        assert "User prefers casual tone" in content
        assert "expert:draft_001" in content

    def test_save_context_note_appends(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        save_context_note(project_dir, "Note 1", "expert:draft_001")
        save_context_note(project_dir, "Note 2", "expert:draft_002")

        notes = load_context_notes(project_dir)
        assert len(notes) == 2
        assert notes[0]["note"] == "Note 1"
        assert notes[1]["note"] == "Note 2"

    def test_load_context_notes_missing_returns_empty(self, temp_dir):
        project_dir = temp_dir / "empty-project"
        project_dir.mkdir()
        notes = load_context_notes(project_dir)
        assert notes == []

    def test_save_context_note_caps_at_50(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        for i in range(55):
            save_context_note(project_dir, f"note_{i}", f"expert:draft_{i}")

        notes = load_context_notes(project_dir)
        assert len(notes) == 50
        # Should have the latest (note_54) and not the oldest (note_0)
        assert any(n["note"] == "note_54" for n in notes)
        assert not any(n["note"] == "note_0" for n in notes)

    def test_parse_context_notes_from_content(self):
        content = """\
# Context Notes

| Date | Note | Source |
|------|------|--------|
| 2026-01-30 | Prefers casual tone | expert:draft_001 |
| 2026-01-31 | Avoid jargon | expert:draft_002 |
"""
        notes = _parse_context_notes(content)
        assert len(notes) == 2
        assert notes[0]["note"] == "Prefers casual tone"
        assert notes[1]["source"] == "expert:draft_002"

    def test_context_note_has_date(self, temp_dir):
        project_dir = temp_dir / "my-project"
        project_dir.mkdir()

        save_context_note(project_dir, "Test note", "expert:draft_001")

        notes = load_context_notes(project_dir)
        assert notes[0]["date"] == date.today().isoformat()
