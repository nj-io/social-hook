"""Section J: CLI Commands scenarios."""

import os
import subprocess


def run(harness, runner):
    """J1-J8: CLI command scenarios."""
    from typer.testing import CliRunner

    from social_hook.cli import app

    cli = CliRunner()

    if not harness.project_id:
        harness.seed_project()

    # J1: Version
    def j1():
        result = cli.invoke(app, ["version"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}"
        return result.output.strip()

    runner.run_scenario("J1", "Version", j1)

    # J2: Inspect log
    def j2():
        result = cli.invoke(app, ["inspect", "log"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J2", "Inspect log", j2)

    # J3: Inspect pending
    def j3():
        result = cli.invoke(app, ["inspect", "pending"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J3", "Inspect pending", j3)

    # J4: Inspect usage
    def j4():
        result = cli.invoke(app, ["inspect", "usage"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J4", "Inspect usage", j4)

    # J5: Test command
    def j5():
        result = cli.invoke(app, ["test", "test", "--repo", str(harness.repo_path), "--last", "1"])
        # May succeed or fail depending on state — just check it runs
        return f"Exit code: {result.exit_code}"

    runner.run_scenario("J5", "Test command", j5)

    # J6: Unregister project (use a throwaway project)
    def j6():
        # Register a throwaway
        throwaway = harness.base / "repos" / "throwaway"
        throwaway.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(throwaway)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(throwaway), "commit", "--allow-empty", "-m", "init"],
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )

        reg_result = cli.invoke(app, ["project", "register", str(throwaway)])
        if reg_result.exit_code != 0:
            return f"SKIP: Could not register throwaway: {reg_result.output}"

        # Extract ID
        throwaway_id = None
        for line in reg_result.output.splitlines():
            if "ID:" in line:
                throwaway_id = line.split("ID:")[-1].strip()
                break
        if not throwaway_id:
            return "SKIP: Could not extract throwaway ID"

        result = cli.invoke(app, ["project", "unregister", throwaway_id, "--force"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        from social_hook.db import operations as ops

        project = ops.get_project(harness.conn, throwaway_id)
        assert project is None, "Project still exists after unregister"
        return "Project unregistered"

    runner.run_scenario("J6", "Unregister project", j6)

    # J7: Draft media-remove CLI command
    def j7():
        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_paths=["/tmp/j7_media.png"],
            media_type="mermaid",
        )

        result = cli.invoke(app, ["draft", "media-remove", draft.id])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        from social_hook.db import operations as ops

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [], f"Expected empty media_paths, got {updated.media_paths}"
        return "Media removed via CLI"

    runner.run_scenario("J7", "Draft media-remove CLI", j7)

    # J8: Draft show displays media URL
    def j8():
        from social_hook.filesystem import get_base_path

        # Create a real file so the path is valid
        media_dir = get_base_path() / "media-cache" / "j8_test"
        media_dir.mkdir(parents=True, exist_ok=True)
        media_file = media_dir / "test.png"
        media_file.write_bytes(b"fake png data")

        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_paths=[str(media_file)],
            media_type="mermaid",
        )

        result = cli.invoke(app, ["draft", "show", draft.id])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "View:" in result.output, "Expected 'View:' URL in output"
        assert "localhost" in result.output, "Expected localhost URL in output"
        return "Draft show includes media URL"

    runner.run_scenario("J8", "Draft show displays media URL", j8)
