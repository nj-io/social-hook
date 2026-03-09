"""E2E test harness and capture adapter."""

import json as _json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from e2e.constants import PROVIDER_PRESETS


class E2EHarness:
    """Isolated temp environment for E2E tests."""

    def __init__(self, real_base: Path | None = None, provider: str = "claude-cli"):
        if real_base is None:
            # Resolve before we patch HOME
            real_home = os.environ.get("HOME", str(Path.home()))
            real_base = Path(real_home) / ".social-hook"
        self.real_base = real_base
        self.provider = provider
        self.fake_home: Path | None = None
        self.base: Path | None = None  # = fake_home / ".social-hook"
        self.repo_path: Path | None = None
        self.conn = None
        self.project_id: str | None = None
        self._orig_home: str | None = None
        self.project_root = Path(__file__).resolve().parent.parent.parent

    def setup(self, snapshot: str | None = None):
        """Create isolated environment.

        Args:
            snapshot: If provided, load this snapshot instead of creating
                a fresh DB. The snapshot file must exist in the real
                snapshots directory (~/.social-hook/snapshots/{name}.db).
        """
        self.fake_home = Path(tempfile.mkdtemp(prefix="e2e_"))
        self.base = self.fake_home / ".social-hook"
        self.base.mkdir()

        # Copy real credentials
        env_src = self.real_base / ".env"
        if env_src.exists():
            shutil.copy(env_src, self.base / ".env")
        else:
            raise FileNotFoundError(f"No .env found at {env_src}. Configure credentials first.")

        # Copy prompt files
        prompts_src = self.real_base / "prompts"
        if prompts_src.exists():
            shutil.copytree(prompts_src, self.base / "prompts")
        else:
            raise FileNotFoundError(
                f"No prompts/ found at {prompts_src}. Run 'social-hook setup' first."
            )

        # Write deterministic config.yaml for E2E tests
        # (Don't copy user's config — it may have outdated bare model names)
        self._write_global_config()

        # Symlink real ~/.claude/ so Claude CLI subprocess can authenticate
        real_claude_dir = Path(os.environ.get("HOME", str(Path.home()))) / ".claude"
        if real_claude_dir.exists():
            (self.fake_home / ".claude").symlink_to(real_claude_dir)

        # Patch HOME before any imports that use Path.home()
        self._patch_home()

        db_path = self.base / "social-hook.db"

        if snapshot:
            # Load snapshot instead of fresh DB
            self._load_snapshot_db(snapshot, db_path)
        else:
            # Init fresh DB
            from social_hook.db import init_database

            self.conn = init_database(db_path)

        # Clone this repo
        self._clone_repo()

        # Create project config in cloned repo
        self._write_project_config()

        if snapshot:
            # Recover project_id from the loaded DB
            self._recover_project_id()

    def teardown(self):
        """Clean up."""
        if self.conn:
            self.conn.close()
        self._unpatch_home()
        if self.fake_home and self.fake_home.exists():
            shutil.rmtree(self.fake_home, ignore_errors=True)

    def _patch_home(self):
        self._orig_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.fake_home)

    def _unpatch_home(self):
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]

    def _load_snapshot_db(self, name: str, db_path: Path):
        """Load a snapshot DB file into the harness environment."""
        snap_path = self.real_base / "snapshots" / f"{name}.db"
        if not snap_path.exists():
            raise FileNotFoundError(
                f"Snapshot not found: {snap_path}\n"
                f"Available snapshots: {', '.join(f.stem for f in (self.real_base / 'snapshots').glob('*.db') if not f.stem.startswith('_')) if (self.real_base / 'snapshots').exists() else []}"
            )
        shutil.copy2(str(snap_path), str(db_path))
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def _recover_project_id(self):
        """Recover project_id from a loaded snapshot DB.

        The snapshot was saved with repo_path pointing to a previous
        temp clone. We update the project's repo_path to point to the
        current clone, and recover the project_id.
        """
        if not self.conn or not self.repo_path:
            return
        rows = self.conn.execute(
            "SELECT id, repo_path FROM projects WHERE name = 'social-media-auto-hook' LIMIT 1"
        ).fetchall()
        if rows:
            self.project_id = rows[0][0]
            old_path = rows[0][1]
            new_path = str(self.repo_path)
            if old_path != new_path:
                self.conn.execute(
                    "UPDATE projects SET repo_path = ? WHERE id = ?",
                    (new_path, self.project_id),
                )
                self.conn.commit()

    def save_snapshot(self, name: str):
        """Save the current DB state as a named snapshot.

        Saves to the real snapshots directory (~/.social-hook/snapshots/)
        so it persists across E2E runs. Also saves metadata (project_id,
        provider) as a JSON sidecar.
        """
        if not self.conn:
            return
        snap_dir = self.real_base / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        dest = snap_dir / f"{name}.db"

        # Flush WAL to ensure all data is in the main DB file
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        db_path = self.base / "social-hook.db"
        shutil.copy2(str(db_path), str(dest))

        # Save metadata sidecar
        meta = {
            "project_id": self.project_id,
            "provider": self.provider,
        }
        meta_path = snap_dir / f"{name}.json"
        meta_path.write_text(_json.dumps(meta, indent=2))

        print(f"  Snapshot saved: {name} ({dest.stat().st_size / 1024:.1f} KB)")

    def _clone_repo(self):
        """Clone this repo into the temp environment."""
        repos_dir = self.base / "repos"
        repos_dir.mkdir(exist_ok=True)

        self.repo_path = repos_dir / "social-media-auto-hook"
        subprocess.run(
            ["git", "clone", "--quiet", str(self.project_root), str(self.repo_path)],
            check=True,
            capture_output=True,
        )

    def _write_global_config(self):
        """Write deterministic global config.yaml for E2E tests."""
        import yaml

        preset = PROVIDER_PRESETS[self.provider]
        config = {
            "models": {
                "evaluator": preset["evaluator"],
                "drafter": preset["drafter"],
                "gatekeeper": preset["gatekeeper"],
            },
            "platforms": {
                "x": {"enabled": True, "account_tier": "free"},
                "linkedin": {"enabled": False},
            },
            "scheduling": {
                "timezone": "UTC",
                "max_posts_per_day": 5,
                "min_gap_minutes": 30,
                "optimal_days": ["Tue", "Wed", "Thu"],
                "optimal_hours": [9, 12, 17],
            },
            "media_generation": {"enabled": False},
        }
        (self.base / "config.yaml").write_text(yaml.dump(config))

    def _write_project_config(self):
        """Create .social-hook/ in the cloned repo with test config."""
        config_dir = self.repo_path / ".social-hook"
        config_dir.mkdir(exist_ok=True)

        # social-context.md — use the example template
        template = self.project_root / "examples" / "social-context.example.md"
        if template.exists():
            shutil.copy(template, config_dir / "social-context.md")
        else:
            (config_dir / "social-context.md").write_text(
                "# Social Context: social-media-auto-hook\n\n"
                "A system that turns git commits into social media posts.\n"
            )

        # content-config.yaml — test settings
        (config_dir / "content-config.yaml").write_text(
            "account:\n"
            '  tier: "free"\n'
            "\n"
            "models:\n"
            f"  evaluator: {PROVIDER_PRESETS[self.provider]['evaluator']}\n"
            f"  drafter: {PROVIDER_PRESETS[self.provider]['drafter']}\n"
            f"  gatekeeper: {PROVIDER_PRESETS[self.provider]['gatekeeper']}\n"
            "\n"
            "platforms:\n"
            "  x:\n"
            "    enabled: true\n"
            "    priority: 1\n"
            "    constraints:\n"
            "      char_limit: 280\n"
            "    threads:\n"
            "      enabled: true\n"
            "      max_tweets: 10\n"
            '      style: "numbered"\n'
            "    scheduling:\n"
            '      optimal_times: ["09:00", "10:00", "14:00"]\n'
            '      timezone: "UTC"\n'
            '      optimal_days: ["Tuesday", "Wednesday", "Thursday"]\n'
            "\n"
            "  linkedin:\n"
            "    enabled: false\n"
            "\n"
            "posting_rules:\n"
            "  max_per_day: 3\n"
            "  min_gap_minutes: 30\n"
            "  max_per_week: 10\n"
            "  prefer_scheduled: true\n"
            "  batch_window_minutes: 30\n"
            "\n"
            "strategy:\n"
            "  narrative_debt_threshold: 3\n"
            "  portfolio_window: 10\n"
            "  arc_stagnation_days: 14\n"
            "  strategy_moment_max_gap_days: 7\n"
            "\n"
            "context:\n"
            "  recent_decisions: 30\n"
            "  recent_posts: 15\n"
            "  max_tokens: 150000\n"
        )

    def seed_project(self, paused=False):
        """Register the test repo directly in DB. Returns Project."""
        from social_hook.db import (
            insert_lifecycle,
            insert_narrative_debt,
            insert_project,
        )
        from social_hook.filesystem import generate_id
        from social_hook.models import Lifecycle, NarrativeDebt, Project

        origin = subprocess.run(
            ["git", "-C", str(self.repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        repo_origin = origin.stdout.strip() if origin.returncode == 0 else None

        project = Project(
            id=generate_id("project"),
            name="social-media-auto-hook",
            repo_path=str(self.repo_path),
            repo_origin=repo_origin,
            paused=paused,
        )
        insert_project(self.conn, project)

        lifecycle = Lifecycle(
            project_id=project.id,
            phase="research",
            confidence=0.3,
        )
        insert_lifecycle(self.conn, lifecycle)

        debt = NarrativeDebt(
            project_id=project.id,
            debt_counter=0,
        )
        insert_narrative_debt(self.conn, debt)
        self.conn.commit()

        self.project_id = project.id
        return project

    def seed_draft(self, project_id, status="draft", **kwargs):
        """Insert a draft with supporting decision row."""
        from social_hook.db import insert_decision, insert_draft
        from social_hook.filesystem import generate_id
        from social_hook.models import Decision, Draft

        decision = Decision(
            id=generate_id("decision"),
            project_id=project_id,
            commit_hash=f"seed_{generate_id('commit')[:12]}",  # unique per call
            decision="draft",
            reasoning="E2E test decision",
            episode_type="milestone",
            post_category="arc",
        )
        insert_decision(self.conn, decision)

        draft = Draft(
            id=kwargs.pop("id", generate_id("draft")),
            project_id=project_id,
            decision_id=decision.id,
            platform=kwargs.pop("platform", "x"),
            content=kwargs.pop("content", "E2E test draft content for social media."),
            status=status,
            media_paths=kwargs.pop("media_paths", []),
            media_type=kwargs.pop("media_type", None),
            media_spec=kwargs.pop("media_spec", None),
            suggested_time=kwargs.pop("suggested_time", None),
            scheduled_time=kwargs.pop("scheduled_time", None),
            retry_count=kwargs.pop("retry_count", 0),
            last_error=kwargs.pop("last_error", None),
        )
        if kwargs:
            raise TypeError(f"Unexpected seed_draft kwargs: {kwargs}")
        insert_draft(self.conn, draft)
        self.conn.commit()
        return draft

    def update_config(self, overrides: dict):
        """Update the global config.yaml with overrides."""
        import yaml

        config_path = self.base / "config.yaml"
        data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
        for key, value in overrides.items():
            if isinstance(value, dict):
                data.setdefault(key, {}).update(value)
            else:
                data[key] = value
        config_path.write_text(yaml.dump(data))

    def load_config(self):
        """Load config using the patched paths."""
        from social_hook.config import load_full_config

        return load_full_config()

    def clean_scenario_state(self):
        """Delete all decisions, drafts, and arcs for the test project.

        Preserves project registration, lifecycle, and narrative_debt so
        each scenario starts from a 'project registered, nothing evaluated'
        state. Works across connections because it operates on committed data.
        """
        if not self.project_id or not self.conn:
            return
        # Order matters: drafts reference decisions, decisions may reference arcs
        for draft_row in self.conn.execute(
            "SELECT id FROM drafts WHERE project_id = ?", (self.project_id,)
        ).fetchall():
            self.conn.execute("DELETE FROM draft_changes WHERE draft_id = ?", (draft_row[0],))
            self.conn.execute("DELETE FROM draft_tweets WHERE draft_id = ?", (draft_row[0],))
        self.conn.execute("DELETE FROM posts WHERE project_id = ?", (self.project_id,))
        self.conn.execute("DELETE FROM drafts WHERE project_id = ?", (self.project_id,))
        self.conn.execute("DELETE FROM decisions WHERE project_id = ?", (self.project_id,))
        self.conn.execute("DELETE FROM arcs WHERE project_id = ?", (self.project_id,))
        self.conn.execute("DELETE FROM usage_log WHERE project_id = ?", (self.project_id,))
        self.conn.execute(
            "DELETE FROM milestone_summaries WHERE project_id = ?", (self.project_id,)
        )
        self.conn.execute(
            "UPDATE projects SET audience_introduced = 0 WHERE id = ?", (self.project_id,)
        )
        self.conn.commit()


class FakeDB:
    """Wrap conn to auto-provide it to ops functions.

    Only injects conn as the first arg — callers provide
    all other args (including project_id) themselves.
    """

    def __init__(self, conn, project_id):
        self._conn = conn
        self._pid = project_id

    def __getattr__(self, name):
        from social_hook.db import operations as ops

        fn = getattr(ops, name)
        import inspect

        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if params and params[0] == "conn":
            return lambda *a, **kw: fn(self._conn, *a, **kw)
        return fn


class CaptureAdapter:
    """MessagingAdapter that captures all outbound messages for test assertions.

    Implements the MessagingAdapter interface without inheriting from it
    to avoid import-time issues with the ABC (tests import this before
    social_hook packages are on sys.path).
    """

    platform = "test"

    def __init__(self):
        self.messages: list[dict] = []

    def send_message(self, chat_id, message):
        from social_hook.messaging.base import SendResult

        self.messages.append(
            {
                "type": "buttons" if message.buttons else "text",
                "chat_id": chat_id,
                "text": message.text,
                "buttons": [
                    [
                        {"label": b.label, "action": b.action, "payload": b.payload}
                        for b in row.buttons
                    ]
                    for row in message.buttons
                ]
                if message.buttons
                else None,
            }
        )
        return SendResult(success=True, message_id=str(len(self.messages)))

    def edit_message(self, chat_id, message_id, message):
        from social_hook.messaging.base import SendResult

        self.messages.append({"type": "edit", "chat_id": chat_id, "text": message.text})
        return SendResult(success=True, message_id=message_id)

    def answer_callback(self, callback_id, text=""):
        return True

    def send_media(self, chat_id, file_path, caption="", parse_mode="markdown"):
        from social_hook.messaging.base import SendResult

        self.messages.append(
            {
                "type": "media",
                "chat_id": chat_id,
                "file_path": file_path,
                "caption": caption,
            }
        )
        return SendResult(success=True, message_id=str(len(self.messages)))

    def get_capabilities(self):
        from social_hook.messaging.base import PlatformCapabilities

        return PlatformCapabilities(
            max_message_length=100000,
            supports_buttons=True,
            supports_media=True,
            max_buttons_per_row=10,
        )

    def clear(self):
        self.messages.clear()

    def last_message_contains(self, text: str) -> bool:
        return any(text.lower() in m.get("text", "").lower() for m in self.messages)

    def last_message(self) -> dict | None:
        return self.messages[-1] if self.messages else None
