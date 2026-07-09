# social-hook account

Manage OAuth-authenticated platform accounts (X, LinkedIn).

---

### `social-hook account add`

Add a platform account via PKCE OAuth flow.

Initiates an OAuth 2.0 PKCE flow: opens a browser for authorization,
runs a local callback server, exchanges the code for tokens, and
stores them in the database.

Example: social-hook account add --platform x --name lead

---

### `social-hook account list`

List accounts with platform, tier, and identity.

Shows all configured platform accounts and their OAuth token status.

Example: social-hook account list

---

### `social-hook account remove`

Remove an account.

Removes OAuth tokens for the specified account.
Fails if targets reference this account.

Example: social-hook account remove lead --yes

---

### `social-hook account validate`

Validate all account credentials.

Checks that OAuth tokens are present and not expired.

Example: social-hook account validate

---
