# social-hook project

Register repos, import commits, install hooks, and control project lifecycle.

---

### `social-hook project evaluate-recent`

Evaluate recent un-evaluated commits through the full pipeline.

Finds commits with 'imported' or 'deferred_eval' decisions and runs each
through the evaluator + drafter pipeline. Makes LLM calls. Writes decisions
and drafts to the database. Max 5 commits per invocation.

Examples:
    social-hook project evaluate-recent
    social-hook project evaluate-recent --last 3
    social-hook project evaluate-recent -p /path/to/repo --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--last`, `-n` | integer | 5 | Number of recent un-evaluated commits to evaluate (max 5) |
| `--project`, `-p` | string |  | Repository path (default: current directory) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project import-commits`

Import historical git commits as imported decisions.

Imports past commits so the dashboard shows the project timeline.
Imported commits are NOT evaluated — use retrigger to evaluate them later.

Examples:
    social-hook project import-commits
    social-hook project import-commits --branch main
    social-hook project import-commits --limit 50
    social-hook project import-commits --branch main --limit 100

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--branch`, `-b` | string |  | Import only this branch |
| `--limit`, `-n` | integer |  | Import only the N most recent commits |
| `--id`, `-i` | string |  | Project ID |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project install-hook`

Install git post-commit hook for a project.

The hook runs 'social-hook git-hook' after each commit, which
triggers the evaluation pipeline automatically. Safe to re-run
if the hook is already installed.

Example: social-hook project install-hook
Example: social-hook project install-hook /path/to/repo

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `path` | no | Path to repository (default: current directory) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project intro`

Manage per-platform introduction status.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project ID or path |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project list`

List all registered projects.

Shows project ID (truncated), name, status (active/paused),
branch filter, and repository path for each registered project.

Example: social-hook project list

---

### `social-hook project pause`

Pause a project (skip commit evaluation).

While paused, commits are still recorded by the git hook but
not evaluated by the LLM pipeline. Auto-detects the project
from the current directory if no ID is given.

Example: social-hook project pause

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (default: detect from current directory) |

---

### `social-hook project register`

Register a project for social-hook.

Creates a database entry for the repository and optionally installs
a git post-commit hook that triggers evaluation on each commit.
Use --no-git-hook to skip hook installation. The project name
defaults to the repository directory name.

Example: social-hook project register
Example: social-hook project register /path/to/repo --name "my-project"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `path` | no | Path to repository (default: current directory) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--name`, `-n` | string |  | Project name |
| `--git-hook`, `--no-git-hook` | boolean | true | Install git post-commit hook |

---

### `social-hook project set-branch`

Set which branch triggers the pipeline for a project.

When a branch filter is set, only commits on that branch are
evaluated. Use --all to clear the filter and evaluate all
branches. Auto-detects the project from the current directory.

Example: social-hook project set-branch main
Example: social-hook project set-branch --all

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `branch` | no | Branch name to filter on |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--id`, `-i` | string |  | Project ID |
| `--all` | boolean | false | Clear filter (trigger on all branches) |

---

### `social-hook project uninstall-hook`

Remove git post-commit hook from a project.

Deletes the social-hook post-commit hook script from the
repository's .git/hooks/ directory. Requires confirmation
unless --force is passed.

Example: social-hook project uninstall-hook
Example: social-hook project uninstall-hook /path/to/repo --force

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `path` | no | Path to repository (default: current directory) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force`, `-f` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project unpause`

Unpause a project (resume commit evaluation).

Resumes LLM evaluation for new commits. Already-paused commits
are not retroactively evaluated; use 'project evaluate-recent'
to process missed commits.

Example: social-hook project unpause

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (default: detect from current directory) |

---

### `social-hook project unregister`

Unregister a project.

Deletes the project and all its data (decisions, drafts, arcs,
memories) from the database. Also removes the git post-commit
hook. Requires confirmation unless --force is passed.

Example: social-hook project unregister proj_abc123
Example: social-hook project unregister proj_abc123 --force

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | yes | Project ID to unregister |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force`, `-f` | boolean | false | Skip confirmation |

---
