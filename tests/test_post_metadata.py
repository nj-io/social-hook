"""Tests for Phase 5d: Post metadata population (topic_tags, feature_tags, is_thread_head)."""

from unittest.mock import MagicMock, patch

from social_hook.adapters.models import PostResult
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, DraftTweet, Project
from social_hook.scheduler import record_post_success


class TestPostMetadataPopulation:
    """record_post_success populates topic_tags, feature_tags, is_thread_head from decision."""

    def _setup_project_decision_draft(
        self, conn, *, episode_tags=None, decision_kwargs=None, draft_kwargs=None
    ):
        """Helper: create project + decision + draft, return (project, decision, draft)."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)

        d_kwargs = {
            "id": generate_id("decision"),
            "project_id": project.id,
            "commit_hash": "abc123",
            "decision": "draft",
            "reasoning": "test",
        }
        if episode_tags is not None:
            d_kwargs["episode_tags"] = episode_tags
        if decision_kwargs:
            d_kwargs.update(decision_kwargs)
        decision = Decision(**d_kwargs)
        ops.insert_decision(conn, decision)

        dr_kwargs = {
            "id": generate_id("draft"),
            "project_id": project.id,
            "decision_id": decision.id,
            "platform": "x",
            "content": "Test post",
            "status": "scheduled",
        }
        if draft_kwargs:
            dr_kwargs.update(draft_kwargs)
        draft = Draft(**dr_kwargs)
        ops.insert_draft(conn, draft)

        return project, decision, draft

    def test_topic_tags_populated_from_episode_tags(self, tmp_path):
        """topic_tags on Post are set from the decision's episode_tags."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(
            conn, episode_tags=["auth", "security", "middleware"]
        )
        result = PostResult(success=True, external_id="ext-1", external_url="https://x.com/1")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.topic_tags == ["auth", "security", "middleware"]

        # Verify DB round-trip
        db_post = ops.get_post(conn, post.id)
        assert db_post.topic_tags == ["auth", "security", "middleware"]
        conn.close()

    def test_empty_episode_tags_yields_empty_topic_tags(self, tmp_path):
        """When decision has no episode_tags, topic_tags is empty."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(conn, episode_tags=[])
        result = PostResult(success=True, external_id="ext-2", external_url="https://x.com/2")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.topic_tags == []
        conn.close()

    def test_feature_tags_empty_by_default(self, tmp_path):
        """feature_tags defaults to empty (no separate source yet)."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(conn, episode_tags=["auth"])
        result = PostResult(success=True, external_id="ext-3", external_url="https://x.com/3")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.feature_tags == []
        conn.close()

    def test_is_thread_head_true_when_draft_has_tweets(self, tmp_path):
        """is_thread_head is True when the draft has draft_tweets."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(
            conn, episode_tags=["threading"]
        )

        # Add thread tweets
        tweet1 = DraftTweet(
            id=generate_id("tweet"), draft_id=draft.id, position=0, content="Tweet 1"
        )
        tweet2 = DraftTweet(
            id=generate_id("tweet"), draft_id=draft.id, position=1, content="Tweet 2"
        )
        ops.insert_draft_tweet(conn, tweet1)
        ops.insert_draft_tweet(conn, tweet2)

        result = PostResult(success=True, external_id="ext-4", external_url="https://x.com/4")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.is_thread_head is True

        # DB round-trip
        db_post = ops.get_post(conn, post.id)
        assert db_post.is_thread_head is True
        conn.close()

    def test_is_thread_head_false_when_no_tweets(self, tmp_path):
        """is_thread_head is False for single posts (no draft_tweets)."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(conn, episode_tags=["auth"])
        result = PostResult(success=True, external_id="ext-5", external_url="https://x.com/5")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.is_thread_head is False
        conn.close()

    def test_no_decision_id_yields_empty_tags(self, tmp_path):
        """Legacy drafts without decision_id get empty tags."""
        conn = init_database(tmp_path / "test.db")
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)

        # Decision still needed in DB for FK, but draft.decision_id will be empty string
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
            episode_tags=["should-not-appear"],
        )
        ops.insert_decision(conn, decision)

        # Draft with empty decision_id (falsy)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Legacy post",
            status="scheduled",
        )
        ops.insert_draft(conn, draft)

        # Simulate a legacy draft by patching decision_id to empty
        draft.decision_id = ""

        result = PostResult(success=True, external_id="ext-6", external_url="https://x.com/6")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.topic_tags == []
        assert post.feature_tags == []
        conn.close()

    def test_missing_decision_logs_warning(self, tmp_path):
        """When decision_id is set but decision doesn't exist, logs warning."""
        conn = init_database(tmp_path / "test.db")
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)

        # Create a decision for FK, then draft referencing a non-existent one
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Orphan post",
            status="scheduled",
        )
        ops.insert_draft(conn, draft)

        # Point draft at non-existent decision
        draft.decision_id = "decision-does-not-exist"

        result = PostResult(success=True, external_id="ext-7", external_url="https://x.com/7")

        with (
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.logger") as mock_logger,
        ):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.topic_tags == []
        mock_logger.warning.assert_called_once()
        conn.close()

    def test_all_metadata_combined(self, tmp_path):
        """Full scenario: episode_tags + thread tweets → all metadata populated."""
        conn = init_database(tmp_path / "test.db")
        project, decision, draft = self._setup_project_decision_draft(
            conn, episode_tags=["auth", "refactor"]
        )

        # Add a thread tweet
        tweet = DraftTweet(
            id=generate_id("tweet"), draft_id=draft.id, position=0, content="Thread tweet 1"
        )
        ops.insert_draft_tweet(conn, tweet)

        result = PostResult(success=True, external_id="ext-8", external_url="https://x.com/8")

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(conn, draft, result, MagicMock(), project.name)

        assert post.topic_tags == ["auth", "refactor"]
        assert post.feature_tags == []
        assert post.is_thread_head is True

        # DB round-trip
        db_post = ops.get_post(conn, post.id)
        assert db_post.topic_tags == ["auth", "refactor"]
        assert db_post.feature_tags == []
        assert db_post.is_thread_head is True
        conn.close()
