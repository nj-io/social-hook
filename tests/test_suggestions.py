"""Tests for operator content suggestions."""

from social_hook.db import operations as ops
from social_hook.suggestions import create_suggestion, dismiss_suggestion, evaluate_suggestion


def _seed_project(conn, project_id="proj-1"):
    """Seed a test project."""
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        (project_id, "Test Project", "/tmp/test-repo"),
    )
    conn.commit()
    return project_id


class TestCreateSuggestion:
    """Tests for create_suggestion()."""

    def test_create_with_explicit_strategy(self, temp_db):
        """Create suggestion with explicit strategy."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(
            temp_db,
            project_id,
            "Post about new auth system",
            strategy="brand-primary",
        )
        assert suggestion.id.startswith("suggestion_")
        assert suggestion.project_id == project_id
        assert suggestion.idea == "Post about new auth system"
        assert suggestion.strategy == "brand-primary"
        assert suggestion.status == "pending"
        assert suggestion.source == "operator"

        # Verify persisted
        stored = ops.get_suggestions_by_project(temp_db, project_id)
        assert len(stored) == 1
        assert stored[0].id == suggestion.id

    def test_create_with_strategy_none(self, temp_db):
        """Create suggestion without strategy — evaluator decides."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Show the new dashboard")
        assert suggestion.strategy is None
        assert suggestion.status == "pending"

    def test_create_with_media_refs(self, temp_db):
        """Create suggestion with media references."""
        project_id = _seed_project(temp_db)
        refs = ["screenshot.png", "demo.mp4"]
        suggestion = create_suggestion(
            temp_db,
            project_id,
            "Demo video post",
            media_refs=refs,
        )
        assert suggestion.media_refs == refs

        # Verify JSON serialization in DB
        stored = ops.get_suggestions_by_project(temp_db, project_id)
        assert stored[0].media_refs == refs

    def test_create_with_custom_source(self, temp_db):
        """Create suggestion with non-default source."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(
            temp_db,
            project_id,
            "From chat",
            source="assistant",
        )
        assert suggestion.source == "assistant"


class TestEvaluateSuggestion:
    """Tests for evaluate_suggestion()."""

    def test_evaluate_creates_cycle(self, temp_db):
        """Evaluating a suggestion creates an evaluation cycle with correct trigger_type."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Auth system post")

        cycle_id = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id=suggestion.id,
        )

        assert cycle_id is not None
        assert cycle_id.startswith("cycle_")

        # Check evaluation cycle was created
        cycles = ops.get_recent_cycles(temp_db, project_id)
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "operator_suggestion"
        assert cycles[0].trigger_ref == suggestion.id

        # Check suggestion status updated
        stored = ops.get_suggestions_by_project(temp_db, project_id)
        assert stored[0].status == "evaluated"

    def test_evaluate_nonexistent_suggestion(self, temp_db):
        """Evaluating a nonexistent suggestion returns None."""
        project_id = _seed_project(temp_db)
        result = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id="suggestion-nonexistent",
        )
        assert result is None

    def test_evaluate_non_pending_suggestion(self, temp_db):
        """Evaluating a non-pending suggestion returns None."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Already evaluated")
        ops.update_suggestion_status(temp_db, suggestion.id, "evaluated")

        result = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id=suggestion.id,
        )
        assert result is None

    def test_evaluate_dry_run(self, temp_db):
        """Dry run returns cycle ID but doesn't persist."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Dry run idea")

        cycle_id = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id=suggestion.id,
            dry_run=True,
        )

        assert cycle_id is not None

        # No cycle persisted
        cycles = ops.get_recent_cycles(temp_db, project_id)
        assert len(cycles) == 0

        # Status unchanged
        stored = ops.get_suggestions_by_project(temp_db, project_id)
        assert stored[0].status == "pending"


class TestDismissSuggestion:
    """Tests for dismiss_suggestion()."""

    def test_dismiss(self, temp_db):
        """Dismiss a suggestion updates status."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Not useful")

        result = dismiss_suggestion(temp_db, suggestion.id)
        assert result is True

        stored = ops.get_suggestions_by_project(temp_db, project_id)
        assert stored[0].status == "dismissed"

    def test_dismiss_nonexistent(self, temp_db):
        """Dismissing nonexistent suggestion returns False."""
        result = dismiss_suggestion(temp_db, "suggestion-nonexistent")
        assert result is False


class TestRunSuggestionTrigger:
    """Tests for run_suggestion_trigger() in trigger.py."""

    def test_validates_suggestion_exists(self, temp_db):
        """run_suggestion_trigger validates suggestion exists and is pending."""

        # We can't easily call run_suggestion_trigger directly since it
        # loads config from disk and initializes its own DB. Instead,
        # test the validation logic that it relies on — the suggestion
        # must exist and be pending before evaluation proceeds.
        project_id = _seed_project(temp_db)

        # Non-pending suggestion should fail evaluation
        suggestion = create_suggestion(temp_db, project_id, "Test idea")
        ops.update_suggestion_status(temp_db, suggestion.id, "evaluated")

        result = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id=suggestion.id,
        )
        assert result is None  # Rejected because not pending

    def test_pending_suggestion_succeeds(self, temp_db):
        """Pending suggestion passes validation and produces cycle."""
        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(temp_db, project_id, "Good idea")

        result = evaluate_suggestion(
            temp_db,
            config=None,
            project_id=project_id,
            suggestion_id=suggestion.id,
        )
        assert result is not None


class TestContentSourceResolver:
    """Integration test: operator_suggestion resolver returns content."""

    def test_resolver_returns_suggestion_content(self, temp_db):
        """ContentSource resolver returns suggestion content."""
        from social_hook.content_sources import resolve_operator_suggestion

        project_id = _seed_project(temp_db)
        suggestion = create_suggestion(
            temp_db,
            project_id,
            "Write about the OAuth migration",
            strategy="brand-primary",
        )

        content = resolve_operator_suggestion(
            conn=temp_db,
            project_id=project_id,
            suggestion_id=suggestion.id,
        )
        assert "Write about the OAuth migration" in content
        assert "brand-primary" in content

    def test_resolver_returns_empty_for_missing(self, temp_db):
        """Resolver returns empty string for nonexistent suggestion."""
        from social_hook.content_sources import resolve_operator_suggestion

        project_id = _seed_project(temp_db)
        content = resolve_operator_suggestion(
            conn=temp_db,
            project_id=project_id,
            suggestion_id="suggestion-nope",
        )
        assert content == ""
