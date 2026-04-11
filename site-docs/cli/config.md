# social-hook config

View and modify configuration.

---

### `social-hook config get`

Get a single configuration value by dotted key path.

Traverses the YAML config tree using dot-separated keys.
Returns scalars directly or nested structures as YAML.

Example: social-hook config get context.max_discovery_tokens
Example: social-hook config get platforms.x.account_tier

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `key` | yes | Dotted key path (e.g. context.max_discovery_tokens) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--content` | boolean | false | Read from content-config.yaml. Example: social-hook config get context.max_discovery_tokens --content |
| `--project`, `-p` | string |  | Project path |

---

### `social-hook config set`

Set a configuration value by dotted key path.

Only scalar values (strings, numbers, booleans) are supported.
For lists/arrays, edit the YAML directly or use the web UI.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `key` | yes | Dotted key path (e.g. context.max_discovery_tokens) |
| `value` | yes | Value to set (scalars only) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--content` | boolean | false | Write to content-config.yaml. Example: social-hook config set context.max_discovery_tokens 80000 --content |
| `--project`, `-p` | string |  | Project path |

---

### `social-hook config show`

Show the full configuration as YAML.

Prints the merged config.yaml contents. Use --content to show
content-config.yaml instead (social context, voice, post
categories).

Example: social-hook config show
Example: social-hook config show --content

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--content` | boolean | false | Show content-config.yaml instead of config.yaml. Example: social-hook config show --content |
| `--project`, `-p` | string |  | Project path for project-specific config |

---
