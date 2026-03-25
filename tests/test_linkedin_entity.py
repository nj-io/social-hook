"""Tests for LinkedIn entity model — personal vs organization posting.

Tests LinkedInAdapter entity parameter, org admin validation,
factory pass-through, and auth URL scope.
"""

from unittest.mock import MagicMock, patch

from social_hook.adapters.platform.linkedin import LinkedInAdapter

# =============================================================================
# Helpers
# =============================================================================


def _li_userinfo_response(sub, name):
    """Create a mock LinkedIn /v2/userinfo success response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"sub": sub, "name": name}
    return resp


def _li_post_success_response(post_id):
    """Create a mock LinkedIn /rest/posts success response."""
    resp = MagicMock()
    resp.status_code = 201
    resp.headers = {"x-restli-id": post_id}
    resp.json.return_value = {}
    return resp


def _li_org_acls_response(org_urns):
    """Create a mock org ACLs response listing orgs the user admins."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"elements": [{"organizationalTarget": urn} for urn in org_urns]}
    return resp


def _li_error_response(status_code, message):
    """Create a mock LinkedIn error response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"message": message}
    resp.text = message
    return resp


# =============================================================================
# Entity parameter defaults
# =============================================================================


class TestLinkedInEntityDefaults:
    """Entity parameter initialization."""

    def test_default_entity_is_personal(self):
        """Default entity (None) resolves to 'personal'."""
        adapter = LinkedInAdapter("token")
        assert adapter.entity == "personal"

    def test_explicit_personal(self):
        """entity='personal' is accepted."""
        adapter = LinkedInAdapter("token", entity="personal")
        assert adapter.entity == "personal"

    def test_org_urn_entity(self):
        """entity set to an org URN is stored as-is."""
        adapter = LinkedInAdapter("token", entity="urn:li:organization:12345")
        assert adapter.entity == "urn:li:organization:12345"


# =============================================================================
# Validate with personal entity
# =============================================================================


class TestLinkedInValidatePersonal:
    """validate() with personal entity."""

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_validate_personal_returns_personal_prefix(self, mock_get):
        """Personal entity validation returns 'Personal: <name>'."""
        mock_get.return_value = _li_userinfo_response("abc123", "Neil")

        adapter = LinkedInAdapter("token", entity="personal")
        success, info = adapter.validate()

        assert success is True
        assert info == "Personal: Neil"
        assert adapter.author_urn == "urn:li:person:abc123"


# =============================================================================
# Validate with org entity
# =============================================================================


class TestLinkedInValidateOrg:
    """validate() with org entity."""

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_validate_org_checks_admin_access(self, mock_get):
        """Org entity validation checks admin access via ACLs endpoint."""
        org_urn = "urn:li:organization:12345"
        # First call: userinfo; second call: org ACLs
        mock_get.side_effect = [
            _li_userinfo_response("abc123", "Acme Corp"),
            _li_org_acls_response([org_urn]),
        ]

        adapter = LinkedInAdapter("token", entity=org_urn)
        success, info = adapter.validate()

        assert success is True
        assert info == "Org: Acme Corp"
        assert adapter.author_urn == org_urn
        assert adapter._org_validated is True

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_validate_org_no_admin_access(self, mock_get):
        """Org entity without admin access returns (False, error)."""
        org_urn = "urn:li:organization:12345"
        # User is admin of a different org
        mock_get.side_effect = [
            _li_userinfo_response("abc123", "Acme Corp"),
            _li_org_acls_response(["urn:li:organization:99999"]),
        ]

        adapter = LinkedInAdapter("token", entity=org_urn)
        success, info = adapter.validate()

        assert success is False
        assert "Not an admin" in info
        assert adapter._org_validated is False

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_validate_org_empty_acls(self, mock_get):
        """Org entity with empty ACLs returns (False, error)."""
        org_urn = "urn:li:organization:12345"
        mock_get.side_effect = [
            _li_userinfo_response("abc123", "Acme Corp"),
            _li_org_acls_response([]),
        ]

        adapter = LinkedInAdapter("token", entity=org_urn)
        success, info = adapter.validate()

        assert success is False
        assert "Not an admin" in info

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_validate_org_acl_api_failure(self, mock_get):
        """Org entity with ACL API failure returns (False, error)."""
        org_urn = "urn:li:organization:12345"
        mock_get.side_effect = [
            _li_userinfo_response("abc123", "Acme Corp"),
            _li_error_response(403, "Insufficient permissions"),
        ]

        adapter = LinkedInAdapter("token", entity=org_urn)
        success, info = adapter.validate()

        assert success is False
        assert "Org admin check failed" in info


# =============================================================================
# Post with org entity
# =============================================================================


class TestLinkedInPostOrg:
    """post() with org entity uses org URN as author."""

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    def test_post_org_uses_org_urn_as_author(self, mock_post):
        """Post with org entity sets author to org URN in API payload."""
        org_urn = "urn:li:organization:12345"
        mock_post.return_value = _li_post_success_response("urn:li:share:777")

        adapter = LinkedInAdapter("token", entity=org_urn)
        result = adapter.post("Hello from the company!")

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert body["author"] == org_urn

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    def test_post_org_caches_author_urn(self, mock_post):
        """Org entity author URN is set on first post and cached."""
        org_urn = "urn:li:organization:12345"
        mock_post.return_value = _li_post_success_response("urn:li:share:777")

        adapter = LinkedInAdapter("token", entity=org_urn)
        assert adapter.author_urn is None

        adapter.post("First post")
        assert adapter.author_urn == org_urn

        adapter.post("Second post")
        # No GET calls needed — org URN is used directly
        assert mock_post.call_count == 2

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_post_personal_calls_validate(self, mock_get, mock_post):
        """Personal entity post() calls validate() to resolve person URN."""
        mock_get.return_value = _li_userinfo_response("abc123", "Neil")
        mock_post.return_value = _li_post_success_response("urn:li:share:888")

        adapter = LinkedInAdapter("token", entity="personal")
        adapter.post("Hello!")

        mock_get.assert_called_once()  # validate was called
        body = mock_post.call_args.kwargs["json"]
        assert body["author"] == "urn:li:person:abc123"


# =============================================================================
# Auth URL scope for org entity
# =============================================================================


class TestLinkedInAuthUrlScope:
    """get_auth_url() adds w_organization_social for org entity."""

    def test_personal_entity_default_scope(self):
        """Personal entity uses default scope without org permission."""
        url = LinkedInAdapter.get_auth_url(
            client_id="client",
            redirect_uri="https://example.com/cb",
            state="s",
        )
        assert "w_organization_social" not in url
        assert "w_member_social" in url

    def test_org_entity_adds_org_scope(self):
        """Org entity adds w_organization_social to scope."""
        url = LinkedInAdapter.get_auth_url(
            client_id="client",
            redirect_uri="https://example.com/cb",
            state="s",
            entity="urn:li:organization:12345",
        )
        assert "w_organization_social" in url
        assert "w_member_social" in url

    def test_org_entity_no_duplicate_scope(self):
        """If scope already includes w_organization_social, don't duplicate."""
        url = LinkedInAdapter.get_auth_url(
            client_id="client",
            redirect_uri="https://example.com/cb",
            state="s",
            scope="w_member_social openid profile w_organization_social",
            entity="urn:li:organization:12345",
        )
        # Should appear exactly once
        scope_part = url.split("scope=")[1].split("&")[0]
        from urllib.parse import unquote

        decoded = unquote(scope_part)
        assert decoded.count("w_organization_social") == 1

    def test_personal_string_entity_no_org_scope(self):
        """entity='personal' does not add org scope."""
        url = LinkedInAdapter.get_auth_url(
            client_id="client",
            redirect_uri="https://example.com/cb",
            state="s",
            entity="personal",
        )
        assert "w_organization_social" not in url


# =============================================================================
# Factory pass-through
# =============================================================================


class TestLinkedInFactoryEntity:
    """create_adapter_from_account() passes entity to LinkedInAdapter."""

    @patch("social_hook.adapters.platform.factory.auth.refresh_and_get_token")
    def test_factory_passes_entity(self, mock_refresh):
        """Factory passes account.entity to LinkedInAdapter."""
        from social_hook.adapters.platform.factory import create_adapter_from_account
        from social_hook.config.targets import AccountConfig, PlatformCredentialConfig

        mock_refresh.return_value = "test_token"

        account = AccountConfig(
            platform="linkedin",
            entity="urn:li:organization:12345",
        )
        creds = PlatformCredentialConfig(
            platform="linkedin",
            client_id="cid",
            client_secret="csecret",
        )

        adapter = create_adapter_from_account(
            account_name="li-org",
            account=account,
            platform_creds=creds,
            env={},
            db_path="/tmp/test.db",
        )

        assert isinstance(adapter, LinkedInAdapter)
        assert adapter.entity == "urn:li:organization:12345"

    @patch("social_hook.adapters.platform.factory.auth.refresh_and_get_token")
    def test_factory_default_entity(self, mock_refresh):
        """Factory with no entity results in 'personal' default."""
        from social_hook.adapters.platform.factory import create_adapter_from_account
        from social_hook.config.targets import AccountConfig, PlatformCredentialConfig

        mock_refresh.return_value = "test_token"

        account = AccountConfig(platform="linkedin")
        creds = PlatformCredentialConfig(
            platform="linkedin",
            client_id="cid",
            client_secret="csecret",
        )

        adapter = create_adapter_from_account(
            account_name="li-personal",
            account=account,
            platform_creds=creds,
            env={},
            db_path="/tmp/test.db",
        )

        assert isinstance(adapter, LinkedInAdapter)
        assert adapter.entity == "personal"
