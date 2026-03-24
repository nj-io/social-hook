# social-hook account

Platform account management.

---

### `social-hook account add`

Add a platform account via PKCE OAuth flow.

Initiates an OAuth 2.0 PKCE flow: opens a browser for authorization,
runs a local callback server, exchanges the code for tokens, and
stores them in the database.

Example: social-hook account add --platform x --name lead

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--platform` | string |  | Platform (x, linkedin) |
| `--name`, `-n` | string |  | Account name (e.g. 'lead', 'product') |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook account list`

List accounts with platform, tier, and identity.

Shows all configured platform accounts and their OAuth token status.

Example: social-hook account list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook account remove`

Remove an account.

Removes OAuth tokens for the specified account.
Fails if targets reference this account.

Example: social-hook account remove lead --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Account name to remove |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook account validate`

Validate all account credentials.

Checks that OAuth tokens are present and not expired.

Example: social-hook account validate

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---
