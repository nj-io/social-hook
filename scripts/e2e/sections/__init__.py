"""Section registry for E2E test suite."""

SECTION_REGISTRY = {
    "A": {"name": "Project Onboarding", "module": "onboarding", "needs_adapter": False},
    "B": {"name": "Pipeline Scenarios", "module": "pipeline", "needs_adapter": False},
    "C": {"name": "Narrative Mechanics", "module": "narrative", "needs_adapter": False},
    "D": {"name": "Draft Lifecycle", "module": "draft_lifecycle", "needs_adapter": True},
    "E": {"name": "Scheduler", "module": "scheduler", "needs_adapter": False},
    "F": {"name": "Bot Commands", "module": "bot_commands", "needs_adapter": True},
    "G": {"name": "Bot Buttons", "module": "bot_buttons", "needs_adapter": True},
    "H": {"name": "Gatekeeper", "module": "gatekeeper", "needs_adapter": True},
    "I": {"name": "Setup Validation", "module": "setup_validation", "needs_adapter": False},
    "J": {"name": "CLI Commands", "module": "cli", "needs_adapter": False},
    "K": {"name": "Cross-Cutting", "module": "crosscutting", "needs_adapter": True},
    "L": {"name": "Multi-Provider", "module": "multi_provider", "needs_adapter": False},
    "M": {"name": "Development Journey", "module": "journey", "needs_adapter": False},
    "N": {
        "name": "Web Dashboard + Per-Platform",
        "module": "web_dashboard",
        "needs_adapter": False,
    },
    "Q": {"name": "Queue / Evaluator Rework", "module": "queue", "needs_adapter": False},
    "R": {"name": "Git Hooks & Web Registration", "module": "git_hooks", "needs_adapter": False},
}
