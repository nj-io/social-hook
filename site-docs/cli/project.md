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

---

### `social-hook project install-hook`

Install git post-commit hook for a project.

Example: social-hook project install-hook /path/to/repo

---

### `social-hook project intro`

Manage per-platform introduction status.

---

### `social-hook project list`

List all registered projects.

---

### `social-hook project pause`

Pause a project (skip commit evaluation).

---

### `social-hook project prompt-docs`

Manage project prompt documentation files.

---

### `social-hook project register`

Register a project for social-hook.

Supports both git repos and plain directories. For non-git projects,
provide --docs to seed project context.

Example: social-hook project register /path/to/project --docs README.md --docs guide.md

---

### `social-hook project set-branch`

Set which branch triggers the pipeline for a project.

---

### `social-hook project uninstall-hook`

Remove git post-commit hook from a project.

Example: social-hook project uninstall-hook /path/to/repo

---

### `social-hook project unpause`

Unpause a project (resume commit evaluation).

---

### `social-hook project unregister`

Unregister a project.

---
