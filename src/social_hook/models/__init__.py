"""Domain models for social-hook.

Models are organized in submodules:
  - models.enums      — Enums, status constants, helper predicates
  - models.core       — Project, Decision, Draft, DraftPart, DraftChange, Post, CommitInfo
  - models.narrative   — Lifecycle, Arc, NarrativeDebt
  - models.content     — ContentTopic, ContentSuggestion, EvaluationCycle, DraftPattern
  - models.infra       — OAuthToken, UsageLog, SystemErrorRecord
  - models.context     — ProjectContext

Import directly from the specific submodule:
  from social_hook.models.core import Project, Decision
  from social_hook.models.enums import TERMINAL_STATUSES, PipelineStage
"""
