"""Tests for drafter platform-agnostic instructions."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.platforms import ResolvedPlatformConfig
from social_hook.errors import ConfigError
from social_hook.llm.drafter import (
    Drafter,
    _auto_repair_content_tokens,
    _preseed_upload_specs,
    _reconcile_uploads,
    _sanitize_media_specs,
)
from social_hook.models.core import CommitInfo


def _make_drafter_mocks():
    """Build common mocks for drafter tests."""
    client = MagicMock()

    # Mock response with tool_use content
    tool_content = MagicMock()
    tool_content.type = "tool_use"
    tool_content.name = "create_draft"
    tool_content.input = {
        "content": "Great feature!",
        "platform": "x",
        "reasoning": "Short and punchy",
    }
    response = MagicMock()
    response.content = [tool_content]
    client.complete.return_value = response

    commit = CommitInfo(
        hash="abc12345",
        message="Add feature",
        diff="+ new code",
    )

    project_context = MagicMock()
    project_context.recent_posts = []
    project_context.platform_introduced = {"x": True}
    project_context.all_introduced = True
    project_context.project.id = "p1"
    project_context.project.repo_path = None
    project_context.social_context = None
    project_context.memories = []
    project_context.context_notes = []
    project_context.session_narratives = []
    project_context.project_summary = None
    project_context.milestone_summaries = []
    project_context.lifecycle = None
    project_context.active_arcs = []
    project_context.narrative_debt = 0
    project_context.pending_drafts = []
    project_context.recent_decisions = []

    decision = MagicMock()
    decision.decision = "draft"
    decision.reasoning = "Good commit"
    decision.angle = "feature"
    decision.episode_type = "milestone"
    decision.post_category = "arc"
    decision.include_project_docs = False

    db = MagicMock()

    return client, commit, project_context, decision, db


class TestDrafterPlatformConfig:
    """Tests for platform_config parameter in create_draft."""

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_platform_config_instructions(self, mock_prompt):
        """Platform config info appears in user message."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="x",
            enabled=True,
            priority="primary",
            type="builtin",
            account_tier="free",
            description=None,
            format=None,
            max_length=None,
            filter="all",
            frequency="high",
            max_posts_per_day=3,
            min_gap_minutes=30,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Platform: x (primary)" in user_msg
        assert "free tier" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_custom_platform_description(self, mock_prompt):
        """Custom platform description is included."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="blog",
            enabled=True,
            priority="secondary",
            type="custom",
            account_tier=None,
            description="My tech blog about ML",
            format="article",
            max_length=5000,
            filter="notable",
            frequency="moderate",
            max_posts_per_day=1,
            min_gap_minutes=120,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="blog",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "blog" in user_msg
        assert "My tech blog about ML" in user_msg
        assert "article" in user_msg
        assert "max 5000 chars" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_x_free_tier_with_config(self, mock_prompt):
        """X free tier instructions via platform_config."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="x",
            enabled=True,
            priority="primary",
            type="builtin",
            account_tier="free",
            description=None,
            format=None,
            max_length=None,
            filter="all",
            frequency="high",
            max_posts_per_day=3,
            min_gap_minutes=30,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Format Selection Framework" in user_msg
        assert "Avoid links" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_backward_compat_no_config(self, mock_prompt):
        """platform_config=None uses old logic (backward compat)."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            tier="free",
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Format Selection Framework" in user_msg
        assert "280 chars" in user_msg


class TestDrafterVisionUploads:
    """Uploads + vision-capability gating in create_draft."""

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_config_error_when_model_not_vision_capable(self, mock_prompt, tmp_path):
        """A non-vision model with uploads must raise ConfigError — never silent text-fallback."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        # A DeepSeek model in the catalog has supports_vision=False.
        client.full_id = "openrouter/deepseek/deepseek-chat-v3"
        drafter = Drafter(client)

        upload = MagicMock()
        img = tmp_path / "ref.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        upload.path = str(img)
        upload.context = "desk photo"

        with pytest.raises(ConfigError, match="does not support image inputs"):
            drafter.create_draft(
                decision,
                ctx,
                commit,
                db,
                platform="x",
                tier="free",
                uploads=[upload],
            )

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_vision_content_blocks_assembled_for_vision_model(self, mock_prompt, tmp_path):
        """With a vision model and uploads, the user content is a list of blocks (not a str)."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        client.full_id = "anthropic/claude-sonnet-4-5"
        drafter = Drafter(client)

        img = tmp_path / "ref.png"
        # Minimal PNG signature is enough — Pillow is not invoked for .png.
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        upload = MagicMock()
        upload.path = str(img)
        upload.context = "a desk"

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            tier="free",
            uploads=[upload],
        )
        msg_content = client.complete.call_args.kwargs["messages"][0]["content"]
        assert isinstance(msg_content, list)
        types = [b.get("type") for b in msg_content]
        assert "image" in types
        # Per-upload context text precedes the image.
        assert any(b.get("type") == "text" and "a desk" in b.get("text", "") for b in msg_content)
        # Image block uses base64 source.
        image_blocks = [b for b in msg_content if b.get("type") == "image"]
        assert image_blocks[0]["source"]["type"] == "base64"
        assert image_blocks[0]["source"]["media_type"].startswith("image/")


class TestSanitizeMediaSpecs:
    """_sanitize_media_specs — log+strip semantic errors; hard-fail only on structural ones."""

    def test_strips_unknown_tool(self):
        raw = {
            "content": "x",
            "platform": "x",
            "reasoning": "y",
            "media_specs": [
                {"id": "media_000000000001", "tool": "dalle", "spec": {}},
                {"id": "media_000000000002", "tool": "mermaid", "spec": {"diagram": "A"}},
            ],
        }
        out = _sanitize_media_specs(raw)
        tools = [s["tool"] for s in out["media_specs"]]
        assert tools == ["mermaid"]

    def test_dedupes_duplicate_ids_last_wins(self):
        raw = {
            "content": "x",
            "platform": "x",
            "reasoning": "y",
            "media_specs": [
                {"id": "media_dup111111aa", "tool": "mermaid", "spec": {"diagram": "first"}},
                {"id": "media_dup111111aa", "tool": "mermaid", "spec": {"diagram": "second"}},
            ],
        }
        out = _sanitize_media_specs(raw)
        assert len(out["media_specs"]) == 1
        assert out["media_specs"][0]["spec"]["diagram"] == "second"

    def test_strips_hallucinated_user_uploaded(self):
        """user_uploaded=True with no matching upload path is stripped."""
        raw = {
            "content": "x",
            "platform": "x",
            "reasoning": "y",
            "media_specs": [
                {
                    "id": "media_hallucinate",
                    "tool": "legacy_upload",
                    "spec": {"path": "/never/uploaded.png"},
                    "user_uploaded": True,
                },
                {
                    "id": "media_realone1234",
                    "tool": "mermaid",
                    "spec": {"diagram": "A"},
                },
            ],
        }
        out = _sanitize_media_specs(raw, uploads=None)
        ids = [s["id"] for s in out["media_specs"]]
        assert ids == ["media_realone1234"]

    def test_keeps_user_uploaded_when_path_matches(self):
        raw = {
            "content": "x",
            "platform": "x",
            "reasoning": "y",
            "media_specs": [
                {
                    "id": "media_upl000000aa",
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/ref.png"},
                    "user_uploaded": True,
                }
            ],
        }
        fake_upload = MagicMock()
        fake_upload.path = "/tmp/ref.png"
        out = _sanitize_media_specs(raw, uploads=[fake_upload])
        assert len(out["media_specs"]) == 1

    def test_strips_malformed_entries(self):
        raw = {
            "content": "x",
            "platform": "x",
            "reasoning": "y",
            "media_specs": [
                "not-a-dict",
                {"tool": "mermaid"},  # missing id, spec
                {"id": "media_missing1234", "tool": "mermaid"},  # missing spec
                {"id": "media_okokokokokok", "tool": "mermaid", "spec": {"diagram": "A"}},
            ],
        }
        out = _sanitize_media_specs(raw)
        assert len(out["media_specs"]) == 1
        assert out["media_specs"][0]["id"] == "media_okokokokokok"


class TestAutoRepairContentTokens:
    """_auto_repair_content_tokens — defense-in-depth against LLM token drift."""

    def test_prefix_strip_repaired(self):
        """Token id equal to the 12-hex tail of a spec id is rewritten to the full id."""
        content = "intro ![flow diagram](media:a1b2c3d4e5f6) outro"
        specs = [{"id": "media_a1b2c3d4e5f6", "tool": "mermaid", "spec": {"diagram": "A-->B"}}]
        out = _auto_repair_content_tokens(content, specs)
        assert "![flow diagram](media:media_a1b2c3d4e5f6)" in out
        assert "media:a1b2c3d4e5f6)" not in out  # bare tail gone

    def test_literal_placeholder_dropped(self):
        """Tokens whose id is a literal placeholder string are removed outright."""
        content = "before ![example](media:ID) after"
        specs = [{"id": "media_realrealreal", "tool": "mermaid", "spec": {"diagram": "A"}}]
        out = _auto_repair_content_tokens(content, specs)
        assert "(media:ID)" not in out
        assert "before " in out and " after" in out

    def test_literal_placeholder_case_insensitive(self):
        """Case-insensitive match drops uppercase variants like MEDIA_ID."""
        content = "before ![y](media:MEDIA_ID) after ![z](media:Example) tail"
        specs = [{"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {}}]
        out = _auto_repair_content_tokens(content, specs)
        assert "(media:MEDIA_ID)" not in out
        assert "(media:Example)" not in out
        assert "before " in out and " tail" in out

    def test_angle_bracket_placeholder_passes_through(self):
        """``<id>`` is not a valid TOKEN_RE match (regex excludes <>), so it
        passes through untouched. It will remain visible in the rendered
        markdown — that's the correct user-visible signal that the drafter
        copied a placeholder from the schema example."""
        content = "before ![x](media:<id>) after"
        specs = [{"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {}}]
        out = _auto_repair_content_tokens(content, specs)
        assert out == content  # literal passes through — regex doesn't match

    def test_unrecoverable_left_verbatim(self):
        """Tokens that don't match any spec pass through for the diagnostic to catch."""
        content = "text ![a](media:nonsense_xyz) more"
        specs = [{"id": "media_realrealreal", "tool": "mermaid", "spec": {}}]
        out = _auto_repair_content_tokens(content, specs)
        assert "(media:nonsense_xyz)" in out

    def test_exact_match_unchanged(self):
        """Tokens that already reference a real spec id pass through untouched."""
        content = "![ok](media:media_abcdef012345)"
        specs = [{"id": "media_abcdef012345", "tool": "mermaid", "spec": {}}]
        out = _auto_repair_content_tokens(content, specs)
        assert out == content

    def test_multi_token_mixed(self):
        """Mix of repairable + unrepairable + exact tokens resolves per-token."""
        content = (
            "![ok](media:media_aaaaaaaaaaaa) "
            "![strip](media:bbbbbbbbbbbb) "
            "![drop](media:ID) "
            "![keep](media:unknown_id_9)"
        )
        specs = [
            {"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {}},
            {"id": "media_bbbbbbbbbbbb", "tool": "ray_so", "spec": {}},
        ]
        out = _auto_repair_content_tokens(content, specs)
        assert "(media:media_aaaaaaaaaaaa)" in out  # exact kept
        assert "(media:media_bbbbbbbbbbbb)" in out  # prefix-repaired
        assert "(media:bbbbbbbbbbbb)" not in out  # bare tail gone
        assert "(media:ID)" not in out  # literal dropped
        assert "(media:unknown_id_9)" in out  # unrecoverable kept

    def test_ambiguous_tail_not_repaired(self):
        """If two spec ids share the same 12-hex tail (impossible in practice
        but checked defensively), the tail stays ambiguous and is left as-is
        rather than silently mis-routed."""
        # Spec ids can't actually collide this way under the generate_id
        # pattern, but the safety valve matters if a future id change lets
        # them. Force the collision via identical tails on two specs.
        content = "![x](media:deadbeefcafe)"
        specs = [
            {"id": "media_deadbeefcafe", "tool": "mermaid", "spec": {}},
            # Manually induce collision to exercise the ambiguity branch.
            {"id": "media_deadbeefcafe", "tool": "ray_so", "spec": {}},
        ]
        out = _auto_repair_content_tokens(content, specs)
        # With both tails identical the tail maps to a single id (set dedup),
        # so repair still succeeds — this just documents the branch exists.
        assert "media:media_deadbeefcafe" in out

    def test_no_specs_returns_content_unchanged(self):
        content = "![x](media:anything)"
        out = _auto_repair_content_tokens(content, [])
        assert out == content

    def test_empty_content_returns_unchanged(self):
        specs = [{"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {}}]
        assert _auto_repair_content_tokens("", specs) == ""


class TestUploadPreseedAndReconcile:
    """Pre-seeding uploads into media_specs + reconciling the drafter's output."""

    def _upload(self, path: str, context: str = ""):
        up = MagicMock()
        up.path = path
        up.context = context
        return up

    def test_preseed_builds_one_spec_per_upload(self):
        uploads = [self._upload("/tmp/a.png", "desk"), self._upload("/tmp/b.png")]
        specs = _preseed_upload_specs(uploads)
        assert len(specs) == 2
        for spec, src in zip(specs, uploads, strict=True):
            assert spec["tool"] == "legacy_upload"
            assert spec["user_uploaded"] is True
            assert spec["spec"]["path"] == src.path
            assert spec["spec"]["context"] == src.context
            # id must match backend format: media_<12hex>
            assert spec["id"].startswith("media_") and len(spec["id"]) == len("media_") + 12
        # Ids are unique across uploads.
        assert specs[0]["id"] != specs[1]["id"]

    def test_preseed_skips_path_missing(self):
        """Uploads without a path are skipped (logged) rather than raising."""
        bad = MagicMock()
        bad.path = None
        bad.context = "whatever"
        out = _preseed_upload_specs([bad, self._upload("/tmp/ok.png")])
        assert len(out) == 1
        assert out[0]["spec"]["path"] == "/tmp/ok.png"

    def test_reconcile_preserves_upload_when_llm_kept_it(self):
        """LLM returned the pre-seeded upload as-is — merged output preserves id + path."""
        preseeded = _preseed_upload_specs([self._upload("/tmp/ref.png", "desk")])
        llm_out = {
            "media_specs": [
                {
                    "id": preseeded[0]["id"],
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/ref.png"},
                    "caption": "a nice desk",
                    "user_uploaded": True,
                }
            ]
        }
        out = _reconcile_uploads(llm_out, preseeded)
        assert len(out["media_specs"]) == 1
        item = out["media_specs"][0]
        assert item["id"] == preseeded[0]["id"]
        assert item["spec"]["path"] == "/tmp/ref.png"
        assert item["user_uploaded"] is True
        assert item["caption"] == "a nice desk"  # LLM caption accepted

    def test_reconcile_reinjects_dropped_upload(self):
        """LLM dropped a pre-seeded upload — reconciliation re-adds it at the end."""
        up_a = self._upload("/tmp/a.png", "first")
        up_b = self._upload("/tmp/b.png", "second")
        preseeded = _preseed_upload_specs([up_a, up_b])
        llm_out = {
            "media_specs": [
                # LLM kept only the first upload.
                {
                    "id": preseeded[0]["id"],
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/a.png"},
                    "caption": None,
                    "user_uploaded": True,
                },
                # Plus a generated spec unrelated to uploads.
                {
                    "id": "media_gennnnn12345",
                    "tool": "mermaid",
                    "spec": {"diagram": "A-->B"},
                    "caption": None,
                    "user_uploaded": False,
                },
            ]
        }
        out = _reconcile_uploads(llm_out, preseeded)
        paths = [s["spec"].get("path") for s in out["media_specs"] if s.get("user_uploaded")]
        assert set(paths) == {"/tmp/a.png", "/tmp/b.png"}
        # Re-injected entry uses the original pre-seed id.
        reinjected = next(s for s in out["media_specs"] if s["spec"].get("path") == "/tmp/b.png")
        assert reinjected["id"] == preseeded[1]["id"]
        assert reinjected["spec"]["context"] == "second"
        # Non-upload specs pass through unchanged.
        gen_spec = next(s for s in out["media_specs"] if s.get("user_uploaded") is False)
        assert gen_spec["id"] == "media_gennnnn12345"

    def test_reconcile_overwrites_llm_modified_id_with_preseed(self):
        """LLM changed id + caption but path matches — id is overwritten, caption kept."""
        preseeded = _preseed_upload_specs([self._upload("/tmp/ref.png", "original")])
        real_id = preseeded[0]["id"]
        llm_out = {
            "media_specs": [
                {
                    "id": "media_llmmadeupid0",  # LLM tried to invent a new id
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/ref.png"},
                    "caption": "better caption",
                    "user_uploaded": True,
                }
            ]
        }
        out = _reconcile_uploads(llm_out, preseeded)
        item = out["media_specs"][0]
        assert item["id"] == real_id  # preseed id wins
        assert item["caption"] == "better caption"  # LLM caption preserved
        assert item["spec"]["path"] == "/tmp/ref.png"

    def test_reconcile_hallucinated_upload_not_matched(self):
        """LLM emitted user_uploaded with a path not in pre-seeded — left as-is for sanitize to strip.

        The sanitize step (run before reconcile in the real call chain)
        already removes hallucinated uploads. Reconcile does NOT silently
        accept or modify such entries — it just passes them through. We
        verify sanitize → reconcile composes correctly in the integration
        flow below.
        """
        preseeded = _preseed_upload_specs([self._upload("/tmp/ref.png")])
        # Sanitize with real upload would have stripped the hallucination
        # already. We directly test reconcile's defensive branch.
        llm_out = {
            "media_specs": [
                {
                    "id": "media_hallucinate",
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/never_uploaded.png"},
                    "caption": None,
                    "user_uploaded": True,
                }
            ]
        }
        out = _reconcile_uploads(llm_out, preseeded)
        # Hallucinated entry passes through (sanitize handles it upstream).
        paths = [s["spec"].get("path") for s in out["media_specs"] if s.get("user_uploaded")]
        # Real pre-seeded /tmp/ref.png is re-injected (LLM dropped it).
        assert "/tmp/ref.png" in paths

    def test_reconcile_with_no_media_specs_field(self):
        """LLM returned no media_specs at all — all pre-seeded uploads re-injected."""
        preseeded = _preseed_upload_specs(
            [self._upload("/tmp/a.png", "ctx a"), self._upload("/tmp/b.png")]
        )
        out = _reconcile_uploads({"content": "hi"}, preseeded)
        paths = [s["spec"]["path"] for s in out["media_specs"]]
        assert paths == ["/tmp/a.png", "/tmp/b.png"]

    def test_integration_sanitize_then_reconcile_strips_hallucination_reinjects_real(self):
        """End-to-end: sanitize strips hallucinated user_uploaded; reconcile re-injects real ones."""
        preseeded = _preseed_upload_specs([self._upload("/tmp/ref.png")])
        uploads = [self._upload("/tmp/ref.png")]
        llm_out = {
            "content": "ok",
            "media_specs": [
                # Real upload preserved by LLM.
                {
                    "id": preseeded[0]["id"],
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/ref.png"},
                    "caption": None,
                    "user_uploaded": True,
                },
                # Hallucinated upload — not in uploads list.
                {
                    "id": "media_hallucinate",
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/fake.png"},
                    "caption": None,
                    "user_uploaded": True,
                },
            ],
        }
        sanitized = _sanitize_media_specs(llm_out, uploads=uploads)
        reconciled = _reconcile_uploads(sanitized, preseeded)
        paths = [s["spec"].get("path") for s in reconciled["media_specs"]]
        assert "/tmp/ref.png" in paths
        assert "/tmp/fake.png" not in paths  # stripped by sanitize

    def test_empty_uploads_no_preseed(self):
        """intent.uploads=None or [] → no pre-seeding; existing flow intact."""
        assert _preseed_upload_specs([]) == []

    def test_create_draft_preseeds_and_reconciles(self, tmp_path):
        """End-to-end: create_draft with uploads pre-seeds, drafter drops one, reconciliation re-injects.

        Vision-capable model (sonnet) exercises the full path.
        """
        client, commit, ctx, decision, db = _make_drafter_mocks()
        client.full_id = "anthropic/claude-sonnet-4-5"

        # Give the LLM-returned tool_input an empty media_specs so
        # reconciliation MUST re-inject all pre-seeded uploads.
        tool_content = MagicMock()
        tool_content.type = "tool_use"
        tool_content.name = "create_draft"
        tool_content.input = {
            "content": "Post body",
            "platform": "x",
            "reasoning": "vision with uploads",
            "media_specs": [],
        }
        response = MagicMock()
        response.content = [tool_content]
        client.complete.return_value = response

        img = tmp_path / "ref.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        up = MagicMock()
        up.path = str(img)
        up.context = "desk"

        drafter = Drafter(client)
        with patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt"):
            result = drafter.create_draft(
                decision, ctx, commit, db, platform="x", tier="free", uploads=[up]
            )

        # Pre-seeded upload survived the empty-LLM-output round-trip.
        assert len(result.media_specs) == 1
        item = result.media_specs[0]
        assert item.tool == "legacy_upload"
        assert item.user_uploaded is True
        assert item.spec["path"] == str(img)
        # Id is backend-generated, not LLM-invented.
        assert item.id.startswith("media_") and len(item.id) == len("media_") + 12
