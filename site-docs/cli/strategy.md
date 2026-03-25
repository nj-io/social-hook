# social-hook strategy

View and customize content strategies (voice, audience, editorial rules).

---

### `social-hook strategy edit`

Edit a strategy's fields in $EDITOR.

Extracts the strategy's editable fields (audience, voice, angle,
post_when, avoid, format_preference, media_preference) into a
temporary YAML file, opens in $EDITOR, then writes changes back
to the project's content-config.yaml.

Example: social-hook strategy edit building-public

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Strategy name to edit |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook strategy list`

List strategies: built-in templates + project overrides.

Shows all content strategies available for the project, including
built-in templates (building-public, product-news, etc.) merged
with any project-level customizations.

Example: social-hook strategy list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook strategy reset`

Reset a strategy to built-in template defaults.

Removes the project-level override for the named strategy,
restoring it to its built-in template values.

Example: social-hook strategy reset building-public --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Strategy name to reset |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook strategy show`

Show full strategy definition (merges template + project override).

Example: social-hook strategy show building-public

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Strategy name |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
