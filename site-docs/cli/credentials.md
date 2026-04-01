# social-hook credentials

Manage API keys and secrets in ~/.social-hook/.env.

---

### `social-hook credentials add`

Add or update a platform credential entry.

Prompts for the required API keys for the specified platform.
Static app credentials are stored in the .env file.
Use --set to bypass prompts for agent/CI use.

Example: social-hook credentials add --platform x --name x-main
Example: social-hook credentials add --platform x --set X_CLIENT_ID=abc --set X_CLIENT_SECRET=xyz

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--platform` | string |  | Platform name (x, linkedin, telegram) |
| `--name`, `-n` | string |  | Credential entry name (default: platform name) |
| `--set` | string | [] | Set a key non-interactively (KEY=VALUE). Repeat for multiple keys. |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook credentials list`

List platform credential entries.

Shows configured platform credentials (X, LinkedIn, etc.) and their status.

Example: social-hook credentials list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook credentials remove`

Remove a platform credential entry.

Removes API keys for the specified platform from the .env file.
Fails if accounts reference this credential.

Example: social-hook credentials remove x --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Credential entry name (platform name) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook credentials validate`

Validate all platform credential entries.

Checks that required API keys are present and non-empty.

Example: social-hook credentials validate

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---
