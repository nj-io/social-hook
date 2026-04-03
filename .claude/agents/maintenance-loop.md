---
name: maintenance-loop
description: Generic maintenance loop agent. Diffs a branch from last run, performs autonomous work, flags new work for approval, creates PRs. Reads config from a YAML file in .claude/loops/.
model: opus
color: green
---

## Usage

```bash
# Local — full gh access, creates PRs automatically
claude --agent maintenance-loop --prompt "Run .claude/loops/docs-maintenance.yml"

# Remote — scheduled via RemoteTrigger or claude schedule
# Prompt: "Read .claude/agents/maintenance-loop.md for your process. Config is at .claude/loops/docs-maintenance.yml. Run the loop."
```

## Config format

The loop reads a YAML config file from `.claude/loops/`. Required fields:

```yaml
loop_name: docs-maintenance          # Branch names, commit messages, PR titles
branch: develop                       # Branch to monitor
state_file: site-docs/DOC_STATUS.md  # Path to state file
checks:                               # Commands to run before committing
  - "ruff check src/ tests/"
setup:                                # Commands to run before starting work
  - "pip install -e '.[dev]'"
autonomous:                           # Work to do without asking
  - Update existing docs to match code changes
approval_required:                    # Work that needs PR comment approval first
  - New doc pages
```

---

## Process

### Step 1: Setup

Always start from the latest target branch:

```bash
git fetch origin <branch>
git checkout <branch>
git pull origin <branch>
```

All maintenance branches are created from the target branch (step 8), never from a worktree's working branch.

Run any `setup` commands from config. Then detect environment:

```bash
if gh auth status &>/dev/null 2>&1; then
  GH_AVAILABLE=true
else
  GH_AVAILABLE=false
fi
```

### Step 2: Read state

Read the state file. Extract `last_run_commit` from the HTML comment at the top:

```
<!-- last_run_commit: <sha> -->
<!-- last_run_date: <date> -->
```

If the state file doesn't exist, create it with current HEAD as starting point and stop. First run is just initialization.

### Step 3: Diff

```bash
git log --oneline <last_run_commit>..HEAD
```

If no changes, stop. No work needed.

### Step 4: Check for feedback

If `GH_AVAILABLE=true`, check merged PRs for approval comments:

```bash
gh pr list --state merged --search "<loop_name>" --limit 5 --json number,title,comments
```

Look for comments that approve backlog items (e.g. "yes to web dashboard guide"). Mark those items as approved in the state file so step 5 can act on them.

If `GH_AVAILABLE=false`, skip this step. The user can mark approvals directly in the state file backlog by changing `- [ ]` to `- [x]`.

### Step 5: Do work

For each change in the diff:
- If it falls under `autonomous` rules — do it
- If it needs new content — check if previously approved (from step 4 or state file)
  - If approved — do it
  - If not — add to "Backlog" in the PR

### Step 6: Run checks

Run each command in `checks`. If any fail, fix the issue before committing.

### Step 7: Update state file

- Set `last_run_commit` to current HEAD
- Set `last_run_date` to today
- Update any status tables
- Mark completed backlog items

### Step 8: Commit and PR

Create a branch and commit:

```bash
git checkout -b <loop_name>/maintenance-<YYYY-MM-DD>
git add <changed files>
git commit -m "chore(<loop_name>): maintenance run — <summary>"
```

If an open PR from this loop already exists (search by branch prefix `<loop_name>/maintenance-`), push to that branch instead of creating a new PR.

If `GH_AVAILABLE=true`:

```bash
gh pr create --base <branch> --title "chore(<loop_name>): maintenance run <date>" --body "<body>"
```

If `GH_AVAILABLE=false`, push the branch and log:

```
Branch <loop_name>/maintenance-<date> pushed. PR creation skipped (gh not available).
Create manually: gh pr create --base <branch> --head <loop_name>/maintenance-<date>
```

### PR body format

```markdown
## Summary
- <bullet per change made>

## Backlog
- [ ] <item> — <what it is and why it needs approval>

## State
- last_run_commit: <old sha> → <new sha>
- Changes since last run: <N> commits
```

---

## State file format

Every loop uses this standard format. The loop reads and writes it.

```markdown
<!-- last_run_commit: <sha> -->
<!-- last_run_date: <YYYY-MM-DD> -->
<!-- loop_name: <name> -->

# Loop Status: <name>

## Work Items
| Item | Status | Last updated | Notes |
|------|--------|--------------|-------|

## Backlog (waiting_approval)
- [ ] Item needing approval
- [x] Approved item (will be actioned next run)
```

---

## Rules

- Never force-push
- Never push to the target branch directly — always use a PR branch
- One PR per run — don't create multiple
- If the state file is missing, create it and stop (initialization run)
- Read project conventions (CLAUDE.md, CODING_PRACTICES.md) if they exist
- Read memory files if running locally for additional context
