# social-hook strategy

View and customize content strategies (voice, audience, editorial rules).

---

### `social-hook strategy add`

Create a new custom content strategy.

Creates a strategy in the project's config. Optionally base it on a
built-in template to inherit defaults, then override specific fields.

Example: social-hook strategy add --name dev-community --audience "open-source developers" --voice casual

---

### `social-hook strategy delete`

Delete a custom strategy from the project config.

Fails if any targets reference the strategy (409 Conflict).
Built-in template strategies cannot be deleted — use 'reset' instead.

Example: social-hook strategy delete dev-community --yes

---

### `social-hook strategy edit`

Edit a strategy's fields in $EDITOR.

Extracts the strategy's editable fields (audience, voice, angle,
post_when, avoid, format_preference, media_preference) into a
temporary YAML file, opens in $EDITOR, then writes changes back
to the project's content-config.yaml.

Example: social-hook strategy edit building-public

---

### `social-hook strategy list`

List strategies: built-in templates + project overrides.

Shows all content strategies available for the project, including
built-in templates (building-public, product-news, etc.) merged
with any project-level customizations.

Example: social-hook strategy list

---

### `social-hook strategy reset`

Reset a strategy to built-in template defaults.

Removes the project-level override for the named strategy,
restoring it to its built-in template values.

Example: social-hook strategy reset building-public --yes

---

### `social-hook strategy show`

Show full strategy definition (merges template + project override).

Displays the strategy's label, description, type (built-in or custom),
and fields: audience, voice, angle, post_when, avoid, format_preference,
and media_preference.

Example: social-hook strategy show building-public

---
