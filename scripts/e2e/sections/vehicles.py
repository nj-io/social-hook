"""Section V: Content Vehicle & Advisory scenarios.

Tests vehicle-aware approval routing: article drafts create advisory items
instead of entering the scheduler. Covers bot commands, bot buttons, CLI
commands, batch approve, and the scheduler safety net.

V8-V16 extend coverage to multi-media drafts: article inline-positioned
generation, upload-first vision, partial-failure diagnostic, orphan/broken
token diagnostics, per-item regen background task, max-count enforcement,
change-angle per-part media, CLI media subcommand parity, and advisory
token resolution. Media files from behavioral scenarios are persisted to
``~/.social-hook/e2e-media-review/<scenario>/`` for human review.
"""

import shutil
from pathlib import Path

# Persistent directory for reviewing generated media after E2E runs.
# Uses the real HOME (not the patched E2E temp HOME) so files survive cleanup.
_MEDIA_REVIEW_DIR: Path | None = None


def _init_media_review(harness) -> None:
    """Set up persistent media review directory under real ~/.social-hook/."""
    global _MEDIA_REVIEW_DIR
    real_home = harness._orig_home or str(Path.home())
    _MEDIA_REVIEW_DIR = Path(real_home) / ".social-hook" / "e2e-media-review"
    _MEDIA_REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _persist_media(scenario_id: str, file_paths: list[str]) -> list[str]:
    """Copy generated media files to persistent review directory."""
    if not _MEDIA_REVIEW_DIR or not file_paths:
        return []
    dest_dir = _MEDIA_REVIEW_DIR / scenario_id.lower()
    dest_dir.mkdir(parents=True, exist_ok=True)
    persisted: list[str] = []
    for fp in file_paths:
        src = Path(fp)
        if src.exists():
            dst = dest_dir / src.name
            shutil.copy2(src, dst)
            persisted.append(str(dst))
    return persisted


def run(harness, runner, adapter):
    """V1-V16: Vehicle, advisory, and multi-media scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    _init_media_review(harness)

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # V1: Approve article draft → advisory (bot command)
    def v1():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.commands import cmd_approve

        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        return f"Article draft → advisory, advisory item {linked[0].id}"

    runner.run_scenario("V1", "Approve article → advisory (bot command)", v1)

    # V2: Quick approve article draft → advisory with due_date (bot button)
    def v2():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.buttons import btn_quick_approve

        adapter.clear()
        btn_quick_approve(adapter, chat_id, "web_0", draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        assert linked[0].due_date is not None, "Advisory should have due_date from schedule"
        return f"Quick approve → advisory with due_date {linked[0].due_date}"

    runner.run_scenario("V2", "Quick approve article → advisory with due_date", v2)

    # V3: Post Now article draft → advisory (bot button)
    def v3():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.buttons import btn_post_now

        adapter.clear()
        btn_post_now(adapter, chat_id, "web_0", draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        return "Post Now article → advisory (no scheduler involved)"

    runner.run_scenario("V3", "Post Now article → advisory (bot button)", v3)

    # V4: Approve single draft → normal approve (not advisory)
    def v4():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="single")
        from social_hook.bot.commands import cmd_approve

        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "approved", f"Expected approved, got {updated.status}"
        return "Single draft → approved (normal flow, no advisory)"

    runner.run_scenario("V4", "Approve single draft → normal (not advisory)", v4)

    # V5: Batch approve mixed vehicles
    def v5():
        from social_hook.filesystem import generate_id

        # Create a cycle with both single and article drafts
        cycle_id = generate_id("cycle")
        harness.conn.execute(
            "INSERT INTO evaluation_cycles (id, project_id, trigger_type, created_at) "
            "VALUES (?, ?, 'manual', datetime('now'))",
            (cycle_id, harness.project_id),
        )
        harness.conn.commit()

        single_draft = harness.seed_draft(harness.project_id, status="draft", vehicle="single")
        article_draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")

        # Link drafts to cycle
        harness.conn.execute(
            "UPDATE drafts SET evaluation_cycle_id = ? WHERE id IN (?, ?)",
            (cycle_id, single_draft.id, article_draft.id),
        )
        harness.conn.commit()

        from social_hook.bot.buttons import handle_cycle_approve

        adapter.clear()
        handle_cycle_approve(adapter, chat_id, "web_0", cycle_id, config)

        single_after = ops.get_draft(harness.conn, single_draft.id)
        article_after = ops.get_draft(harness.conn, article_draft.id)
        assert single_after.status == "approved", f"Single: {single_after.status}"
        assert article_after.status == "advisory", f"Article: {article_after.status}"
        return "Batch: single → approved, article → advisory"

    runner.run_scenario("V5", "Batch approve mixed vehicles", v5)

    # V6: CLI approve article → advisory
    def v6():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        assert not check_auto_postable(draft), "Article should not be auto-postable"
        handle_advisory_approval(harness.conn, draft, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        return "CLI path: check_auto_postable + handle_advisory_approval works"

    runner.run_scenario("V6", "CLI advisory helpers direct call", v6)

    # V7: Scheduler safety net — article draft in scheduled status
    def v7():
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            vehicle="article",
            scheduled_time=now,
        )

        from social_hook.scheduler import scheduler_tick

        scheduler_tick(draft_id=draft.id, dry_run=False)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) >= 1, "Safety net should create advisory item"
        return "Scheduler safety net: scheduled article → advisory"

    runner.run_scenario("V7", "Scheduler safety net for article", v7)

    # ------------------------------------------------------------------
    # V8-V16 — Multi-media scenarios
    # ------------------------------------------------------------------

    # V8: Article multi-media generation (LLM + Gemini; isolate=True)
    def v8():
        if not config.env.get("GEMINI_API_KEY"):
            raise AssertionError("V8 requires GEMINI_API_KEY for nano_banana_pro generation")
        harness.update_config({"media_generation": {"enabled": True}})

        from fastapi.testclient import TestClient

        from social_hook.media_tokens import extract_tokens
        from social_hook.web.server import app

        client = TestClient(app)
        body = {
            "vehicle": "article",
            "idea": (
                "Walk through how the multi-media drafter assembles inline article images "
                "alongside narrative prose, with a diagram of the generation pipeline and "
                "a photo-realistic hero."
            ),
            "upload_ids": [],
        }
        res = client.post(f"/api/projects/{harness.project_id}/create-content", json=body)
        assert res.status_code in (200, 202), f"create-content failed: {res.status_code} {res.text}"
        task_id = res.json().get("task_id")
        assert task_id, f"missing task_id in response: {res.json()}"

        final = harness.wait_for_task(task_id, timeout=180.0)
        assert final.get("status") == "completed", (
            f"task ended in {final.get('status')}: {final.get('error')}"
        )

        # Pick up the most recently created article draft for this project
        rows = harness.conn.execute(
            "SELECT id FROM drafts WHERE project_id = ? AND vehicle = 'article' "
            "ORDER BY created_at DESC LIMIT 1",
            (harness.project_id,),
        ).fetchall()
        assert rows, "No article draft created by V8"
        draft = ops.get_draft(harness.conn, rows[0][0])

        assert draft.vehicle == "article", f"expected article, got {draft.vehicle}"
        assert len(draft.media_specs) >= 1, (
            f"expected >=1 media_specs, got {len(draft.media_specs)}"
        )

        # Every spec must have an id
        for s in draft.media_specs:
            assert s.get("id"), f"media spec missing id: {s}"

        # Inline tokens should reference spec ids in the content
        tokens = extract_tokens(draft.content)
        assert tokens, "article content has no ![](media:ID) tokens"
        token_ids = {t.media_id for t in tokens}
        spec_ids = {s["id"] for s in draft.media_specs}
        overlap = token_ids & spec_ids
        assert overlap, f"no token ids match spec ids; tokens={token_ids} specs={spec_ids}"

        # Every spec has a path, no errors
        assert len(draft.media_paths) == len(draft.media_specs), (
            f"paths/specs length mismatch: {len(draft.media_paths)} vs {len(draft.media_specs)}"
        )
        for i, p in enumerate(draft.media_paths):
            assert p, f"media_paths[{i}] empty"
            assert Path(p).exists(), f"media file missing: {p}"
            assert Path(p).stat().st_size > 1000, f"media file too small: {p}"
        assert all(e is None for e in draft.media_errors), (
            f"media_errors has non-null: {draft.media_errors}"
        )

        _persist_media("V8", draft.media_paths)

        runner.add_review_item(
            "V8",
            title="Article multi-media generation",
            review_question=(
                "Are the generated media tools appropriate for the content? "
                "Do the inline token positions feel natural?"
            ),
            context={
                "content_excerpt": draft.content[:400],
                "spec_tools": [s.get("tool") for s in draft.media_specs],
                "media_files": draft.media_paths,
            },
        )

        harness.update_config({"media_generation": {"enabled": False}})
        return (
            f"Article draft: {draft.id}, {len(draft.media_specs)} spec(s), {len(tokens)} token(s)"
        )

    runner.run_scenario(
        "V8",
        "Article multi-media generation (LLM + Gemini)",
        v8,
        llm_call=True,
        isolate=True,
    )

    # V9: Upload-first with vision (real claude-cli/sonnet; isolate=True)
    def v9():
        from social_hook.llm.catalog import get_model_info
        from social_hook.media_tokens import extract_tokens

        # Config.models is a typed ModelsConfig dataclass with .drafter attribute,
        # not a dict; access via getattr to stay defensive if the shape shifts.
        drafter_model = getattr(getattr(config, "models", None), "drafter", None)
        info = get_model_info(drafter_model) if drafter_model else None
        if info is None or not info.supports_vision:
            # Skip cleanly
            return f"SKIP: drafter model {drafter_model!r} is not vision-capable"

        if not config.env.get("GEMINI_API_KEY"):
            raise AssertionError("V9 requires GEMINI_API_KEY for nano_banana_pro generation")
        harness.update_config({"media_generation": {"enabled": True}})

        # Materialize a small PNG to upload. Use a seeded adapter file if one
        # already exists from V8; else a stdlib-only 1x1 PNG fallback.
        upload_src = None
        if _MEDIA_REVIEW_DIR and (_MEDIA_REVIEW_DIR / "v8").exists():
            for f in (_MEDIA_REVIEW_DIR / "v8").iterdir():
                if f.suffix.lower() == ".png":
                    upload_src = str(f)
                    break
        if upload_src is None:
            import base64

            _PNG_1X1 = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAA"
                "SUVORK5CYII="
            )
            upload_src = str(Path(harness.base) / "v9_upload.png")
            Path(upload_src).write_bytes(_PNG_1X1)

        upload = harness.upload_file(
            harness.project_id, upload_src, context="Hero image for the article"
        )
        upload_id = upload["upload_id"]

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        body = {
            "vehicle": "article",
            "idea": (
                "Write an article that builds on the attached hero image, then add a second "
                "generated visual to illustrate the main flow."
            ),
            "upload_ids": [upload_id],
        }
        res = client.post(f"/api/projects/{harness.project_id}/create-content", json=body)
        assert res.status_code in (200, 202), f"create-content failed: {res.status_code} {res.text}"
        task_id = res.json().get("task_id")
        assert task_id, f"missing task_id in response: {res.json()}"

        final = harness.wait_for_task(task_id, timeout=180.0)
        assert final.get("status") == "completed", (
            f"task ended in {final.get('status')}: {final.get('error')}"
        )

        rows = harness.conn.execute(
            "SELECT id FROM drafts WHERE project_id = ? AND vehicle = 'article' "
            "ORDER BY created_at DESC LIMIT 1",
            (harness.project_id,),
        ).fetchall()
        assert rows, "No article draft created by V9"
        draft = ops.get_draft(harness.conn, rows[0][0])

        # Drafter may legitimately judge one image (the upload itself) is
        # sufficient for the article — we only require the upload to be
        # present and referenced, not a minimum total count.
        assert len(draft.media_specs) >= 1, f"expected >=1 spec, got {len(draft.media_specs)}"
        uploaded = [s for s in draft.media_specs if s.get("user_uploaded")]
        assert uploaded, "no user_uploaded spec in draft.media_specs"
        tokens = {t.media_id for t in extract_tokens(draft.content)}
        assert any(s["id"] in tokens for s in uploaded), (
            "uploaded spec's id is not referenced by any content token"
        )

        uploaded_idx = draft.media_specs.index(uploaded[0])
        uploaded_path = draft.media_paths[uploaded_idx]
        assert uploaded_path, "uploaded media_paths entry is empty"
        assert Path(uploaded_path).exists(), f"uploaded file missing after move: {uploaded_path}"

        # Generated items (non-upload) are optional — drafter may choose
        # upload-only. When present, each must have a non-empty path on disk.
        gen_paths = [
            draft.media_paths[i]
            for i, s in enumerate(draft.media_specs)
            if not s.get("user_uploaded")
        ]
        for p in gen_paths:
            assert p, "generated path empty"
            assert Path(p).exists(), f"generated file missing: {p}"

        _persist_media("V9", draft.media_paths)

        runner.add_review_item(
            "V9",
            title="Upload-first with vision",
            review_question=(
                "Did the drafter write content around the uploaded image? "
                "Is the generated media complementary?"
            ),
            context={
                "upload_path": upload_src,
                "generated_tools": [
                    s.get("tool") for s in draft.media_specs if not s.get("user_uploaded")
                ],
                "content_excerpt": draft.content[:400],
            },
        )

        harness.update_config({"media_generation": {"enabled": False}})
        return f"Article draft: {draft.id}, uploads={len(uploaded)}, generated={len(gen_paths)}"

    runner.run_scenario(
        "V9",
        "Upload-first with vision (real claude-cli)",
        v9,
        llm_call=True,
        isolate=True,
    )

    # V10: Partial failure diagnostic (structural)
    def v10():
        specs = [
            {
                "id": "media_v10aaa111",
                "tool": "nano_banana_pro",
                "spec": {"prompt": "a"},
                "caption": None,
                "user_uploaded": False,
            },
            {
                "id": "media_v10bbb222",
                "tool": "nano_banana_pro",
                "spec": {"prompt": "b"},
                "caption": None,
                "user_uploaded": False,
            },
            {
                "id": "media_v10ccc333",
                "tool": "nano_banana_pro",
                "spec": {"prompt": "c"},
                "caption": None,
                "user_uploaded": False,
            },
        ]
        content = (
            "Intro ![a](media:media_v10aaa111) mid "
            "![b](media:media_v10bbb222) tail ![c](media:media_v10ccc333)"
        )
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="article",
            content=content,
            media_specs=specs,
            media_paths=["/tmp/ok1.png", "", "/tmp/ok3.png"],
            media_errors=[None, "Gemini timeout", None],
        )

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        res = client.get(f"/api/drafts/{draft.id}")
        assert res.status_code == 200, f"GET failed: {res.status_code} {res.text}"
        body = res.json()
        codes = {d["code"]: d for d in body.get("diagnostics", [])}
        assert "partial_media_failure" in codes, (
            f"expected partial_media_failure; got {sorted(codes)}"
        )
        diag = codes["partial_media_failure"]
        assert diag["severity"] == "warning", f"severity: {diag['severity']}"
        assert diag["context"]["failed_indexes"] == [1], f"failed_indexes: {diag['context']}"

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "draft", f"status: {updated.status}"
        return "partial_media_failure diagnostic surfaced at read time"

    runner.run_scenario("V10", "Partial failure diagnostic", v10)

    # V11: Orphan + broken-ref consolidated (structural)
    def v11():
        specs = [
            {
                "id": "media_orphan_111",
                "tool": "mermaid",
                "spec": {"diagram": "A-->B"},
                "caption": None,
                "user_uploaded": False,
            },
        ]
        content = "Intro ![x](media:missing_xyz) text"
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="article",
            content=content,
            media_specs=specs,
            media_paths=["/tmp/a.png"],
        )

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        res = client.get(f"/api/drafts/{draft.id}")
        assert res.status_code == 200, f"GET failed: {res.status_code}"
        codes = {d["code"]: d for d in res.json().get("diagnostics", [])}
        assert "orphaned_media_spec" in codes, f"expected orphaned_media_spec; got {sorted(codes)}"
        assert "broken_media_reference" in codes, (
            f"expected broken_media_reference; got {sorted(codes)}"
        )
        assert codes["orphaned_media_spec"]["context"]["orphan_indexes"] == [0]
        assert codes["broken_media_reference"]["context"]["broken_ids"] == ["missing_xyz"]
        return "orphaned_media_spec + broken_media_reference emitted independently"

    runner.run_scenario("V11", "Orphan + broken-ref consolidated", v11)

    # V12: Per-item regen background task (structural)
    def v12():
        media_id = "media_v12xxxxxx"
        # Mermaid requires a diagram-type prefix (``graph TD`` etc.); the
        # adapter renders via mermaid.ink which 400s on bare edge syntax.
        specs = [
            {
                "id": media_id,
                "tool": "mermaid",
                "spec": {"diagram": "graph TD;\n  A-->B"},
                "caption": None,
                "user_uploaded": False,
            },
        ]
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="article",
            content=f"Intro ![a](media:{media_id}) end",
            media_specs=specs,
            media_paths=["/tmp/initial.png"],
            media_specs_used=specs,
        )

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        new_spec = {"tool": "mermaid", "spec": {"diagram": "graph LR;\n  X-->Y"}}
        res = client.put(f"/api/drafts/{draft.id}/media/{media_id}", json=new_spec)
        assert res.status_code in (200, 202), f"PUT failed: {res.status_code} {res.text}"
        body = res.json()
        task_id = body.get("task_id")
        assert task_id, f"missing task_id: {body}"

        final = harness.wait_for_task(task_id, timeout=60.0)
        assert final.get("status") == "completed", f"task status: {final.get('status')}"

        updated = ops.get_draft(harness.conn, draft.id)
        idx = next(i for i, s in enumerate(updated.media_specs) if s["id"] == media_id)
        # Path must have CHANGED from the seeded value (truthy isn't enough —
        # the seed was ``/tmp/initial.png``; success writes a real output path).
        assert updated.media_paths[idx] and updated.media_paths[idx] != "/tmp/initial.png", (
            f"media_paths[{idx}] didn't change from seed: {updated.media_paths[idx]}"
        )
        assert "X-->Y" in updated.media_specs_used[idx]["spec"]["diagram"], (
            f"media_specs_used not updated: {updated.media_specs_used[idx]}"
        )

        changes = ops.get_draft_changes(harness.conn, draft.id)
        assert any(c.field == f"media_spec:{media_id}" for c in changes), (
            f"expected DraftChange field=media_spec:{media_id}, got {[c.field for c in changes]}"
        )

        # task stage events should include a media_N_of_M stage
        stage_rows = (
            harness.conn.execute(
                "SELECT stage FROM web_events WHERE entity = 'task' AND action = 'stage' "
                "AND ref_id = ?",
                (task_id,),
            ).fetchall()
            if _has_web_events_stage_col(harness.conn)
            else []
        )
        if stage_rows:
            assert any((r[0] or "").startswith("media_") for r in stage_rows), (
                f"no media_* stage events for task: {stage_rows}"
            )
        return f"Per-item regen: media_paths[{idx}] updated, DraftChange recorded"

    runner.run_scenario("V12", "Per-item regen background task", v12)

    # V13: Max count enforcement (structural)
    def v13():
        # 4 specs is the X SINGLE cap
        specs = [
            {
                "id": f"media_v13_{i:04}",
                "tool": "nano_banana_pro",
                "spec": {"prompt": f"p{i}"},
                "caption": None,
                "user_uploaded": False,
            }
            for i in range(4)
        ]
        paths = [f"/tmp/v13_{i}.png" for i in range(4)]
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="single",
            platform="x",
            media_specs=specs,
            media_paths=paths,
        )

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        res = client.post(
            f"/api/drafts/{draft.id}/media",
            json={"tool": "nano_banana_pro", "spec": {"prompt": "5th"}},
        )
        assert res.status_code in (400, 409, 422), (
            f"expected 4xx rejection for over-cap add; got {res.status_code} {res.text}"
        )
        body_text = res.text.lower()
        assert "max_count" in body_text or "max count" in body_text or "limit" in body_text, (
            f"error should mention max_count/limit; got {res.text}"
        )

        updated = ops.get_draft(harness.conn, draft.id)
        assert len(updated.media_specs) == 4, (
            f"media_specs should be unchanged at 4; got {len(updated.media_specs)}"
        )
        return "Max count enforced: 5th media item rejected"

    runner.run_scenario("V13", "Max count enforcement", v13)

    # V14: Change-angle → per-part media (LLM; isolate=True)
    def v14():
        from social_hook.filesystem import generate_id
        from social_hook.models.core import DraftPart

        # Seed an X thread draft with 4 parts
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="thread",
            platform="x",
            content=(
                "1/ Shipping a multi-part thread\n\n"
                "2/ each part will grow its own image\n\n"
                "3/ via change-angle Expert redraft\n\n"
                "4/ verifying per-part draft_part.media_specs"
            ),
        )
        for pos, part_content in enumerate(
            [
                "Shipping a multi-part thread",
                "each part will grow its own image",
                "via change-angle Expert redraft",
                "verifying per-part draft_part.media_specs",
            ]
        ):
            ops.insert_draft_part(
                harness.conn,
                DraftPart(
                    id=generate_id("part"),
                    draft_id=draft.id,
                    position=pos,
                    content=part_content,
                ),
            )
        harness.conn.commit()

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        res = client.post(
            "/api/callback",
            json={
                "action": "expert",
                "payload": draft.id,
                "text": "give each tweet its own image",
            },
        )
        assert res.status_code in (200, 202), f"callback failed: {res.status_code} {res.text}"
        task_id = res.json().get("task_id") if res.json() else None
        if task_id:
            harness.wait_for_task(task_id, timeout=180.0)

        parts = ops.get_draft_parts(harness.conn, draft.id)
        assert len(parts) == 4, f"expected 4 parts, got {len(parts)}"
        populated = [p for p in parts if p.media_specs]
        assert len(populated) >= 3, f"expected >=3 parts with media_specs, got {len(populated)}"
        for p in populated:
            assert p.media_paths, f"part {p.id} has media_specs but no media_paths"

        changes = ops.get_draft_changes(harness.conn, draft.id)
        per_part_changes = [c for c in changes if c.field.startswith("draft_part.media_specs:")]
        assert len(per_part_changes) >= len(populated), (
            f"expected one DraftChange per affected part; "
            f"got {len(per_part_changes)} for {len(populated)} parts"
        )

        # Vehicle still thread
        updated_draft = ops.get_draft(harness.conn, draft.id)
        assert updated_draft.vehicle == "thread", f"vehicle changed: {updated_draft.vehicle}"

        runner.add_review_item(
            "V14",
            title="Change-angle per-part media",
            review_question=(
                "Are the per-part images coherent with each tweet? Do they "
                "visually differentiate the parts?"
            ),
            context={
                "part_contents": [p.content for p in parts],
                "part_media": [{"part_id": p.id, "media_paths": p.media_paths} for p in populated],
            },
        )
        return f"Thread with per-part media: {len(populated)}/4 parts populated"

    runner.run_scenario(
        "V14",
        "Change-angle per-part media (LLM)",
        v14,
        llm_call=True,
        isolate=True,
    )

    # V15: CLI media subcommand parity (structural)
    def v15():
        from typer.testing import CliRunner

        from social_hook.cli import app as cli_app

        media_id = "media_v15_aaaa"
        # Mermaid requires a diagram-type prefix; see V12.
        specs = [
            {
                "id": media_id,
                "tool": "mermaid",
                "spec": {"diagram": "graph TD;\n  A-->B"},
                "caption": None,
                "user_uploaded": False,
            },
        ]
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="article",
            content=f"Intro ![a](media:{media_id}) end",
            media_specs=specs,
            media_paths=["/tmp/v15.png"],
            media_specs_used=specs,
        )

        cli = CliRunner()

        # Regen with JSON output + explicit project path. CLI signature:
        # ``draft media regen --draft DRAFT_ID --id MEDIA_ID --project PATH [--json]``
        result = cli.invoke(
            cli_app,
            [
                "draft",
                "media",
                "regen",
                "--draft",
                draft.id,
                "--id",
                media_id,
                "--project",
                str(harness.repo_path),
                "--json",
            ],
        )
        assert result.exit_code == 0, f"regen exit {result.exit_code}: {result.output}"
        import json as _j

        payload = _j.loads(result.stdout)
        # CLI regen runs synchronously (per `draft media regen --help`:
        # "LLM-bearing — runs adapter generation synchronously in CLI context").
        # Response shape is ``{draft_id, count, regenerated: [{id, ...}, ...]}``,
        # not 202 + task_id. Assert structure AND that at least one item
        # actually succeeded — a regen that returns only items with ``error``
        # entries is a failure masquerading as success.
        assert "regenerated" in payload, f"regen output missing 'regenerated': {payload}"
        assert payload.get("count", 0) >= 1, f"regen count < 1: {payload}"
        succeeded = [r for r in payload["regenerated"] if not r.get("error")]
        assert succeeded, f"regen produced no successful items — all entries have errors: {payload}"

        # --index must be rejected (ID-only addressing)
        reject = cli.invoke(
            cli_app,
            [
                "draft",
                "media",
                "regen",
                "--draft",
                draft.id,
                "--index",
                "0",
                "--project",
                str(harness.repo_path),
            ],
        )
        assert reject.exit_code != 0, "--index should be rejected for ID-only addressing"

        # remove with --yes (no prompt)
        remove_result = cli.invoke(
            cli_app,
            [
                "draft",
                "media",
                "remove",
                "--draft",
                draft.id,
                "--id",
                media_id,
                "--project",
                str(harness.repo_path),
                "--yes",
            ],
        )
        assert remove_result.exit_code == 0, (
            f"remove exit {remove_result.exit_code}: {remove_result.output}"
        )
        updated = ops.get_draft(harness.conn, draft.id)
        assert all(s["id"] != media_id for s in updated.media_specs), (
            f"{media_id} still present after remove: {updated.media_specs}"
        )

        # Forgiving flag placement: global --json before subcommand
        list_json = cli.invoke(
            cli_app,
            [
                "--json",
                "draft",
                "media",
                "list",
                "--draft",
                draft.id,
                "--project",
                str(harness.repo_path),
            ],
        )
        assert list_json.exit_code == 0, (
            f"global --json list exit {list_json.exit_code}: {list_json.output}"
        )
        return "CLI media regen/remove/list parity confirmed; --index rejected"

    runner.run_scenario("V15", "CLI media subcommand parity", v15)

    # V16: Advisory token resolution (structural)
    def v16():
        from social_hook.filesystem import get_base_path

        media_id = "media_v16_bbbb"
        # Write a real (small) image file so the advisory can resolve a path
        media_dir = get_base_path() / "media-cache" / media_id
        media_dir.mkdir(parents=True, exist_ok=True)
        media_path = media_dir / "cover.png"
        import base64

        _PNG_1X1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        media_path.write_bytes(_PNG_1X1)

        specs = [
            {
                "id": media_id,
                "tool": "nano_banana_pro",
                "spec": {"prompt": "cover"},
                "caption": "Hero image",
                "user_uploaded": False,
            },
        ]
        content = f"# Article title\n\nIntro ![Hero image](media:{media_id})\n\nBody text."
        draft = harness.seed_draft(
            harness.project_id,
            vehicle="article",
            content=content,
            media_specs=specs,
            media_paths=[str(media_path)],
            media_specs_used=specs,
        )

        # Move to advisory status (bypass approve flow — this is a structural test)
        from social_hook.vehicle import handle_advisory_approval

        handle_advisory_approval(harness.conn, draft, config)

        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert linked, "no advisory item linked to seeded draft"
        advisory_id = linked[0].id

        from fastapi.testclient import TestClient

        from social_hook.web.server import app

        client = TestClient(app)
        res = client.get(f"/api/advisory/{advisory_id}")
        assert res.status_code == 200, f"GET advisory failed: {res.status_code} {res.text}"
        body = res.json()
        rendered = body.get("rendered_content") or ""
        assert rendered, f"advisory has no rendered_content: {body}"
        assert f"media:{media_id}" not in rendered, (
            f"token not resolved in rendered_content: {rendered}"
        )
        assert str(media_path) in rendered or media_path.name in rendered, (
            f"resolved path not in rendered_content: {rendered}"
        )
        assert "Hero image" in rendered, f"caption missing from rendered_content: {rendered}"
        return "Advisory GET returns rendered_content with tokens resolved"

    runner.run_scenario("V16", "Advisory token resolution", v16)

    # Print location of persisted media files for review
    if _MEDIA_REVIEW_DIR and _MEDIA_REVIEW_DIR.exists() and any(_MEDIA_REVIEW_DIR.iterdir()):
        from e2e.runner import file_link

        print(f"\n  Media files saved for review: {_MEDIA_REVIEW_DIR}")
        for sub in sorted(_MEDIA_REVIEW_DIR.iterdir()):
            if sub.is_dir():
                files = list(sub.iterdir())
                if not files:
                    continue
                print(f"    {sub.name}/: {len(files)} file(s)")
                for f in files:
                    print(f"      {file_link(str(f))} ({f.stat().st_size:,} bytes)")


def _has_web_events_stage_col(conn) -> bool:
    """True when web_events has a ``stage`` column (task stage tracking)."""
    try:
        cols = conn.execute("PRAGMA table_info(web_events)").fetchall()
        return any(c[1] == "stage" for c in cols)
    except Exception:
        return False
