"""Section F: Bot Commands scenarios."""

from datetime import datetime, timezone

from e2e.constants import COMMITS


def run(harness, runner, adapter):
    """F1-F13: Bot command scenarios."""
    from social_hook.messaging.base import InboundMessage

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    def make_message(text):
        return InboundMessage(
            message_id="1",
            chat_id=chat_id,
            sender_id=chat_id,
            text=text,
        )

    from social_hook.bot.commands import handle_command

    # F1: Help
    def f1():
        adapter.clear()
        handle_command(make_message("/help"), adapter, config)
        assert adapter.last_message_contains("command"), "Expected 'command' in response"
        return "Help sent"

    runner.run_scenario("F1", "Help command", f1)

    # F2: Status with data
    def f2():
        adapter.clear()
        handle_command(make_message("/status"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Status sent"

    runner.run_scenario("F2", "Status with data", f2)

    # F3: Status empty (tested with real state — may have projects)
    def f3():
        adapter.clear()
        handle_command(make_message("/status"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Status sent"

    runner.run_scenario("F3", "Status (may have data)", f3)

    # F4: Pending list
    def f4():
        # Seed a pending draft
        harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_command(make_message("/pending"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Pending list sent"

    runner.run_scenario("F4", "Pending list", f4)

    # F5: Pending empty
    def f5():
        adapter.clear()
        handle_command(make_message("/pending"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Pending response sent"

    runner.run_scenario("F5", "Pending (may be empty)", f5)

    # F6: Projects list
    def f6():
        adapter.clear()
        handle_command(make_message("/projects"), adapter, config)
        assert adapter.messages, "No message sent"
        msg = adapter.last_message()
        assert "social-media-auto-hook" in msg["text"].lower() or "project" in msg["text"].lower()
        return "Projects listed"

    runner.run_scenario("F6", "Projects list", f6)

    # F7: Usage summary
    def f7():
        adapter.clear()
        handle_command(make_message("/usage"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Usage sent"

    runner.run_scenario("F7", "Usage summary", f7)

    # F8: Review draft
    def f8():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_command(make_message(f"/review {draft.id}"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Review sent"

    runner.run_scenario("F8", "Review draft", f8)

    # F9: Unknown command
    def f9():
        adapter.clear()
        handle_command(make_message("/foo"), adapter, config)
        assert adapter.messages, "No message sent"
        assert adapter.last_message_contains("unknown") or adapter.last_message_contains(
            "not recognized"
        )
        return "Unknown command handled"

    runner.run_scenario("F9", "Unknown command", f9)

    # F10: Pause project
    def f10():
        from social_hook.db import operations as ops

        adapter.clear()
        handle_command(make_message(f"/pause {harness.project_id}"), adapter, config)

        project = ops.get_project(harness.conn, harness.project_id)
        assert project.paused is True, f"paused={project.paused}"

        # Unpause for remaining tests
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()
        return "Project paused"

    runner.run_scenario("F10", "Pause project", f10)

    # F11: Resume project
    def f11():
        from social_hook.db import operations as ops

        # Pause first
        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        adapter.clear()
        handle_command(make_message(f"/resume {harness.project_id}"), adapter, config)

        project = ops.get_project(harness.conn, harness.project_id)
        assert project.paused is False, f"paused={project.paused}"
        return "Project resumed"

    runner.run_scenario("F11", "Resume project", f11)

    # F12: Scheduled list
    def f12():
        harness.seed_draft(
            harness.project_id,
            status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        adapter.clear()
        handle_command(make_message("/scheduled"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Scheduled list sent"

    runner.run_scenario("F12", "Scheduled list", f12)

    # F13: Review shows evaluator context (episode_type, angle, post_category)
    def f13():
        from social_hook.db import insert_decision, insert_draft
        from social_hook.filesystem import generate_id
        from social_hook.models import Decision, Draft

        # Seed a decision with angle and episode_type populated
        decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=COMMITS["significant"],
            decision="draft",
            reasoning="Great feature launch with demo potential",
            episode_type="demo_proof",
            post_category="arc",
            angle="Show how the trigger pipeline works end-to-end",
        )
        insert_decision(harness.conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=harness.project_id,
            decision_id=decision.id,
            platform="x",
            content="Just shipped: end-to-end trigger pipeline!",
            status="draft",
        )
        insert_draft(harness.conn, draft)
        harness.conn.commit()

        adapter.clear()
        handle_command(make_message(f"/review {draft.id}"), adapter, config)

        assert adapter.messages, "No message sent"
        msg_text = adapter.last_message()["text"]
        assert "Episode:" in msg_text or "episode" in msg_text.lower(), (
            "Expected episode_type in review output"
        )
        assert "Angle:" in msg_text or "angle" in msg_text.lower(), (
            "Expected angle in review output"
        )
        return "Review shows episode_type and angle"

    runner.run_scenario("F13", "Review shows evaluator context", f13)
