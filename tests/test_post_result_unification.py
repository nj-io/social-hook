"""Tests for PostResult absorbing ThreadResult (Phase 1c).

Verifies:
- PostResult.part_results field works correctly
- Each adapter's post_thread() returns PostResult (not ThreadResult)
- Scheduler thread dispatch uses part_results
- dry_run_thread_result returns PostResult with part_results
"""

from unittest.mock import MagicMock, patch

from social_hook.adapters.dry_run import dry_run_thread_result
from social_hook.adapters.models import PostResult

# =============================================================================
# PostResult.part_results field
# =============================================================================


class TestPostResultPartResults:
    """PostResult now carries optional part_results for threads."""

    def test_part_results_defaults_to_none(self):
        """Single-post results have part_results=None."""
        pr = PostResult(success=True, external_id="123")
        assert pr.part_results is None

    def test_part_results_stores_list(self):
        """Thread results carry a list of per-part PostResults."""
        parts = [PostResult(success=True, external_id=f"p{i}") for i in range(4)]
        pr = PostResult(success=True, part_results=parts)
        assert pr.part_results is not None
        assert len(pr.part_results) == 4
        assert pr.part_results[2].external_id == "p2"

    def test_failed_thread_with_partial_results(self):
        """Failed thread carries partial results up to failure point."""
        parts = [
            PostResult(success=True, external_id="ok1"),
            PostResult(success=True, external_id="ok2"),
            PostResult(success=False, error="Rate limited"),
        ]
        pr = PostResult(success=False, part_results=parts, error="Tweet 3 failed")
        assert pr.success is False
        assert len(pr.part_results) == 3
        assert pr.part_results[0].success is True
        assert pr.part_results[2].success is False

    def test_empty_part_results_list(self):
        """Empty part_results list is valid (different from None)."""
        pr = PostResult(success=True, part_results=[])
        assert pr.part_results is not None
        assert len(pr.part_results) == 0

    def test_wrapper_external_id_separate_from_parts(self):
        """Wrapper PostResult can have its own external_id alongside parts."""
        parts = [PostResult(success=True, external_id="first")]
        pr = PostResult(
            success=True,
            external_id="first",
            external_url="https://x.com/u/status/first",
            part_results=parts,
        )
        assert pr.external_id == "first"
        assert pr.part_results[0].external_id == "first"


# =============================================================================
# Adapter post_thread() return types
# =============================================================================


class TestXAdapterPostThreadReturnType:
    """XAdapter.post_thread() returns PostResult with part_results."""

    def test_dry_run_returns_post_result(self):
        from social_hook.adapters.platform.x import XAdapter

        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(3)]
        result = adapter.post_thread(tweets, dry_run=True)

        assert isinstance(result, PostResult)
        assert result.success is True
        assert result.part_results is not None
        assert len(result.part_results) == 3

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_success_returns_post_result_with_parts(self, mock_post):
        from social_hook.adapters.platform.x import XAdapter

        call_count = 0

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {"data": {"id": f"t{call_count}"}}
            return resp

        mock_post.side_effect = fake_post
        adapter = XAdapter("test-token")
        result = adapter.post_thread([{"content": "A"}, {"content": "B"}])

        assert isinstance(result, PostResult)
        assert result.success is True
        assert result.part_results is not None
        assert len(result.part_results) == 2

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_failure_returns_post_result_with_partial_parts(self, mock_post):
        from social_hook.adapters.platform.x import XAdapter

        call_count = 0

        def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 2:
                resp.status_code = 500
                resp.json.return_value = {"detail": "Server error"}
                resp.text = "Server error"
            else:
                resp.status_code = 201
                resp.json.return_value = {"data": {"id": f"t{call_count}"}}
            return resp

        mock_post.side_effect = fake_post
        adapter = XAdapter("test-token")
        result = adapter.post_thread([{"content": "A"}, {"content": "B"}, {"content": "C"}])

        assert isinstance(result, PostResult)
        assert result.success is False
        assert result.part_results is not None
        assert len(result.part_results) == 2  # 1 success + 1 failure
        assert result.part_results[0].success is True
        assert result.part_results[1].success is False


class TestLinkedInAdapterPostThreadReturnType:
    """LinkedInAdapter.post_thread() returns PostResult (not ThreadResult)."""

    def test_returns_post_result_with_error(self):
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        adapter = LinkedInAdapter("token")
        result = adapter.post_thread([{"content": "test"}])

        assert isinstance(result, PostResult)
        assert result.success is False
        assert "does not support threads" in result.error
        assert result.part_results is None


# =============================================================================
# dry_run_thread_result
# =============================================================================


class TestDryRunThreadResult:
    """dry_run_thread_result returns PostResult with part_results."""

    def test_returns_post_result(self):
        result = dry_run_thread_result(4)
        assert isinstance(result, PostResult)
        assert result.success is True

    def test_has_correct_number_of_parts(self):
        result = dry_run_thread_result(5)
        assert result.part_results is not None
        assert len(result.part_results) == 5

    def test_each_part_has_dry_run_id(self):
        result = dry_run_thread_result(3)
        for part in result.part_results:
            assert part.success is True
            assert part.external_id is not None
            assert part.external_id.startswith("dry_run_")

    def test_single_part_thread(self):
        result = dry_run_thread_result(1)
        assert len(result.part_results) == 1
