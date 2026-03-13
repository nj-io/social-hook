# social-hook config

View and modify configuration.

---

### `social-hook config get`

Get a single configuration value by dotted key path.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `key` | yes | Dotted key path (e.g. platforms.x.account_tier) |

---

### `social-hook config set`

Set a configuration value by dotted key path.

Only scalar values (strings, numbers, booleans) are supported.
For lists/arrays, edit the YAML directly or use the web UI.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `key` | yes | Dotted key path (e.g. platforms.x.account_tier) |
| `value` | yes | Value to set (scalars only; use web UI for lists/arrays) |

---

### `social-hook config show`

Show the full configuration as YAML.

---
