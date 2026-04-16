"""Tests for project brief generation and maintenance."""

from unittest.mock import MagicMock

from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.brief import (
    BRIEF_SECTIONS,
    _heading_to_slug,
    generate_brief_from_docs,
    generate_initial_brief,
    get_brief_sections,
    update_brief_from_commit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Create a mock LLM client that returns a tool call response."""
    client = MagicMock()
    client.full_id = "test/mock"
    response = NormalizedResponse(
        content=[NormalizedToolCall(type="tool_use", name=tool_name, input=tool_input)],
        usage=NormalizedUsage(),
    )
    client.complete.return_value = response
    return client


SAMPLE_BRIEF = """\
## What It Does

Social Hook automatically generates social media content from development activity.

## Key Capabilities

- Evaluates git commits for post-worthiness
- Drafts platform-specific content
- Multi-platform posting (X, LinkedIn)

## Technical Architecture

Python CLI + web dashboard. SQLite storage. LLM-based evaluation and drafting pipeline.

## Current State

Active development. Scheduler, multi-platform posting, and narrative arcs are stable."""


# ---------------------------------------------------------------------------
# get_brief_sections
# ---------------------------------------------------------------------------


class TestGetBriefSections:
    def test_parses_all_sections(self):
        sections = get_brief_sections(SAMPLE_BRIEF)
        assert len(sections) == 4
        assert "what_it_does" in sections
        assert "key_capabilities" in sections
        assert "technical_architecture" in sections
        assert "current_state" in sections

    def test_content_preserved(self):
        sections = get_brief_sections(SAMPLE_BRIEF)
        assert "automatically generates social media" in sections["what_it_does"]
        assert "Evaluates git commits" in sections["key_capabilities"]
        assert "SQLite storage" in sections["technical_architecture"]
        assert "Active development" in sections["current_state"]

    def test_empty_string(self):
        assert get_brief_sections("") == {}

    def test_none_input(self):
        assert get_brief_sections(None) == {}  # type: ignore[arg-type]

    def test_no_sections(self):
        assert get_brief_sections("Just some text with no headings") == {}

    def test_freeform_sections_accepted(self):
        """Arbitrary ## headings are accepted and slugified."""
        brief = "## Unknown Section\n\nSome content"
        sections = get_brief_sections(brief)
        assert "unknown_section" in sections
        assert sections["unknown_section"] == "Some content"

    def test_mixed_known_and_freeform(self):
        """Mix of canonical and freeform sections."""
        brief = "## What It Does\n\nA tool.\n\n## Target Audience\n\nDevelopers."
        sections = get_brief_sections(brief)
        assert sections["what_it_does"] == "A tool."
        assert sections["target_audience"] == "Developers."

    def test_partial_sections(self):
        brief = "## What It Does\n\nJust this section."
        sections = get_brief_sections(brief)
        assert len(sections) == 1
        assert sections["what_it_does"] == "Just this section."

    def test_roundtrip(self):
        """Sections parsed from a brief can be re-assembled."""
        sections = get_brief_sections(SAMPLE_BRIEF)
        # All 4 sections should be present
        for key in BRIEF_SECTIONS:
            assert key in sections


# ---------------------------------------------------------------------------
# generate_initial_brief
# ---------------------------------------------------------------------------


class TestGenerateInitialBrief:
    def test_produces_structured_markdown(self):
        tool_input = {
            "what_it_does": "A tool for X.",
            "key_capabilities": "- Feature A\n- Feature B",
            "technical_architecture": "Built with Python.",
            "current_state": "In active development.",
        }
        client = _make_client_response("generate_brief", tool_input)

        brief = generate_initial_brief("Some discovery summary", client)
        assert "## What It Does" in brief
        assert "## Key Capabilities" in brief
        assert "## Technical Architecture" in brief
        assert "## Current State" in brief
        assert "A tool for X." in brief

    def test_sections_parseable(self):
        tool_input = {
            "what_it_does": "Does things.",
            "key_capabilities": "Capabilities.",
            "technical_architecture": "Architecture.",
            "current_state": "State.",
        }
        client = _make_client_response("generate_brief", tool_input)

        brief = generate_initial_brief("Summary", client)
        sections = get_brief_sections(brief)
        assert sections["what_it_does"] == "Does things."
        assert sections["current_state"] == "State."

    def test_returns_empty_on_failure(self):
        client = MagicMock()
        client.full_id = "test/mock"
        # No tool call in response
        client.complete.return_value = NormalizedResponse(content=[], usage=NormalizedUsage())

        brief = generate_initial_brief("Summary", client)
        assert brief == ""

    def test_usage_logged(self):
        tool_input = {
            "what_it_does": "X",
            "key_capabilities": "Y",
            "technical_architecture": "Z",
            "current_state": "W",
        }
        client = _make_client_response("generate_brief", tool_input)
        db = MagicMock()

        generate_initial_brief("Summary", client, db=db, project_id="proj-1")
        # log_usage is called (via the module-level function)
        # Just verify the client was called
        client.complete.assert_called_once()


# ---------------------------------------------------------------------------
# update_brief_from_commit
# ---------------------------------------------------------------------------


class TestUpdateBriefFromCommit:
    def test_incremental_update(self):
        tool_input = {
            "what_it_does": "Social Hook automatically generates social media content from development activity.",
            "key_capabilities": "- Evaluates git commits for post-worthiness\n- Drafts platform-specific content\n- Multi-platform posting (X, LinkedIn)",
            "technical_architecture": "Python CLI + web dashboard. SQLite storage. LLM-based evaluation and drafting pipeline.",
            "current_state": "Now includes OAuth 2.0 support for X platform.",
            "updated_sections": ["current_state"],
        }
        client = _make_client_response("update_brief", tool_input)

        updated_brief, metadata, changed = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Added OAuth 2.0 token refresh for X adapter",
            commit_analysis_tags=["feature", "auth"],
            client=client,
        )
        assert "OAuth 2.0" in updated_brief
        assert "current_state" in changed
        assert metadata["current_state"]["last_edited_by"] == "system"

    def test_preserves_unchanged_sections(self):
        """Unchanged sections keep their original content."""
        tool_input = {
            "what_it_does": "New text from LLM",
            "key_capabilities": "New caps",
            "technical_architecture": "New arch",
            "current_state": "Updated state.",
            "updated_sections": ["current_state"],
        }
        client = _make_client_response("update_brief", tool_input)

        updated_brief, _, changed = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Minor change",
            commit_analysis_tags=[],
            client=client,
        )
        sections = get_brief_sections(updated_brief)
        # Only current_state should change
        assert "current_state" in changed
        # Unchanged sections preserve original content
        original_sections = get_brief_sections(SAMPLE_BRIEF)
        assert sections["what_it_does"] == original_sections["what_it_does"]
        assert sections["key_capabilities"] == original_sections["key_capabilities"]

    def test_operator_edited_sections_passed_to_llm(self):
        """Operator-edited metadata is passed in the system prompt."""
        tool_input = {
            "what_it_does": "Operator wrote this.",
            "key_capabilities": "Updated caps.",
            "technical_architecture": "Arch.",
            "current_state": "State.",
            "updated_sections": ["key_capabilities"],
        }
        client = _make_client_response("update_brief", tool_input)

        section_metadata = {
            "what_it_does": {
                "last_edited_by": "operator",
                "last_edited_at": "2026-03-20T00:00:00+00:00",
            }
        }

        _, _, changed = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Some change",
            commit_analysis_tags=[],
            client=client,
            section_metadata=section_metadata,
        )

        # Verify the system prompt mentions operator-edited
        call_kwargs = client.complete.call_args
        system_prompt = call_kwargs.kwargs.get("system", "") or call_kwargs[1].get("system", "")
        assert "OPERATOR-EDITED" in system_prompt

    def test_empty_brief_returns_unchanged(self):
        client = MagicMock()
        brief, meta, changed = update_brief_from_commit(
            current_brief="",
            commit_analysis_summary="Something",
            commit_analysis_tags=[],
            client=client,
        )
        assert brief == ""
        assert changed == []
        client.complete.assert_not_called()

    def test_returns_original_on_failure(self):
        client = MagicMock()
        client.full_id = "test/mock"
        client.complete.return_value = NormalizedResponse(content=[], usage=NormalizedUsage())

        brief, _, changed = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Something",
            commit_analysis_tags=[],
            client=client,
        )
        assert brief == SAMPLE_BRIEF
        assert changed == []

    def test_metadata_updated_for_changed_sections(self):
        tool_input = {
            "what_it_does": "Same.",
            "key_capabilities": "New capabilities added.",
            "technical_architecture": "Same.",
            "current_state": "Same.",
            "updated_sections": ["key_capabilities"],
        }
        client = _make_client_response("update_brief", tool_input)

        _, metadata, _ = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Added new feature",
            commit_analysis_tags=["feature"],
            client=client,
        )
        assert metadata["key_capabilities"]["last_edited_by"] == "system"
        assert "last_edited_at" in metadata["key_capabilities"]


# ---------------------------------------------------------------------------
# Freeform brief sections (Phase 3a)
# ---------------------------------------------------------------------------


class TestFreeformBriefSections:
    def test_heading_to_slug(self):
        assert _heading_to_slug("What It Does") == "what_it_does"
        assert _heading_to_slug("Target Audience") == "target_audience"
        assert _heading_to_slug("API Reference (v2)") == "api_reference_v2"

    def test_freeform_generate_with_sections_key(self):
        """New-style generate_brief response using 'sections' dict."""
        tool_input = {
            "sections": {
                "What It Does": "A tool for X.",
                "Target Audience": "Developers and DevOps engineers.",
                "Technical Architecture": "Built with Python.",
            }
        }
        client = _make_client_response("generate_brief", tool_input)

        brief = generate_initial_brief("Some discovery summary", client)
        assert "## What It Does" in brief
        assert "## Target Audience" in brief
        assert "A tool for X." in brief
        assert "Developers and DevOps engineers." in brief

    def test_freeform_sections_parsed_back(self):
        """Freeform sections round-trip through parse -> render."""
        brief = (
            "## What It Does\n\nA tool.\n\n"
            "## Target Audience\n\nDevelopers.\n\n"
            "## Deployment Guide\n\nRun docker compose."
        )
        sections = get_brief_sections(brief)
        assert len(sections) == 3
        assert sections["what_it_does"] == "A tool."
        assert sections["target_audience"] == "Developers."
        assert sections["deployment_guide"] == "Run docker compose."

    def test_update_with_freeform_sections(self):
        """Update brief supports freeform sections dict."""
        tool_input = {
            "sections": {
                "What It Does": "Social Hook does X.",
                "Key Capabilities": "Features.",
                "Technical Architecture": "Python.",
                "Current State": "Updated state.",
                "New Section": "New content here.",
            },
            "updated_sections": ["Current State", "New Section"],
        }
        client = _make_client_response("update_brief", tool_input)

        updated_brief, metadata, changed = update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="Major update",
            commit_analysis_tags=["feature"],
            client=client,
        )
        assert "Updated state." in updated_brief
        assert "New content here." in updated_brief

    def test_update_with_analyzer_guidance(self):
        """update_brief_from_commit passes analyzer guidance through."""
        tool_input = {
            "sections": {
                "What It Does": "Tool for X.",
                "Current State": "Now with OAuth.",
            },
            "updated_sections": ["Current State"],
        }
        client = _make_client_response("update_brief", tool_input)

        update_brief_from_commit(
            current_brief=SAMPLE_BRIEF,
            commit_analysis_summary="OAuth added",
            commit_analysis_tags=["auth"],
            client=client,
            sections_to_update={"Current State": "Add OAuth support info"},
            new_facts=["OAuth 2.0 token refresh implemented"],
        )
        # Verify the user message includes guidance
        call_kwargs = client.complete.call_args
        user_msg = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages", []))[0][
            "content"
        ]
        assert "OAuth support" in user_msg or "OAuth 2.0 token" in user_msg


# ---------------------------------------------------------------------------
# generate_brief_from_docs (Phase 3c)
# ---------------------------------------------------------------------------


class TestGenerateBriefFromDocs:
    def test_generates_brief_from_doc_files(self, tmp_path):
        (tmp_path / "readme.md").write_text("# My Project\n\nA tool for building things.")
        (tmp_path / "guide.md").write_text("## Usage\n\nRun `make build`.")

        tool_input = {
            "sections": {
                "What It Does": "A tool for building things.",
                "Target Audience": "Developers.",
            }
        }
        client = _make_client_response("generate_brief", tool_input)

        brief = generate_brief_from_docs(
            ["readme.md", "guide.md"],
            str(tmp_path),
            client,
        )
        assert "## What It Does" in brief
        assert "A tool for building things." in brief

    def test_returns_empty_when_no_files(self, tmp_path):
        client = MagicMock()
        client.full_id = "test/mock"

        brief = generate_brief_from_docs(
            ["nonexistent.md"],
            str(tmp_path),
            client,
        )
        assert brief == ""
        client.complete.assert_not_called()


# ---------------------------------------------------------------------------
# Brief update gate (Phase 3b)
# ---------------------------------------------------------------------------


class TestBriefUpdateGate:
    def test_gate_returns_false_when_no_analyzer_result(self):
        from social_hook.trigger_side_effects import _trigger_brief_update

        result = _trigger_brief_update(
            evaluation=MagicMock(),
            analysis=MagicMock(episode_tags=["feature"]),
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="proj-1"),
            evaluator_client=MagicMock(),
            dry_run=False,
            verbose=False,
            analyzer_result=None,
        )
        assert result is False

    def test_gate_returns_false_when_no_brief_update(self):
        from social_hook.trigger_side_effects import _trigger_brief_update

        analyzer_result = MagicMock()
        analyzer_result.brief_update = None

        result = _trigger_brief_update(
            evaluation=MagicMock(),
            analysis=MagicMock(episode_tags=["feature"]),
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="proj-1"),
            evaluator_client=MagicMock(),
            dry_run=False,
            verbose=False,
            analyzer_result=analyzer_result,
        )
        assert result is False

    def test_gate_returns_false_when_empty_guidance(self):
        from social_hook.trigger_side_effects import _trigger_brief_update

        analyzer_result = MagicMock()
        analyzer_result.brief_update.sections_to_update = {}
        analyzer_result.brief_update.new_facts = []

        result = _trigger_brief_update(
            evaluation=MagicMock(),
            analysis=MagicMock(episode_tags=["feature"]),
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="proj-1"),
            evaluator_client=MagicMock(),
            dry_run=False,
            verbose=False,
            analyzer_result=analyzer_result,
        )
        assert result is False
