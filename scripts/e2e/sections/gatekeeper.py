"""Section H: Bot Free-Text (Gatekeeper) scenarios."""


def run(harness, runner, adapter):
    """H1-H5: Bot free-text scenarios."""
    from social_hook.messaging.base import InboundMessage

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    from social_hook.bot.commands import handle_message

    def make_message(text):
        return InboundMessage(
            message_id="1",
            chat_id=chat_id,
            sender_id=chat_id,
            text=text,
        )

    # H1: Query message
    def h1():
        # Seed a draft so there's something to query
        harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_message(make_message("what's pending?"), adapter, config)
        assert adapter.messages, "No response sent"

        runner.add_review_item(
            "H1",
            title='Gatekeeper: "what\'s pending?"',
            response=adapter.last_message()["text"] if adapter.messages else "",
            review_question="Helpful and accurate?",
        )
        return "Gatekeeper responded"

    runner.run_scenario("H1", "Query message -> gatekeeper routes", h1)

    # H2: Expert escalation
    def h2():
        harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_message(make_message("make it punchier"), adapter, config)
        assert adapter.messages, "No response sent"

        runner.add_review_item(
            "H2",
            title='Expert escalation: "make it punchier"',
            response=adapter.last_message()["text"] if adapter.messages else "",
            review_question="Did the expert improve the content?",
        )
        return "Expert escalation handled"

    runner.run_scenario("H2", "Expert escalation", h2)

    # H3: Substitute via gatekeeper
    def h3():
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import operations as ops

        draft = harness.seed_draft(
            harness.project_id, status="draft", content="Old draft content for substitution"
        )
        set_chat_draft_context(chat_id, draft.id, harness.project_id)

        adapter.clear()
        handle_message(
            make_message("use this instead: Brand new post content about automation"),
            adapter,
            config,
        )
        assert adapter.messages, "No response sent"

        # Check if draft content was updated (gatekeeper should route to substitute)
        updated = ops.get_draft(harness.conn, draft.id)
        content_changed = updated.content != "Old draft content for substitution"

        # Check for DraftChange row if content changed
        if content_changed:
            changes = ops.get_draft_changes(harness.conn, draft.id)
            assert len(changes) >= 1, "Expected DraftChange row after substitute"

        runner.add_review_item(
            "H3",
            title='Substitute via gatekeeper: "use this instead: ..."',
            response=adapter.last_message()["text"] if adapter.messages else "",
            review_question="Did the Gatekeeper correctly route to substitute? Is the content saved accurately?",
            content_changed=content_changed,
        )
        return f"Substitute handled, content_changed={content_changed}"

    runner.run_scenario("H3", "Substitute via gatekeeper", h3, llm_call=True)

    # H4: Expert refine saves to DB
    def h4():
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import operations as ops

        draft = harness.seed_draft(
            harness.project_id, status="draft", content="Original draft for expert refinement test"
        )
        set_chat_draft_context(chat_id, draft.id, harness.project_id)

        adapter.clear()
        handle_message(make_message("make it punchier and more engaging"), adapter, config)
        assert adapter.messages, "No response sent"

        # Check if expert refined and saved
        updated = ops.get_draft(harness.conn, draft.id)
        content_changed = updated.content != "Original draft for expert refinement test"

        if content_changed:
            changes = ops.get_draft_changes(harness.conn, draft.id)
            expert_changes = [c for c in changes if c.changed_by == "expert"]
            assert len(expert_changes) >= 1, "Expected DraftChange with changed_by='expert'"

        runner.add_review_item(
            "H4",
            title='Expert refine: "make it punchier and more engaging"',
            response=adapter.last_message()["text"] if adapter.messages else "",
            review_question="Did the Expert improve the draft? Is the refined content better than the original?",
            content_changed=content_changed,
            original="Original draft for expert refinement test",
            refined=updated.content if content_changed else "(unchanged)",
        )
        return f"Expert refine handled, content_changed={content_changed}"

    runner.run_scenario("H4", "Expert refine saves to DB", h4, llm_call=True)

    # H5: Gatekeeper receives draft context
    def h5():
        from unittest.mock import patch as _patch

        from social_hook.bot.commands import set_chat_draft_context

        draft = harness.seed_draft(
            harness.project_id, status="draft", content="Draft content for context threading test"
        )
        set_chat_draft_context(chat_id, draft.id, harness.project_id)

        # Capture Gatekeeper.route() args while still calling through
        captured_args = {}

        original_route = None

        def capture_route(self, *args, **kwargs):
            captured_args["draft_context"] = kwargs.get("draft_context")
            captured_args["project_id"] = kwargs.get("project_id")
            return original_route(self, *args, **kwargs)

        from social_hook.llm.gatekeeper import Gatekeeper

        original_route = Gatekeeper.route

        with _patch.object(Gatekeeper, "route", capture_route):
            adapter.clear()
            handle_message(
                make_message("what do you think of this draft?"),
                adapter,
                config,
            )

        assert captured_args.get("draft_context") is not None, (
            "Expected draft_context to be passed to Gatekeeper.route()"
        )
        assert captured_args.get("project_id") is not None, (
            "Expected project_id to be passed to Gatekeeper.route()"
        )

        runner.add_review_item(
            "H5",
            title='Gatekeeper context threading: "what do you think of this draft?"',
            response=adapter.last_message()["text"] if adapter.messages else "",
            review_question="Is the Gatekeeper's response more contextual now? Does it reference the draft content?",
        )
        return "Gatekeeper received draft context and project_id"

    runner.run_scenario("H5", "Gatekeeper receives draft context", h5, llm_call=True)
