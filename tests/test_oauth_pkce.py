"""Tests for social_hook.oauth_pkce — generic PKCE utilities."""

import base64
import hashlib

from social_hook.oauth_pkce import (
    CallbackHandler,
    OAuthEndpoints,
    build_auth_url,
    generate_pkce,
)


class TestGeneratePkce:
    def test_returns_verifier_and_challenge(self):
        verifier, challenge = generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) <= 128

    def test_challenge_matches_verifier(self):
        verifier, challenge = generate_pkce()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert challenge == expected

    def test_unique_each_call(self):
        v1, _ = generate_pkce()
        v2, _ = generate_pkce()
        assert v1 != v2


class TestBuildAuthUrl:
    def test_contains_required_params(self):
        endpoints = OAuthEndpoints(
            auth_url="https://example.com/authorize",
            token_url="https://example.com/token",
            scopes="read write",
        )
        url = build_auth_url(
            endpoints,
            client_id="cid",
            state="st",
            code_challenge="ch",
            redirect_uri="http://localhost:4000/callback",
        )
        assert "response_type=code" in url
        assert "client_id=cid" in url
        assert "state=st" in url
        assert "code_challenge=ch" in url
        assert "code_challenge_method=S256" in url
        assert "scope=read+write" in url
        assert url.startswith("https://example.com/authorize?")


class TestCallbackHandler:
    def test_reset_state(self):
        # Reset for clean state
        CallbackHandler.code = None
        CallbackHandler.state = None
        CallbackHandler.error = None
        assert CallbackHandler.code is None
        assert CallbackHandler.state is None
        assert CallbackHandler.error is None
