# social-hook project

Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained.

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

---

### `social-hook project pause`

Pause a project (skip commit evaluation).

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (default: detect from current directory) |

---

### `social-hook project prompt-docs`

Manage project prompt documentation files.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project ID or path |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook project register`

Register a project for social-hook.

Supports both git repos and plain directories. For non-git projects,
provide --docs to seed project context.

Example: social-hook project register /path/to/project --docs README.md --docs guide.md

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `path` | no | Path to repository or directory (default: current directory) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--name`, `-n` | string |  | Project name |
| `--git-hook`, `--no-git-hook` | boolean | true | Install git post-commit hook |
| `--docs`, `-d` | string |  | Documentation files to add as project context |

---

### `social-hook project set-branch`

Set which branch triggers the pipeline for a project.

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

Example: social-hook project uninstall-hook /path/to/repo

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

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (default: detect from current directory) |

---

### `social-hook project unregister`

Unregister a project.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | yes | Project ID to unregister |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force`, `-f` | boolean | false | Skip confirmation |

---
