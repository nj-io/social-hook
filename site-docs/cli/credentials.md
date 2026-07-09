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

---

### `social-hook credentials list`

List platform credential entries.

Shows configured platform credentials (X, LinkedIn, etc.) and their status.

Example: social-hook credentials list

---

### `social-hook credentials remove`

Remove a platform credential entry.

Removes API keys for the specified platform from the .env file.
Fails if accounts reference this credential.

Example: social-hook credentials remove x --yes

---

### `social-hook credentials validate`

Validate all platform credential entries.

Checks that required API keys are present and non-empty.

Example: social-hook credentials validate

---
