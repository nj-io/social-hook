-- OAuth 2.0 token storage for per-account user tokens.
-- App credentials (client_id, client_secret) stay in .env.
-- User tokens (access_token, refresh_token) are dynamic and stored here.
CREATE TABLE IF NOT EXISTS oauth_tokens (
    account_name TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
