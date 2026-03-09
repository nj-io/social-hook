"""Section N: Web Dashboard + Per-Platform scenarios."""

from e2e.constants import COMMITS


def run(harness, runner):
    """N1-N9: Web Dashboard + Per-Platform scenarios."""

    if not harness.project_id:
        harness.seed_project()

    # Enable web config so WebAdapter can init
    harness.update_config({"web": {"enabled": True, "port": 3000}})

    # Lazy import of TestClient + FastAPI app -- these require the patched HOME
    # so DB and config resolve to the isolated temp environment.
    def _get_test_client():
        # Force re-import so module-level state picks up patched paths
        import importlib

        import social_hook.web.server as srv_mod

        importlib.reload(srv_mod)
        from fastapi.testclient import TestClient

        return TestClient(srv_mod.app)

    # N1: API /help command
    def n1():
        client = _get_test_client()
        resp = client.post("/api/command", json={"text": "/help"})
        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "events" in data, f"No 'events' in response: {data}"
        # Check that at least one event contains help text
        found_help = False
        for ev in data["events"]:
            ev_data = ev.get("data", {})
            text = ev_data.get("text", "")
            if "command" in text.lower() or "help" in text.lower():
                found_help = True
                break
        assert found_help, f"No help text found in events: {data['events']}"

        runner.add_review_item(
            "N1",
            title="API /help command via web",
            response=data["events"][0].get("data", {}).get("text", "")[:200]
            if data["events"]
            else "",
            review_question="Is the help text complete and well-formatted?",
        )
        return f"200 OK, {len(data['events'])} events"

    runner.run_scenario("N1", "API /help command", n1)

    # N2: API callback (approve)
    def n2():
        draft = harness.seed_draft(harness.project_id, status="draft")
        client = _get_test_client()
        resp = client.post(
            "/api/callback",
            json={
                "action": "quick_approve",
                "payload": draft.id,
            },
        )
        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "events" in data, f"No 'events' in response: {data}"

        # Verify draft status changed
        from social_hook.db import operations as ops

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status in ("approved", "scheduled"), (
            f"Draft status after approve: {updated.status}"
        )

        return f"Draft {draft.id[:12]} → {updated.status}"

    runner.run_scenario("N2", "API callback (approve)", n2)

    # N3: Trigger with 2 platforms
    def n3():
        from social_hook.db import operations as ops
        from social_hook.trigger import run_trigger

        # Enable both X and LinkedIn
        harness.update_config(
            {
                "platforms": {
                    "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
                    "linkedin": {"enabled": True, "priority": "secondary"},
                },
            }
        )

        exit_code = run_trigger(
            COMMITS["web_dashboard"],
            str(harness.repo_path),
            verbose=runner.verbose,
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        # Check for new drafts
        after_drafts = ops.get_pending_drafts(harness.conn, harness.project_id)

        # We need at least 1 draft. With 2 platforms we expect 2, but the LLM
        # might decide skip. If draft, check platforms differ.
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=5)
        d = decisions[0] if decisions else None

        if d and d.decision == "draft":
            # Look for drafts with different platforms
            platforms_seen = set()
            for draft in after_drafts:
                platforms_seen.add(draft.platform)

            detail = f"Decision: draft, platforms: {platforms_seen}"
            if len(platforms_seen) >= 2:
                detail += " (multi-platform confirmed)"
            else:
                detail += " (only 1 platform - content filter may have excluded one)"

            # Add review items for each platform's draft
            for draft in after_drafts[:2]:
                runner.add_review_item(
                    "N3",
                    title=f"Per-platform draft ({draft.platform})",
                    draft_content=draft.content,
                    review_question=f"Is this draft tailored for {draft.platform}?",
                )
        else:
            detail = f"Decision: {d.decision if d else 'none'} (no multi-platform check)"

        # Restore single-platform config
        harness.update_config(
            {
                "platforms": {
                    "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
                    "linkedin": {"enabled": False},
                },
            }
        )
        return detail

    runner.run_scenario("N3", "Trigger with 2 platforms", n3, llm_call=True, isolate=True)

    # N4: Content filter: notable skips decision episode
    def n4():
        from social_hook.config.platforms import passes_content_filter

        # "all" filter passes everything
        assert passes_content_filter("all", "decision") is True
        assert passes_content_filter("all", "milestone") is True

        # "notable" filter skips "decision" episode_type
        assert passes_content_filter("notable", "decision") is False
        assert passes_content_filter("notable", "milestone") is True
        assert passes_content_filter("notable", "launch") is True
        assert passes_content_filter("notable", "synthesis") is True

        # "significant" filter is even stricter
        assert passes_content_filter("significant", "decision") is False
        assert passes_content_filter("significant", "demo_proof") is False
        assert passes_content_filter("significant", "milestone") is True
        assert passes_content_filter("significant", "launch") is True

        return "Filter logic verified: all > notable > significant"

    runner.run_scenario("N4", "Content filter: notable skips decision", n4)

    # N5: Settings: read config
    def n5():
        client = _get_test_client()
        resp = client.get("/api/settings/config")
        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "config" in data, f"No 'config' in response: {data}"
        config = data["config"]
        assert isinstance(config, dict), f"Config is not dict: {type(config)}"
        assert "platforms" in config, f"No 'platforms' in config: {list(config.keys())}"
        assert isinstance(config["platforms"], dict), (
            f"platforms is not dict: {type(config['platforms'])}"
        )
        return f"Config keys: {list(config.keys())}"

    runner.run_scenario("N5", "Settings: read config", n5)

    # N6: Settings: update platform priority
    def n6():
        client = _get_test_client()

        # Update X priority to secondary
        resp = client.put(
            "/api/settings/config",
            json={
                "platforms": {
                    "x": {"enabled": True, "priority": "secondary", "account_tier": "free"},
                },
            },
        )
        assert resp.status_code == 200, f"PUT status {resp.status_code}: {resp.text}"

        # Re-read and verify
        resp2 = client.get("/api/settings/config")
        config = resp2.json()["config"]
        x_cfg = config.get("platforms", {}).get("x", {})
        assert x_cfg.get("priority") == "secondary", f"Expected priority=secondary, got: {x_cfg}"

        # Restore to primary
        client.put(
            "/api/settings/config",
            json={
                "platforms": {
                    "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
                },
            },
        )
        return "Priority updated and verified"

    runner.run_scenario("N6", "Settings: update platform priority", n6)

    # N7: Settings: add custom platform
    def n7():
        client = _get_test_client()

        resp = client.put(
            "/api/settings/config",
            json={
                "platforms": {
                    "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
                    "blog": {
                        "enabled": True,
                        "type": "custom",
                        "priority": "secondary",
                        "format": "article",
                        "description": "Technical blog",
                    },
                },
            },
        )
        assert resp.status_code == 200, f"PUT status {resp.status_code}: {resp.text}"

        # Re-read and verify
        resp2 = client.get("/api/settings/config")
        config = resp2.json()["config"]
        platforms = config.get("platforms", {})
        assert "blog" in platforms, f"blog not in platforms: {list(platforms.keys())}"
        blog = platforms["blog"]
        assert blog.get("type") == "custom"
        assert blog.get("format") == "article"

        # Clean up: remove blog
        client.put(
            "/api/settings/config",
            json={
                "platforms": {
                    "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
                },
            },
        )
        return "Custom platform 'blog' added and verified"

    runner.run_scenario("N7", "Settings: add custom platform", n7)

    # N8: SSE endpoint streams events
    def n8():
        client = _get_test_client()

        # First send a command to generate some events
        client.post("/api/command", json={"text": "/help"})

        # Now check the SSE endpoint
        resp = client.get("/api/events?lastId=0")
        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, (
            f"Expected text/event-stream, got: {content_type}"
        )
        return f"SSE content-type: {content_type}"

    runner.run_scenario("N8", "SSE endpoint streams events", n8)

    # N9: Media file serving endpoint
    def n9():
        from social_hook.filesystem import get_base_path

        # Create a real media file in the cache
        media_dir = get_base_path() / "media-cache" / "n9_test"
        media_dir.mkdir(parents=True, exist_ok=True)
        media_file = media_dir / "test_image.png"
        # Minimal valid PNG (1x1 pixel)
        png_header = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        media_file.write_bytes(png_header)

        client = _get_test_client()
        from urllib.parse import quote

        rel_path = "n9_test/test_image.png"
        resp = client.get(f"/api/media/{quote(rel_path)}")
        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"

        content_type = resp.headers.get("content-type", "")
        assert "image/png" in content_type, f"Expected image/png, got: {content_type}"
        assert len(resp.content) > 0, "Empty response body"

        # Path traversal protection
        resp_bad = client.get("/api/media/../../../etc/passwd")
        assert resp_bad.status_code in (403, 404), (
            f"Path traversal should fail, got {resp_bad.status_code}"
        )

        return f"Served {len(resp.content)} bytes, content-type={content_type}"

    runner.run_scenario("N9", "Media file serving endpoint", n9)
