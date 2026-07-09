"""Tests for src/social_hook/vehicle.py — vehicle pipeline stage."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from social_hook.adapters.models import (
    ARTICLE,
    SINGLE,
    THREAD,
    PostResult,
)
from social_hook.vehicle import (
    check_auto_postable,
    get_max_media_count,
    materialize_vehicle_artifacts,
    parse_thread_parts,
    post_by_vehicle,
    resolve_vehicle,
    validate_draft_for_vehicle,
)

# ---------------------------------------------------------------------------
# resolve_vehicle
# ---------------------------------------------------------------------------


class TestResolveVehicle:
    def test_operator_choice_takes_priority(self):
        result = resolve_vehicle(
            evaluator_suggestion="single",
            operator_choice="thread",
            platform_capabilities=[SINGLE, THREAD],
        )
        assert result == "thread"

    def test_evaluator_suggestion_used_when_no_operator(self):
        result = resolve_vehicle(
            evaluator_suggestion="thread",
            operator_choice=None,
            platform_capabilities=[SINGLE, THREAD],
        )
        assert result == "thread"

    def test_returns_none_when_neither_set(self):
        result = resolve_vehicle(
            evaluator_suggestion=None,
            operator_choice=None,
            platform_capabilities=[SINGLE, THREAD],
        )
        assert result is None

    def test_unsupported_vehicle_returns_none(self):
        result = resolve_vehicle(
            evaluator_suggestion="thread",
            operator_choice=None,
            platform_capabilities=[SINGLE],
        )
        assert result is None

    def test_article_vehicle_resolved(self):
        result = resolve_vehicle(
            evaluator_suggestion="article",
            operator_choice=None,
            platform_capabilities=[SINGLE, THREAD, ARTICLE],
        )
        assert result == "article"


# ---------------------------------------------------------------------------
# validate_draft_for_vehicle
# ---------------------------------------------------------------------------


class TestValidateDraftForVehicle:
    def test_single_within_limit(self):
        v = validate_draft_for_vehicle("short", "single", "x", 280)
        assert v.valid is True

    def test_single_exceeds_limit_suggests_thread(self):
        v = validate_draft_for_vehicle("x" * 300, "single", "x", 280)
        assert v.valid is False
        assert v.suggested_vehicle == "thread"

    def test_single_exceeds_limit_non_x(self):
        v = validate_draft_for_vehicle("x" * 4000, "single", "linkedin", 3000)
        assert v.valid is False
        assert v.suggested_vehicle is None

    def test_thread_on_non_x_platform(self):
        v = validate_draft_for_vehicle("content", "thread", "linkedin", 3000)
        assert v.valid is False
        assert v.suggested_vehicle == "single"

    def test_thread_with_enough_parts(self):
        content = "1/ First\n\n2/ Second\n\n3/ Third\n\n4/ Fourth"
        v = validate_draft_for_vehicle(content, "thread", "x", 280)
        assert v.valid is True

    def test_thread_with_too_few_parts(self):
        content = "1/ First\n\n2/ Second"
        v = validate_draft_for_vehicle(content, "thread", "x", 280)
        assert v.valid is False
        assert v.suggested_vehicle == "single"

    def test_article_always_valid(self):
        v = validate_draft_for_vehicle("any content", "article", "x", 280)
        assert v.valid is True

    def test_unknown_vehicle_valid(self):
        v = validate_draft_for_vehicle("content", "newsletter", "x", 280)
        assert v.valid is True


# ---------------------------------------------------------------------------
# parse_thread_parts
# ---------------------------------------------------------------------------


class TestParseThreadParts:
    def test_numbered_format(self):
        content = "1/ Hello world\n\n2/ Second tweet\n\n3/ Third\n\n4/ Fourth"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4
        assert parts[0] == "Hello world"

    def test_separator_format(self):
        content = "Part one---Part two---Part three---Part four"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4

    def test_paragraph_format(self):
        content = "Para one\n\nPara two\n\nPara three\n\nPara four"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4

    def test_fallback_single(self):
        parts = parse_thread_parts("short content", "x")
        assert len(parts) == 1
        assert parts[0] == "short content"

    def test_empty_content(self):
        parts = parse_thread_parts("", "x")
        assert parts == []

    def test_custom_thread_min(self):
        content = "1/ A\n\n2/ B\n\n3/ C"
        # With default min=4, this is too few
        parts = parse_thread_parts(content, "x", thread_min=3)
        assert len(parts) == 3


# ---------------------------------------------------------------------------
# materialize_vehicle_artifacts
# ---------------------------------------------------------------------------


class TestMaterializeVehicleArtifacts:
    def test_thread_creates_parts(self):
        db = MagicMock()
        content = "1/ First part\n\n2/ Second part\n\n3/ Third part\n\n4/ Fourth part"
        materialize_vehicle_artifacts(
            "draft-1",
            "thread",
            "x",
            content,
            [SINGLE, THREAD],
            db,
        )
        db.replace_draft_parts.assert_called_once_with("draft-1", [])
        assert db.insert_draft_part.call_count == 4

    def test_single_clears_parts(self):
        db = MagicMock()
        materialize_vehicle_artifacts(
            "draft-1",
            "single",
            "x",
            "hello",
            [SINGLE, THREAD],
            db,
        )
        db.replace_draft_parts.assert_called_once_with("draft-1", [])
        db.insert_draft_part.assert_not_called()

    def test_thread_without_capability_skips(self):
        db = MagicMock()
        content = "1/ A\n\n2/ B\n\n3/ C\n\n4/ D"
        materialize_vehicle_artifacts(
            "draft-1",
            "thread",
            "linkedin",
            content,
            [SINGLE],
            db,
        )
        db.replace_draft_parts.assert_called_once_with("draft-1", [])
        db.insert_draft_part.assert_not_called()


# ---------------------------------------------------------------------------
# post_by_vehicle
# ---------------------------------------------------------------------------


class TestPostByVehicle:
    def _make_adapter(self, caps=None):
        adapter = MagicMock()
        adapter.capabilities.return_value = caps or [SINGLE, THREAD]
        adapter.post.return_value = PostResult(success=True, external_id="ext-1")
        adapter.post_thread.return_value = PostResult(
            success=True,
            part_results=[
                PostResult(success=True, external_id="t-1"),
                PostResult(success=True, external_id="t-2"),
            ],
        )
        return adapter

    def test_single_post(self):
        adapter = self._make_adapter()
        draft = SimpleNamespace(vehicle="single", content="Hello", media_paths=[])
        result = post_by_vehicle(adapter, draft, None, None)
        assert result.success is True
        adapter.post.assert_called_once()

    def test_thread_post(self):
        adapter = self._make_adapter()
        draft = SimpleNamespace(vehicle="thread", content="thread content", media_paths=[])
        parts = [
            SimpleNamespace(id="p1", content="Part 1", media_paths=[]),
            SimpleNamespace(id="p2", content="Part 2", media_paths=[]),
        ]
        db = MagicMock()
        result = post_by_vehicle(adapter, draft, parts, None, db=db)
        assert result.success is True
        adapter.post_thread.assert_called_once()
        assert result.external_id == "t-1"

    def test_advisory_vehicle_safety_net(self):
        """Non-auto-postable vehicles should never reach post_by_vehicle in normal flow.
        If they do, it's a safety net — returns failure with a clear message."""
        adapter = self._make_adapter(caps=[SINGLE, THREAD, ARTICLE])
        draft = SimpleNamespace(vehicle="article", content="long content", media_paths=[])
        result = post_by_vehicle(adapter, draft, None, None)
        assert result.success is False
        assert "not auto-postable" in result.error

    def test_unsupported_vehicle(self):
        adapter = self._make_adapter(caps=[SINGLE])
        draft = SimpleNamespace(vehicle="thread", content="content", media_paths=[])
        result = post_by_vehicle(adapter, draft, None, None)
        assert result.success is False
        assert "Unsupported vehicle" in result.error

    def test_reference_posting(self):
        from social_hook.adapters.models import PostReference, ReferenceType

        adapter = self._make_adapter()
        adapter.supports_reference_type.return_value = True
        adapter.post_with_reference.return_value = PostResult(success=True, external_id="ref-1")
        draft = SimpleNamespace(vehicle="single", content="content", media_paths=[])
        ref = PostReference("ext-123", "https://x.com/123", ReferenceType.QUOTE)
        result = post_by_vehicle(adapter, draft, None, None, reference=ref)
        assert result.success is True
        adapter.post_with_reference.assert_called_once()

    def test_none_vehicle_defaults_to_single(self):
        adapter = self._make_adapter()
        draft = SimpleNamespace(vehicle=None, content="Hello", media_paths=[])
        result = post_by_vehicle(adapter, draft, None, None)
        assert result.success is True
        adapter.post.assert_called_once()


# ---------------------------------------------------------------------------
# check_auto_postable — polymorphic input (Draft | dict | SimpleNamespace)
# ---------------------------------------------------------------------------


class TestCheckAutoPostable:
    def test_accepts_dict(self):
        assert check_auto_postable({"vehicle": "single", "platform": "x"}) is True
        assert check_auto_postable({"vehicle": "article", "platform": "x"}) is False

    def test_accepts_simplenamespace(self):
        assert check_auto_postable(SimpleNamespace(vehicle="single", platform="x")) is True
        assert check_auto_postable(SimpleNamespace(vehicle="article", platform="x")) is False

    def test_accepts_draft_dataclass(self):
        from social_hook.models.core import Draft

        d = Draft(
            id="d1",
            project_id="p",
            decision_id="de",
            platform="x",
            content="hi",
            vehicle="article",
        )
        assert check_auto_postable(d) is False
        d2 = Draft(
            id="d2",
            project_id="p",
            decision_id="de",
            platform="x",
            content="hi",
            vehicle="thread",
        )
        assert check_auto_postable(d2) is True

    def test_empty_dict_defaults_to_single(self):
        assert check_auto_postable({}) is True

    def test_missing_platform_treated_as_empty_string(self):
        # Unknown platform + non-single vehicle: no cap found -> auto_postable
        # (defensive default: True so the scheduler doesn't swallow drafts).
        assert check_auto_postable({"vehicle": "thread"}) is True

    def test_vehicle_none_treated_as_single(self):
        assert check_auto_postable(SimpleNamespace(vehicle=None, platform="x")) is True

    def test_article_on_linkedin_not_auto_postable(self):
        assert check_auto_postable({"vehicle": "article", "platform": "linkedin"}) is False


# ---------------------------------------------------------------------------
# get_max_media_count
# ---------------------------------------------------------------------------


class TestGetMaxMediaCount:
    def test_x_single_is_four(self):
        """X uses SINGLE_X which extends the baseline with MULTI_IMAGE_X(4)."""
        assert get_max_media_count("single", "x") == 4

    def test_x_thread_is_one(self):
        assert get_max_media_count("thread", "x") == 1

    def test_x_article_is_twenty(self):
        assert get_max_media_count("article", "x") == 20

    def test_linkedin_single_is_one(self):
        """LinkedIn uses the universal SINGLE baseline (one image, one GIF)."""
        assert get_max_media_count("single", "linkedin") == 1

    def test_linkedin_article_is_twenty(self):
        assert get_max_media_count("article", "linkedin") == 20

    def test_unknown_platform_defaults_to_one_with_warning(self, caplog):
        import logging

        caplog.set_level(logging.WARNING)
        assert get_max_media_count("single", "bluesky") == 1
        assert any(
            "Unknown" in rec.getMessage() and "bluesky" in rec.getMessage()
            for rec in caplog.records
        )

    def test_unknown_vehicle_defaults_to_one_with_warning(self, caplog):
        import logging

        caplog.set_level(logging.WARNING)
        assert get_max_media_count("nonexistent", "x") == 1
        assert any(
            "Unknown" in rec.getMessage() and "nonexistent" in rec.getMessage()
            for rec in caplog.records
        )

    def test_text_only_capability_returns_zero(self, monkeypatch):
        """A capability declared with empty media_modes reports zero — a
        hypothetical text-only platform must not receive generated media.

        This distinct-from-unknown fallback (0 vs 1) keeps the drafter from
        silently attaching media to a platform that refuses it.
        """
        from social_hook.adapters.models import PostCapability
        from social_hook.config import platforms as plat

        text_only = PostCapability("single", (), "Text-only")
        monkeypatch.setitem(plat.PLATFORM_VEHICLE_SUPPORT, "textonly", [text_only])
        assert get_max_media_count("single", "textonly") == 0
