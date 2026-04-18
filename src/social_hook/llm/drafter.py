"""Drafter agent: creates social media content (T14)."""

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from social_hook.adapters.models import SINGLE_IMAGE
from social_hook.config.project import ContextConfig
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id

if TYPE_CHECKING:
    from social_hook.config.platforms import ResolvedPlatformConfig
    from social_hook.config.project import MediaToolGuidance
    from social_hook.config.yaml import MediaGenerationConfig
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.catalog import get_model_info
from social_hook.llm.prompts import assemble_drafter_prompt, load_prompt
from social_hook.llm.schemas import CreateDraftInput  # re-exported types
from social_hook.media_tokens import TOKEN_RE
from social_hook.models.context import ProjectContext
from social_hook.models.core import CommitInfo

logger = logging.getLogger(__name__)

# Upload size and allowed image formats — single source of truth is the
# SINGLE_IMAGE MediaMode. 5 MiB / {png, jpg, jpeg, webp, gif}. BMP/TIFF
# are re-encoded to PNG before being sent to the LLM.
_UPLOAD_MAX_SIZE = SINGLE_IMAGE.max_size or 5_242_880
_UPLOAD_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
_UPLOAD_REENCODE_EXTS = {"bmp", "tiff", "tif"}

# Allowed tool names for the post-LLM strip step. Must match schemas.
_ALLOWED_TOOLS = {"nano_banana_pro", "mermaid", "ray_so", "playwright", "legacy_upload"}

# Fields every sane spec must carry. Hallucinations missing these get
# stripped post-validation.
_REQUIRED_SPEC_FIELDS = {"id", "tool", "spec"}

# Literal placeholder strings the drafter sometimes copies verbatim from
# schema/prompt examples. Any content token whose id matches one of these
# is dropped outright — there is no spec id it could possibly refer to.
# Case-insensitive match.
#
# Note: angle-bracketed variants like ``<id>`` are NOT listed because the
# token regex (media_tokens.TOKEN_RE) excludes ``<`` and ``>`` from the
# id character class, so ``(media:<id>)`` never registers as a token
# and passes through the repair step untouched. It will remain visible
# in the rendered markdown, but that's the correct user-visible signal
# that the drafter copied a placeholder.
_LITERAL_PLACEHOLDER_IDS = {
    "id",
    "media_id",
    "media",
    "example",
    "placeholder",
    "xxx",
    "xyz",
}


class Drafter:
    """Creates draft social media content from evaluation decisions.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _build_platform_entries(
        platform_configs: list[tuple[str, Any]],
        intro_states: dict[str, dict] | None = None,
    ):
        """Yield (platform_name, config, intro_state) tuples, deduplicated by platform name."""
        seen: set[str] = set()
        states = intro_states or {}
        for pname, pconfig in platform_configs:
            if pname in seen:
                continue
            seen.add(pname)
            yield pname, pconfig, states.get(pname, {})

    def create_draft(
        self,
        decision: Any,
        project_context: ProjectContext,
        commit: CommitInfo,
        db: Any,
        platform: str = "x",
        tier: str = "free",
        vehicle: str | None = None,
        arc_context: dict[str, Any] | None = None,
        config: ContextConfig | None = None,
        platform_config: Optional["ResolvedPlatformConfig"] = None,
        platform_configs: list[tuple[str, Any]] | None = None,
        media_config: Optional["MediaGenerationConfig"] = None,
        media_guidance: dict[str, "MediaToolGuidance"] | None = None,
        referenced_posts: list | None = None,
        platform_introduced: bool | None = None,
        identity: Any | None = None,
        target_post_count: int = 0,
        is_first_post: bool = False,
        first_post_date: str | None = None,
        content_source_context: dict[str, str] | None = None,
        platform_intro_states: dict[str, dict] | None = None,
        project_docs_text: str | None = None,
        uploads: list[Any] | None = None,
    ) -> CreateDraftInput:
        """Create a draft post for a post-worthy commit (1-pass, all vehicles).

        Args:
            decision: Evaluation decision (evaluation result)
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform (x, linkedin)
            tier: Account tier (free, premium, premium_plus)
            vehicle: Content vehicle preference ("single", "thread", "article", or None)
            arc_context: Arc metadata + posts (when post_category == 'arc')
            config: Context config for doc inclusion
            platform_config: Resolved platform configuration
            platform_configs: Multiple platform configs for shared group calls
            media_config: Media generation config (enabled tools)
            media_guidance: Per-tool content guidance
            referenced_posts: Posts to reference in the draft
            platform_introduced: Whether this platform has been introduced
            identity: Resolved IdentityConfig for this platform
            target_post_count: Posts published on this platform
            is_first_post: Whether this is the first post
            first_post_date: Earliest posted_at for this platform
            content_source_context: Resolved content source context
            platform_intro_states: Per-platform intro state for shared groups

        Returns:
            Validated CreateDraftInput from the LLM
        """
        prompt = load_prompt("drafter")

        recent_posts = project_context.recent_posts

        system = assemble_drafter_prompt(
            prompt,
            decision,
            project_context,
            recent_posts,
            commit,
            arc_context=arc_context,
            config=config,
            media_config=media_config,
            media_guidance=media_guidance,
            referenced_posts=referenced_posts,
            platform_name=platform,
            identity=identity,
            target_post_count=target_post_count,
            is_first_post=is_first_post,
            first_post_date=first_post_date,
            content_source_context=content_source_context,
            project_docs_text=project_docs_text,
        )

        # Build narrative-aware user message
        episode_info = ""
        if hasattr(decision, "post_category") and decision.post_category:
            episode_info += f"Post category: {decision.post_category}. "

        # Include evaluator's angle if available
        angle_info = ""
        if hasattr(decision, "angle") and decision.angle:
            angle_info = f"Angle: {decision.angle}\n"

        # Introduction context for first-ever posts on this platform
        intro_info = ""
        is_intro = (
            platform_introduced is False
            if platform_introduced is not None
            else not project_context.all_introduced
        )
        if is_intro:
            intro_info = (
                "IMPORTANT: This is the FIRST POST for this project on this platform. "
                "The audience has never heard of it. Write a substantial introductory "
                "post that tells the story of what this project is, what "
                "problem it solves, and why it matters. Give the reader enough depth "
                "to understand and care. Don't just summarize "
                "the commit — introduce the project. Use the README and "
                "project documentation in the system prompt for context.\n"
            )

        # Vehicle-specific instructions injected into user message
        vehicle_instruction = ""
        if vehicle == "thread":
            vehicle_instruction = (
                "\nVehicle: THREAD. Write as a thread (minimum 4 parts, numbered 1/, 2/, etc.). "
                "Each part must be ≤280 characters. One beat per part. Structure for visual separation.\n"
            )
        elif vehicle == "article":
            vehicle_instruction = (
                "\nVehicle: ARTICLE. Write long-form structured content. "
                "Use headings, sections, and full paragraphs. No character limits. "
                "Aim for depth and completeness.\n"
            )
        else:
            vehicle_instruction = (
                "\nChoose the best vehicle for this content and set the `vehicle` field accordingly:\n"
                "- `single`: Self-contained post. Best for punchy insights, quick updates, opinions.\n"
                "- `thread`: Multi-part narrative (4+ connected posts, numbered 1/, 2/). Best for walkthroughs, step-by-step, breakdowns.\n"
                "- `article`: Long-form structured content with sections. Best for deep dives, tutorials, comprehensive analyses.\n"
                "Note whether the Angle already defines a preference for the desired vehicle.\n"
            )

        if platform_configs:
            # Multi-platform shared group: build user message with all platform constraints
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            platform_blocks = []
            for i, (pname, pconfig, pintro_state) in enumerate(
                self._build_platform_entries(platform_configs, platform_intro_states), 1
            ):
                pc_tier = pconfig.account_tier or "free"
                char_limit = TIER_CHAR_LIMITS.get(pc_tier, 25000)
                block = f"{i}. {pname} ({pc_tier} tier, {char_limit} char limit)"
                # Platform-specific guidance
                if pname == "x" and pc_tier == "free":
                    block += " — use Format Selection Framework: punchy (<100), detailed (240-280), or thread (4+ beats)"
                elif pname == "x":
                    block += " — use Format Selection Framework, write at whatever length serves the narrative"
                elif pname == "linkedin":
                    block += " — professional tone, 3-5 hashtags, max 3000 chars"
                # Per-platform intro state
                if pintro_state.get("is_first"):
                    block += "\n   First post on this platform. Write an introductory post."
                elif pintro_state.get("post_count"):
                    block += f"\n   {pintro_state['post_count']} previous posts on this platform."
                platform_blocks.append(block)

            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create content for this commit across multiple platforms.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"Platform variants needed:\n"
                + "\n".join(platform_blocks)
                + "\n\nUse the `variants` array to produce one content variant per platform.\n"
                "Share the same angle/narrative but optimize format and length per platform.\n"
                "Media is shared — set media_type/media_spec once at the top level."
            )
        elif platform_config and platform_config.name == "preview":
            # Generic preview: no platform constraints
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a social media post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"This is a preview draft — no platform constraints. "
                f"Write at whatever length and format best serves the content. "
                f"Do not apply character limits or thread formatting."
            )
        elif platform_config:
            # Build platform-specific instructions from resolved config
            pname = platform_config.name
            platform_desc = f"Platform: {pname}"
            if platform_config.priority:
                platform_desc += f" ({platform_config.priority})"
            pc_tier = platform_config.account_tier or "free"
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS.get(pc_tier, 25000)
            platform_desc += f", {pc_tier} tier, {char_limit} char limit"
            if platform_config.max_length:
                platform_desc += f", max {platform_config.max_length} chars"
            if platform_config.format:
                platform_desc += f", format: {platform_config.format}"
            if platform_config.description:
                platform_desc += f"\nContext: {platform_config.description}"

            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {pname} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"{platform_desc}"
            )

            # X free tier specific format guidance (only if no vehicle override)
            if not vehicle:
                if pname == "x" and pc_tier == "free":
                    user_content += (
                        "\nUse the Format Selection Framework: punchy (<100), detailed (240-280), "
                        "or set vehicle='thread' if this needs multiple beats (4+). "
                        "Avoid links in main post."
                    )
                elif pname == "x":
                    user_content += (
                        "\nUse the Format Selection Framework. Write at whatever length serves the narrative. "
                        "Set beat_count for narrative beats. vehicle='thread' for visual separation."
                    )
        elif platform == "x" and tier == "free":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X (free tier). Single post limit: {char_limit} chars. "
            )
            if not vehicle:
                user_content += (
                    "Use the Format Selection Framework: punchy (<100), detailed (240-280), "
                    "or set vehicle='thread' if this needs multiple beats (4+). "
                    "Avoid links in main post."
                )
        elif platform == "x":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X ({tier} tier). Single post limit: {char_limit} chars. "
            )
            if not vehicle:
                user_content += (
                    "Use the Format Selection Framework. For multi-beat content, you can write "
                    "a single flowing post OR set vehicle='thread' for visual beat separation. "
                    "Set beat_count to indicate how many narrative beats your content has. "
                    "Write at whatever length serves the narrative."
                )
        else:
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}"
            )

        # If the operator pre-uploaded reference images, assemble a
        # content-block message (text + base64 image blocks). Fail LOUDLY
        # (ConfigError) when the configured drafter model is not vision-
        # capable — never silently fall through to text-only.
        #
        # Pre-seed a user_uploaded MediaSpecItem per upload so the LLM sees
        # them as structured input and understands each one must appear in
        # the output media_specs (with matching id in a content token).
        # Post-LLM reconciliation re-injects any the drafter dropped.
        preseeded_specs: list[dict[str, Any]] = []
        if uploads:
            full_id = getattr(self.client, "full_id", None)
            info = get_model_info(full_id) if full_id else None
            if info is None or not info.supports_vision:
                raise ConfigError(
                    f"Drafter model {full_id!r} does not support image inputs. "
                    f"Use a vision-capable model "
                    f"(e.g. anthropic/claude-sonnet-4-5, claude-cli/sonnet, "
                    f"openai/gpt-4o) or remove reference images."
                )
            preseeded_specs = _preseed_upload_specs(uploads)
            message_content: Any = _assemble_vision_content(user_content, uploads, preseeded_specs)
        else:
            message_content = user_content

        response = self.client.complete(
            messages=[{"role": "user", "content": message_content}],
            tools=[CreateDraftInput.to_tool_schema()],
            system=system,
        )
        log_usage(
            db,
            "draft",
            getattr(self.client, "full_id", "unknown"),
            response.usage,
            project_context.project.id,
            commit.hash,
        )

        tool_input = extract_tool_call(response, "create_draft")
        # TEMP: env-gated raw-tool-call trace for E2E V8/V14 diagnosis.
        # Reverted after root-cause fixes land.
        _trace_dir = os.environ.get("SOCIAL_HOOK_LLM_TRACE_DIR")
        if _trace_dir:
            try:
                import time as _t

                Path(_trace_dir).mkdir(parents=True, exist_ok=True)
                _ts = f"{_t.time():.6f}"
                Path(_trace_dir, f"{_ts}-drafter-raw.json").write_text(
                    json.dumps({"tool_input": tool_input}, indent=2, default=str)
                )
            except Exception:
                pass  # trace must never break the real call
        tool_input = _sanitize_media_specs(tool_input, uploads=uploads)
        # Upload reconciliation: every pre-seeded upload must appear in
        # the final media_specs. Drafter may modify caption/spec extras
        # but id + path + user_uploaded=True are ground truth — never
        # trust the LLM to invent upload paths.
        if preseeded_specs:
            tool_input = _reconcile_uploads(tool_input, preseeded_specs)
        # Defense-in-depth: auto-repair content tokens against the (already
        # sanitized + reconciled) spec list. Handles two observed LLM drift
        # modes — stripped 'media_' prefix and literal placeholder ids from
        # schema/prompt examples. Runs AFTER spec sanitization so fuzzy
        # matching only considers ids that survived validation.
        content = tool_input.get("content")
        if isinstance(content, str) and tool_input.get("media_specs"):
            tool_input["content"] = _auto_repair_content_tokens(content, tool_input["media_specs"])
        return CreateDraftInput.validate(tool_input)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_media_type(path: str) -> str:
    """Infer an ``image/*`` media type from a path. Defaults to image/png."""
    guess, _ = mimetypes.guess_type(path)
    if guess and guess.startswith("image/"):
        return guess
    return "image/png"


def _read_upload_bytes(path_str: str) -> tuple[bytes, str]:
    """Read an upload, re-encoding BMP/TIFF to PNG via Pillow when needed.

    Returns ``(bytes, media_type)``. Raises ``ValidationError`` from
    errors.py-compatible ``ConfigError`` for oversize files; re-encode
    failures surface as ConfigError too.
    """
    p = Path(path_str)
    if not p.is_file():
        raise ConfigError(f"Upload path does not exist: {path_str}")
    ext = p.suffix.lstrip(".").lower()

    if p.stat().st_size > _UPLOAD_MAX_SIZE:
        raise ConfigError(
            f"Upload {path_str!r} is {p.stat().st_size} bytes; "
            f"limit is {_UPLOAD_MAX_SIZE} bytes ({_UPLOAD_MAX_SIZE // 1048576} MiB)."
        )

    if ext in _UPLOAD_REENCODE_EXTS:
        try:
            from io import BytesIO

            from PIL import Image
        except ImportError as exc:  # pragma: no cover — Pillow is a soft dep
            raise ConfigError(
                f"Upload {path_str!r} is {ext.upper()}; install Pillow "
                f"(pip install pillow) to re-encode BMP/TIFF to PNG."
            ) from exc
        img = Image.open(p).convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    if ext not in _UPLOAD_ALLOWED_EXTS:
        raise ConfigError(
            f"Upload {path_str!r} has unsupported extension {ext!r}; "
            f"allowed: {sorted(_UPLOAD_ALLOWED_EXTS)}."
        )
    return p.read_bytes(), _guess_media_type(path_str)


def _preseed_upload_specs(uploads: list[Any]) -> list[dict[str, Any]]:
    """Build pre-seeded ``user_uploaded=True`` MediaSpecItem dicts from uploads.

    One MediaSpecItem per upload, id generated via ``generate_id("media")``
    (same format the drafter is asked to produce for generated items).
    These pre-seeded entries are shown to the LLM and reconciled post-call
    so uploads never vanish from the final ``media_specs`` list.

    Skips uploads with no path (logged; never raises).
    """
    out: list[dict[str, Any]] = []
    for i, up in enumerate(uploads, 1):
        path = getattr(up, "path", None) or (up.get("path") if isinstance(up, dict) else None)
        if not path:
            logger.warning("Upload %d missing path; skipping pre-seed spec", i)
            continue
        ctx = getattr(up, "context", "") or (up.get("context", "") if isinstance(up, dict) else "")
        out.append(
            {
                "id": generate_id("media"),
                "tool": "legacy_upload",
                "spec": {"path": str(path), "context": str(ctx)},
                "caption": None,
                "user_uploaded": True,
            }
        )
    return out


def _reconcile_uploads(
    tool_input: dict[str, Any], preseeded: list[dict[str, Any]]
) -> dict[str, Any]:
    """Reconcile the drafter's media_specs against the pre-seeded uploads.

    Invariants enforced:

    * Every pre-seeded upload (identified by ``spec.path``) appears in the
      final ``media_specs``. Drops by the LLM are re-injected.
    * For a matched upload, the LLM may set ``caption`` and may append
      extra non-path fields to ``spec``, but ``id``, ``spec.path``,
      ``tool = 'legacy_upload'``, and ``user_uploaded = True`` are ground
      truth — overwritten from the pre-seed.

    The path is the stable identity (id is generated locally; the LLM may
    substitute or omit its own id). Uploads are re-injected at the end of
    the list in their original pre-seed order, preserving any other
    media_specs the drafter emitted in between.
    """
    specs = tool_input.get("media_specs")
    if not isinstance(specs, list):
        specs = []

    # Index pre-seeded by path for fast lookup.
    preseed_by_path: dict[str, dict[str, Any]] = {
        str(p["spec"].get("path", "")): p for p in preseeded
    }
    matched_paths: set[str] = set()

    reconciled: list[dict[str, Any]] = []
    for raw in specs:
        if not isinstance(raw, dict):
            reconciled.append(raw)  # let sanitize/validate reject below
            continue
        if raw.get("user_uploaded") is not True:
            reconciled.append(raw)
            continue
        raw_path = str((raw.get("spec") or {}).get("path", ""))
        preseed = preseed_by_path.get(raw_path)
        if preseed is None:
            # user_uploaded with a path not in preseeded — let sanitize
            # strip it as a hallucination. (Reached only if sanitize
            # ran with uploads=None, but keep the defensive branch.)
            reconciled.append(raw)
            continue
        # Accept LLM modifications to caption and any extra spec keys
        # that aren't "path", but overwrite the ground-truth fields
        # from the pre-seed so id and user_uploaded can never drift.
        merged = dict(raw)
        merged_spec = dict(raw.get("spec") or {})
        merged_spec["path"] = preseed["spec"]["path"]
        # Re-thread the operator's context note from the pre-seed; the
        # LLM has no authoritative source for it.
        if "context" in preseed["spec"]:
            merged_spec.setdefault("context", preseed["spec"]["context"])
        merged["spec"] = merged_spec
        merged["id"] = preseed["id"]
        merged["tool"] = "legacy_upload"
        merged["user_uploaded"] = True
        reconciled.append(merged)
        matched_paths.add(raw_path)

    # Re-inject any pre-seeded uploads the drafter dropped.
    for preseed in preseeded:
        path = str(preseed["spec"].get("path", ""))
        if path and path not in matched_paths:
            logger.warning("Drafter dropped pre-seeded upload %r — re-injecting", path)
            reconciled.append(dict(preseed))

    tool_input["media_specs"] = reconciled
    return tool_input


def _assemble_vision_content(
    user_text: str,
    uploads: list[Any],
    preseeded_specs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Interleave operator context text with base64 image blocks.

    Block order: leading text → (optional JSON-serialized pre-seeded
    media_specs block so the LLM sees each upload's id) → each upload
    (optional per-upload context text, then the image) → the main
    user_text. This puts the reference images in front of the LLM
    before the task description, matching the common Anthropic vision
    prompt pattern.
    """
    blocks: list[dict[str, Any]] = []
    if uploads:
        intro = (
            f"The operator attached {len(uploads)} reference image(s). "
            "Build the post around them. Each image has an optional "
            "context note above it."
        )
        if preseeded_specs:
            intro += (
                "\n\nThese uploads already have stable ids (listed below). "
                "Your `media_specs` output MUST include every one of these "
                "items verbatim (same `id`, `tool`, `spec.path`, "
                "`user_uploaded: true`). Reference each one in `content` "
                "using its `id` via the `![caption](media:<id>)` token "
                "convention — do not fabricate new entries for the "
                "uploaded images.\n\n"
                "Pre-seeded uploads (JSON):\n"
                f"```json\n{json.dumps(preseeded_specs, indent=2)}\n```"
            )
        blocks.append({"type": "text", "text": intro})
        for i, up in enumerate(uploads, 1):
            path = getattr(up, "path", None) or (up.get("path") if isinstance(up, dict) else None)
            ctx = getattr(up, "context", "") or (
                up.get("context", "") if isinstance(up, dict) else ""
            )
            if not path:
                logger.warning("Upload %d missing path; skipping vision block", i)
                continue
            data, media_type = _read_upload_bytes(path)
            if ctx:
                blocks.append({"type": "text", "text": f"Image {i} context: {ctx}"})
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(data).decode("ascii"),
                    },
                }
            )
    blocks.append({"type": "text", "text": user_text})
    return blocks


def _sanitize_media_specs(
    tool_input: dict[str, Any],
    *,
    uploads: list[Any] | None = None,
) -> dict[str, Any]:
    """Strip semantic errors from the drafter's raw tool call.

    Structural errors (tool call absent, Pydantic type errors) stay hard-
    fail. Semantic errors are logged + stripped so a single bad spec does
    not sink the whole draft:

    * duplicate ``id`` across items — keep the last occurrence
    * ``user_uploaded=True`` with no matching operator upload
      (hallucination) — strip item
    * unknown ``tool`` name — strip item
    * missing required fields (``id``, ``tool``, ``spec``) — strip item
    """
    specs = tool_input.get("media_specs")
    if not isinstance(specs, list) or not specs:
        return tool_input

    # Collect paths from uploads for hallucination detection. Both
    # attribute and dict access supported.
    known_upload_paths: set[str] = set()
    if uploads:
        for up in uploads:
            path = getattr(up, "path", None) or (up.get("path") if isinstance(up, dict) else None)
            if path:
                known_upload_paths.add(str(path))

    sanitized: list[dict[str, Any]] = []
    for i, raw in enumerate(specs):
        if not isinstance(raw, dict):
            logger.warning("Media spec %d is not a dict — stripping: %r", i, raw)
            continue
        missing = _REQUIRED_SPEC_FIELDS - set(raw.keys())
        if missing:
            logger.warning(
                "Media spec %d missing required fields %s — stripping: %s", i, sorted(missing), raw
            )
            continue
        tool = raw.get("tool")
        if tool not in _ALLOWED_TOOLS:
            logger.warning("Media spec %d has unknown tool %r — stripping", i, tool)
            continue
        spec_body = raw.get("spec")
        if not isinstance(spec_body, dict):
            logger.warning("Media spec %d has non-dict spec body — stripping: %r", i, spec_body)
            continue
        if raw.get("user_uploaded") is True:
            upload_path = spec_body.get("path")
            if not upload_path or str(upload_path) not in known_upload_paths:
                logger.warning(
                    "Media spec %d claims user_uploaded but path %r is not in uploads — stripping",
                    i,
                    upload_path,
                )
                continue
        sanitized.append(raw)

    # Dedup on id, keeping the last occurrence so a later spec wins (mirrors
    # update semantics). Preserve source order of survivors.
    seen_ids: dict[str, int] = {}
    for idx, spec in enumerate(sanitized):
        seen_ids[spec["id"]] = idx  # last-wins
    deduped: list[dict[str, Any]] = []
    kept_indexes = set(seen_ids.values())
    for idx, spec in enumerate(sanitized):
        if idx in kept_indexes:
            deduped.append(spec)
        else:
            logger.warning(
                "Duplicate media spec id %r at index %d — stripping earlier occurrence",
                spec.get("id"),
                idx,
            )

    tool_input["media_specs"] = deduped
    return tool_input


def _auto_repair_content_tokens(content: str, specs: list[dict[str, Any]]) -> str:
    """Repair `![caption](media:<id>)` tokens against the spec list.

    Three observed LLM drift modes, handled here as defense-in-depth:

    * **Missing ``media_`` prefix** — token id is the 12-hex tail of a
      real spec id; rewrite to the full id. Example:
      ``![x](media:a1b2c3d4e5f6)`` with a spec ``{"id":
      "media_a1b2c3d4e5f6"}`` rewrites to
      ``![x](media:media_a1b2c3d4e5f6)``.
    * **Literal placeholder id** — token id matches one of
      ``_LITERAL_PLACEHOLDER_IDS`` (``id``, ``<id>``, ``media_id``, etc.);
      drop the token entirely so the orphan-reference diagnostic does
      not fire on LLM template copying.
    * **Unrecoverable** — token id fuzzy-matches nothing; leave verbatim
      so the ``broken_media_reference`` diagnostic surfaces it at read
      time.

    Structural token matches that already map 1-to-1 to a spec id pass
    through unchanged.
    """
    if not content:
        return content
    spec_ids: set[str] = {str(s.get("id")) for s in specs if isinstance(s, dict) and s.get("id")}
    if not spec_ids:
        return content

    # Build a tail-to-full-id index for prefix-strip repair. Only tails
    # that are unique across all specs are eligible — ambiguous tails
    # stay as-is so we never silently mis-route.
    tail_index: dict[str, str] = {}
    ambiguous_tails: set[str] = set()
    for full_id in spec_ids:
        if full_id.startswith("media_"):
            tail = full_id[len("media_") :]
            if tail in tail_index:
                ambiguous_tails.add(tail)
            else:
                tail_index[tail] = full_id
    for tail in ambiguous_tails:
        tail_index.pop(tail, None)

    def _repair(match: "Any") -> str:
        caption = match.group(1)
        raw_id = match.group(2)
        # 1. Exact match — no repair needed.
        if raw_id in spec_ids:
            return str(match.group(0))
        # 2. Literal placeholder — drop the whole token.
        if raw_id.lower().strip("<>") in _LITERAL_PLACEHOLDER_IDS:
            logger.warning("Dropping content token with literal placeholder id %r", raw_id)
            return ""
        # 3. Prefix-strip repair — unique tail maps back to a real id.
        if raw_id in tail_index:
            repaired_id = tail_index[raw_id]
            logger.warning(
                "Repaired content token: media:%s -> media:%s (missing 'media_' prefix)",
                raw_id,
                repaired_id,
            )
            return f"![{caption}](media:{repaired_id})"
        # 4. Unrecoverable — diagnostic surfaces it at read time.
        return str(match.group(0))

    return TOKEN_RE.sub(_repair, content)
