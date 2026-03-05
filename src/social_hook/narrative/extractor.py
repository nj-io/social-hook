"""Narrative extractor: analyzes dev session transcripts for social content."""

from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.schemas import ExtractNarrativeInput

SYSTEM_PROMPT = """\
You are a narrative analyst for a developer's social media content pipeline.

Your job is to analyze a development session transcript and extract the key \
narrative elements that could be turned into engaging social media posts.

Focus on:
- **Decisions**: What choices were made and why? What trade-offs were considered?
- **Rejected approaches**: What was tried and didn't work? These often make the \
most interesting content because they show real engineering thinking.
- **Aha moments**: Surprising discoveries, unexpected behaviors, or insights that \
changed the approach.
- **Challenges**: What was difficult? What took longer than expected?
- **Narrative arc**: What's the story of this session? Every good post needs a \
story — a beginning (the problem), middle (the struggle), and end (the resolution).

When evaluating social-media relevance, consider:
- Does this session contain a genuine insight others could learn from?
- Is there a surprising twist or counterintuitive finding?
- Would a developer scrolling their feed stop to read this?
- Does it show real problem-solving, not just routine work?

For social hooks, suggest specific post angles — not generic descriptions. \
A good hook makes readers curious about the answer.

Use the extract_narrative tool to return your analysis.\
"""


class NarrativeExtractor:
    """Extracts narrative elements from dev session transcripts.

    Args:
        client: LLMClient configured with the extraction model.
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def extract(
        self,
        transcript_text: str,
        project_name: str,
        cwd: str,
        db: Any,
        project_id: str,
    ) -> ExtractNarrativeInput:
        """Extract narrative elements from a session transcript.

        Args:
            transcript_text: Formatted transcript text (from format_for_prompt).
            project_name: Name of the project.
            cwd: Working directory of the session.
            db: Database context for usage logging.
            project_id: Project ID for usage tracking.

        Returns:
            Validated ExtractNarrativeInput.

        Raises:
            MalformedResponseError: If the LLM response is missing or invalid.
        """
        user_message = (
            f"Analyze this development session transcript for project "
            f"'{project_name}' (working directory: {cwd}).\n\n"
            f"--- TRANSCRIPT ---\n{transcript_text}\n--- END TRANSCRIPT ---"
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[ExtractNarrativeInput.to_tool_schema()],
            system=SYSTEM_PROMPT,
        )
        log_usage(db, "narrative_extract", getattr(self.client, "full_id", "unknown"),
                  response.usage, project_id)

        tool_input = extract_tool_call(response, "extract_narrative")
        return ExtractNarrativeInput.validate(tool_input)
