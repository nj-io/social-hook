# Security Policy

## Supported Versions

Social Hook is currently in alpha. Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |
| Older   | No        |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, use [GitHub Security Advisories](https://github.com/nj-io/social-hook/security/advisories/new) to report vulnerabilities privately. You can also email security reports to `26359601+nj-io@users.noreply.github.com`.

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge reports as soon as possible and work with you to understand the issue and coordinate disclosure.

## Security Considerations

### Credential Storage

Social Hook stores API keys and tokens (Anthropic, X/Twitter, LinkedIn, Telegram, etc.) in `~/.social-hook/.env`. This file is created with `0600` permissions (owner read/write only). Never commit this file to version control.

### Web Dashboard

The web dashboard binds to `127.0.0.1` (localhost) by default and has **no authentication**. This is safe for local use but has important implications:

- **Do not use `--host 0.0.0.0`** unless you understand the risks. This exposes the dashboard to your network with no authentication, allowing anyone on the network to read/modify your API keys, trigger LLM calls, and post to your social media accounts.
- CORS is restricted to localhost origins.
- WebSocket connections reject non-localhost origins.

### What We Consider In-Scope

- Credential exposure or leakage
- Unintended network exposure of the web dashboard
- Command injection via CLI inputs
- Path traversal in file-serving endpoints
- Unauthorized access to the `.env` or configuration files through the API

### What We Consider Out-of-Scope

- Vulnerabilities in upstream dependencies (report these to the relevant project)
- Issues that require physical access to the machine running Social Hook
- The intentional lack of authentication on the localhost-only web dashboard
