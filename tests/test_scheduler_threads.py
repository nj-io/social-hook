"""Tests for scheduler thread-aware posting (Phase A)."""

from unittest.mock import MagicMock, patch

from social_hook.adapters.models import PostResult, ThreadResult
from social_hook.db import (
    get_draft_tweets,
    init_database,
    insert_decision,
    insert_draft,
    insert_draft_tweet,
    update_draft_tweet,
)
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, DraftTweet
from social_hook.scheduler import _post_draft, _registry


class TestPostDraftSignature:
    """_post_draft accepts conn as first parameter."""

    def test_post_draft_requires_conn(self):
        """_post_draft requires conn, draft, config, db_path."""
        import inspect

        sig = inspect.signature(_post_draft)
        params = list(sig.parameters.keys())
        assert params[0] == "conn"
        assert params[1] == "draft"
        assert params[2] == "config"
        assert "db_path" in params


class TestPostDraftThread:
    """_post_draft thread-aware posting."""

    def setup_method(self):
        """Clear adapter registry between tests to prevent stale cache."""
        _registry.clear()

    def _setup_draft_with_tweets(self, conn):
        """Create a project, decision, draft with thread tweets."""
        from social_hook.db import insert_project
        from social_hook.models import Project

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="1/ First\n\n2/ Second\n\n3/ Third\n\n4/ Fourth",
            status="scheduled",
        )
        insert_draft(conn, draft)

        for i, text in enumerate(["First", "Second", "Third", "Fourth"]):
            tweet = DraftTweet(
                id=generate_id("tweet"),
                draft_id=draft.id,
                position=i,
                content=text,
            )
            insert_draft_tweet(conn, tweet)

        return project, draft

    @patch("social_hook.adapters.platform.registry.create_adapter")
    def test_thread_posts_via_post_thread(self, mock_create_adapter, temp_dir):
        """When draft has tweets, uses post_thread()."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_draft_with_tweets(conn)

        mock_adapter = MagicMock()
        mock_thread_result = ThreadResult(
            success=True,
            tweet_results=[PostResult(success=True, external_id=f"ext_{i}") for i in range(4)],
        )
        mock_adapter.post_thread.return_value = mock_thread_result
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        config.env = {
            "X_CLIENT_ID": "cid",
            "X_CLIENT_SECRET": "csec",
        }
        config.platforms = {"x": MagicMock(account_tier="free")}

        result = _post_draft(conn, draft, config, db_path=str(db_path))
        assert result.success is True
        mock_adapter.post_thread.assert_called_once()
        mock_adapter.post.assert_not_called()

    @patch("social_hook.adapters.platform.registry.create_adapter")
    def test_thread_updates_draft_tweets_after_posting(self, mock_create_adapter, temp_dir):
        """After post_thread, each draft_tweet gets external_id and posted_at."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_draft_with_tweets(conn)

        mock_adapter = MagicMock()
        mock_thread_result = ThreadResult(
            success=True,
            tweet_results=[PostResult(success=True, external_id=f"ext_{i}") for i in range(4)],
        )
        mock_adapter.post_thread.return_value = mock_thread_result
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        config.env = {
            "X_CLIENT_ID": "cid",
            "X_CLIENT_SECRET": "csec",
        }
        config.platforms = {"x": MagicMock(account_tier="free")}

        _post_draft(conn, draft, config, db_path=str(db_path))

        tweets = get_draft_tweets(conn, draft.id)
        for i, tweet in enumerate(tweets):
            assert tweet.external_id == f"ext_{i}"
            assert tweet.posted_at is not None

    @patch("social_hook.adapters.platform.registry.create_adapter")
    def test_no_tweets_posts_single(self, mock_create_adapter, temp_dir):
        """Without draft_tweets, posts single via post()."""
        from social_hook.db import insert_project
        from social_hook.models import Project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Short post",
            status="scheduled",
        )
        insert_draft(conn, draft)

        config = MagicMock()
        config.env = {
            "X_CLIENT_ID": "cid",
            "X_CLIENT_SECRET": "csec",
        }
        config.platforms = {"x": MagicMock(account_tier="free")}

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="ext_1")
        mock_create_adapter.return_value = mock_adapter

        result = _post_draft(conn, draft, config, db_path=str(db_path))
        assert result.success is True
        mock_adapter.post.assert_called_once_with("Short post", media_paths=None)
        mock_adapter.post_thread.assert_not_called()

    @patch("social_hook.adapters.platform.registry.create_adapter")
    def test_linkedin_thread_guard(self, mock_create_adapter, temp_dir):
        """LinkedIn posts single content even if draft has tweets."""
        from social_hook.db import insert_project
        from social_hook.models import Project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="linkedin",
            content="Full post content here",
            status="scheduled",
        )
        insert_draft(conn, draft)

        # Add tweets (these should be ignored for linkedin)
        for i in range(4):
            tweet = DraftTweet(
                id=generate_id("tweet"),
                draft_id=draft.id,
                position=i,
                content=f"Tweet {i}",
            )
            insert_draft_tweet(conn, tweet)

        config = MagicMock()
        config.env = {"LINKEDIN_ACCESS_TOKEN": "tok"}

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="li_1")
        mock_create_adapter.return_value = mock_adapter

        result = _post_draft(conn, draft, config)
        assert result.success is True
        mock_adapter.post.assert_called_once_with("Full post content here", media_paths=None)

    @patch("social_hook.adapters.platform.registry.create_adapter")
    def test_paid_tier_long_single_post(self, mock_create_adapter, temp_dir):
        """Paid tier long single post (>280 chars) posts successfully."""
        from social_hook.db import insert_project
        from social_hook.models import Project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        long_content = "x" * 1000
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content=long_content,
            status="scheduled",
        )
        insert_draft(conn, draft)

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="ext_1")
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        config.env = {
            "X_CLIENT_ID": "cid",
            "X_CLIENT_SECRET": "csec",
        }
        config.platforms = {"x": MagicMock(account_tier="premium")}

        result = _post_draft(conn, draft, config, db_path=str(db_path))
        assert result.success is True
        mock_adapter.post.assert_called_once_with(long_content, media_paths=None)


class TestUpdateDraftTweet:
    """Tests for update_draft_tweet DB operation."""

    def test_update_sets_external_id(self, temp_db):
        from social_hook.db import insert_project
        from social_hook.models import Project

        project = Project(id=generate_id("project"), name="t", repo_path="/t")
        insert_project(temp_db, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="t",
        )
        insert_decision(temp_db, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)
        tweet = DraftTweet(
            id=generate_id("tweet"),
            draft_id=draft.id,
            position=0,
            content="hello",
        )
        insert_draft_tweet(temp_db, tweet)

        updated = update_draft_tweet(
            temp_db,
            tweet.id,
            external_id="ext_123",
            posted_at="2026-01-01T00:00:00",
        )
        assert updated is True

        tweets = get_draft_tweets(temp_db, draft.id)
        assert tweets[0].external_id == "ext_123"
        assert tweets[0].posted_at is not None

    def test_update_sets_error(self, temp_db):
        from social_hook.db import insert_project
        from social_hook.models import Project

        project = Project(id=generate_id("project"), name="t", repo_path="/t")
        insert_project(temp_db, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="t",
        )
        insert_decision(temp_db, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)
        tweet = DraftTweet(
            id=generate_id("tweet"),
            draft_id=draft.id,
            position=0,
            content="hello",
        )
        insert_draft_tweet(temp_db, tweet)

        updated = update_draft_tweet(temp_db, tweet.id, error="Rate limited")
        assert updated is True

        tweets = get_draft_tweets(temp_db, draft.id)
        assert tweets[0].error == "Rate limited"

    def test_update_no_fields_returns_false(self, temp_db):
        updated = update_draft_tweet(temp_db, "nonexistent_id")
        assert updated is False
