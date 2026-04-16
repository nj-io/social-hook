"""LinkedIn platform adapter using REST API."""

import logging
from collections.abc import Callable
from urllib.parse import urlencode

import requests

from social_hook.adapters.dry_run import dry_run_post_result
from social_hook.adapters.models import (
    PostCapability,
    PostReference,
    PostResult,
    ReferenceType,
)
from social_hook.adapters.platform.base import PlatformAdapter
from social_hook.adapters.rate_limit import RateLimitState, handle_rate_limit
from social_hook.errors import ErrorType, classify_error

logger = logging.getLogger(__name__)

# LinkedIn API endpoints
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_ORG_ACLS_URL = "https://api.linkedin.com/rest/organizationalEntityAcls"

# LinkedIn API version header
LINKEDIN_VERSION = "202501"

# Character limit for LinkedIn posts
LINKEDIN_CHAR_LIMIT = 3000


class LinkedInAdapter(PlatformAdapter):
    """LinkedIn API adapter using OAuth 2.0."""

    def __init__(
        self,
        access_token: str,
        *,
        entity: str | None = None,
        token_refresher: Callable[[], str] | None = None,
    ):
        """Initialize LinkedIn adapter with access token.

        Args:
            access_token: OAuth 2.0 access token
            entity: Posting entity — "personal" (default) or an org URN
                    like "urn:li:organization:12345"
            token_refresher: Optional callback that returns a fresh access token.
                Called on 401 responses to attempt token refresh and retry.
        """
        self.access_token = access_token
        self.entity = entity or "personal"
        self._token_refresher = token_refresher
        self.author_urn: str | None = None
        self._org_validated: bool = False
        self.rate_limit_state = RateLimitState()
        logger.info("LinkedIn adapter: posting as %s", self.entity)

    def _try_refresh_on_401(self, response: requests.Response) -> bool:
        """Attempt token refresh on 401 response.

        Returns:
            True if token was refreshed (caller should retry), False otherwise.
        """
        if response.status_code == 401 and self._token_refresher:
            logger.info("LinkedIn got 401, attempting token refresh...")
            try:
                self.access_token = self._token_refresher()
                return True
            except Exception as e:
                logger.warning("LinkedIn token refresh failed: %s", e)
        return False

    @staticmethod
    def get_auth_url(
        client_id: str,
        redirect_uri: str,
        state: str,
        scope: str = "w_member_social openid profile",
        *,
        entity: str | None = None,
    ) -> str:
        """Generate OAuth authorization URL.

        Note: LinkedIn requires HTTPS redirect URI, no localhost allowed.

        Args:
            client_id: LinkedIn app client ID
            redirect_uri: HTTPS redirect URI (no localhost)
            state: CSRF protection state parameter
            scope: OAuth scopes (default includes posting permission)
            entity: If an org URN, w_organization_social is added to scope

        Returns:
            Authorization URL for user to visit
        """
        # Add org scope when posting as an organization
        if (
            entity
            and entity.startswith("urn:li:organization:")
            and "w_organization_social" not in scope
        ):
            scope = f"{scope} w_organization_social"

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
        }
        return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"

    @staticmethod
    def exchange_code(
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        """Exchange authorization code for access token.

        Args:
            client_id: LinkedIn app client ID
            client_secret: LinkedIn app client secret
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in authorization

        Returns:
            Dict with access_token, expires_in, etc.

        Raises:
            requests.RequestException: If token exchange fails
        """
        response = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def validate(self) -> tuple[bool, str]:
        """Validate credentials and fetch author URN.

        For personal entity: fetches /userinfo to resolve person URN.
        For org entity: also verifies admin access to the organization.

        Returns:
            (True, identity_info) on success, (False, error_message) on failure
        """
        try:
            # Always fetch userinfo to validate the token and get person identity
            response = requests.get(
                LINKEDIN_USERINFO_URL,
                headers=self._auth_headers(),
                timeout=10,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.get(
                    LINKEDIN_USERINFO_URL,
                    headers=self._auth_headers(),
                    timeout=10,
                )

            if response.status_code != 200:
                error_type = classify_error(response)
                error_msg = response.json().get("message", response.text)
                logger.warning(f"LinkedIn validation failed: {error_type} - {error_msg}")
                return (False, f"{error_type.value}: {error_msg}")

            data = response.json()
            sub = data.get("sub")
            name = data.get("name", data.get("sub", "unknown"))

            if self.entity == "personal":
                # Personal posting — use person URN
                if sub:
                    self.author_urn = f"urn:li:person:{sub}"
                return (True, f"Personal: {name}")
            elif self.entity.startswith("urn:li:organization:"):
                # Org posting — set author URN to org, then verify admin access
                self.author_urn = self.entity
                if sub:
                    self._person_urn = f"urn:li:person:{sub}"

                ok, err = self._validate_org_admin()
                if not ok:
                    return (False, err)
                self._org_validated = True
                return (True, f"Org: {name}")
            else:
                logger.warning("LinkedIn: unknown entity format '%s'", self.entity)
                return (False, f"Invalid entity format: {self.entity}")

        except requests.RequestException as e:
            logger.error(f"LinkedIn validation request failed: {e}")
            return (False, f"Request failed: {e}")

    def _validate_org_admin(self) -> tuple[bool, str]:
        """Verify the token has admin access to the configured org entity.

        Returns:
            (True, "") on success, (False, error_message) on failure.
        """
        try:
            response = requests.get(
                LINKEDIN_ORG_ACLS_URL,
                params={
                    "q": "roleAssignee",
                    "role": "ADMINISTRATOR",
                    "projection": "(elements*(organizationalTarget))",
                },
                headers=self._post_headers(),
                timeout=10,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.get(
                    LINKEDIN_ORG_ACLS_URL,
                    params={
                        "q": "roleAssignee",
                        "role": "ADMINISTRATOR",
                        "projection": "(elements*(organizationalTarget))",
                    },
                    headers=self._post_headers(),
                    timeout=10,
                )

            if response.status_code != 200:
                error_type = classify_error(response)
                error_msg = response.json().get("message", response.text)
                logger.warning("LinkedIn org admin check failed: %s - %s", error_type, error_msg)
                return (False, f"Org admin check failed: {error_type.value}: {error_msg}")

            data = response.json()
            elements = data.get("elements", [])

            # Check if user is admin of the configured org
            for element in elements:
                org_target = element.get("organizationalTarget", "")
                if org_target == self.entity:
                    return (True, "")

            logger.warning(
                "LinkedIn: user is not admin of org %s (found: %s)",
                self.entity,
                [e.get("organizationalTarget", "") for e in elements],
            )
            return (False, f"Not an admin of organization {self.entity}")

        except requests.RequestException as e:
            logger.error("LinkedIn org admin check request failed: %s", e)
            return (False, f"Org admin check request failed: {e}")

    def post(
        self,
        content: str,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post content to LinkedIn.

        Args:
            content: Post text (max 3000 characters)
            media_paths: Optional media paths (not yet implemented)
            dry_run: If True, return simulated success

        Returns:
            PostResult with external_id and external_url on success
        """
        if dry_run:
            return dry_run_post_result()

        # Validate content length
        if len(content) > LINKEDIN_CHAR_LIMIT:
            return PostResult(
                success=False,
                error=f"Content exceeds {LINKEDIN_CHAR_LIMIT} character limit ({len(content)} chars)",
            )

        # Ensure we have author URN (resolved via validate or set from org entity)
        if not self.author_urn:
            if self.entity != "personal" and self.entity.startswith("urn:li:organization:"):
                # Org entity — use the org URN directly as author
                self.author_urn = self.entity
            else:
                valid, info = self.validate()
                if not valid:
                    return PostResult(success=False, error=f"Failed to get author URN: {info}")

        # Build request body
        body = {
            "author": self.author_urn,
            "commentary": content,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        return self._post_to_api(body, "post")

    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> PostResult:
        """LinkedIn does not support threads.

        Args:
            tweets: List of posts (only first will be considered)
            dry_run: If True, return simulated failure

        Returns:
            PostResult with error message
        """
        return PostResult(
            success=False,
            error="LinkedIn does not support threads",
        )

    def post_with_reference(
        self,
        content: str,
        reference: PostReference,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post content with a reference to an existing post.

        Args:
            content: Post text
            reference: Reference to an existing post
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success without API call

        Returns:
            PostResult with external_id and external_url on success
        """
        if dry_run:
            return dry_run_post_result()

        if reference.reference_type == ReferenceType.QUOTE and reference.external_id.startswith(
            "urn:li:"
        ):
            # Native reshare for LinkedIn-to-LinkedIn references
            if not self.author_urn:
                if self.entity != "personal" and self.entity.startswith("urn:li:organization:"):
                    self.author_urn = self.entity
                else:
                    valid, info = self.validate()
                    if not valid:
                        return PostResult(success=False, error=f"Failed to get author URN: {info}")

            body = {
                "author": self.author_urn,
                "commentary": content,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
                "reshareContext": {
                    "parent": reference.external_id,
                },
            }

            return self._post_to_api(body, "reshare")

        # TODO: LinkedIn REPLY via Comments API — excluded this iteration
        # REPLY, cross-platform QUOTE, and LINK all embed the URL in commentary
        if reference.external_url:
            content = f"{content}\n\n{reference.external_url}"
        return self.post(content, media_paths, dry_run)

    def supports_reference_type(self, ref_type: ReferenceType) -> bool:
        """LinkedIn supports QUOTE (reshare) and LINK, but not REPLY."""
        return ref_type in (ReferenceType.QUOTE, ReferenceType.LINK)

    def capabilities(self) -> list[PostCapability]:
        from social_hook.adapters.models import ARTICLE, RESHARE, SINGLE

        return [SINGLE, ARTICLE, RESHARE]

    def supports_threads(self) -> bool:
        return False

    def supports_media(self) -> bool:
        return False

    def delete(self, external_id: str) -> bool:
        """Delete a post by ID.

        Args:
            external_id: LinkedIn post URN

        Returns:
            True if deletion succeeded
        """
        try:
            response = requests.delete(
                f"{LINKEDIN_POSTS_URL}/{external_id}",
                headers=self._post_headers(),
                timeout=10,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.delete(
                    f"{LINKEDIN_POSTS_URL}/{external_id}",
                    headers=self._post_headers(),
                    timeout=10,
                )

            return response.status_code in (200, 204)
        except requests.RequestException as e:
            logger.error(f"LinkedIn delete request failed: {e}")
            return False

    def get_rate_limit_status(self) -> dict:
        """Return current rate limit status.

        Returns:
            Dict with rate limit info
        """
        return {
            "attempts": self.rate_limit_state.attempts,
            "backoff_until": (
                self.rate_limit_state.backoff_until.isoformat()
                if self.rate_limit_state.backoff_until
                else None
            ),
        }

    def _post_to_api(self, body: dict, operation: str = "post") -> PostResult:
        """Post a body to the LinkedIn Posts API and return a PostResult."""
        try:
            response = requests.post(
                LINKEDIN_POSTS_URL,
                headers=self._post_headers(),
                json=body,
                timeout=30,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.post(
                    LINKEDIN_POSTS_URL,
                    headers=self._post_headers(),
                    json=body,
                    timeout=30,
                )

            if response.status_code in (200, 201):
                post_id = response.headers.get("x-restli-id", "")
                return PostResult(
                    success=True,
                    external_id=post_id,
                    external_url=f"https://www.linkedin.com/feed/update/{post_id}",
                )
            else:
                error_type = classify_error(response)
                if error_type == ErrorType.RATE_LIMITED:
                    self.rate_limit_state = handle_rate_limit(
                        response, self.rate_limit_state, platform="linkedin"
                    )
                error_detail = response.json().get("message", response.text)
                logger.warning(f"LinkedIn {operation} failed: {error_type} - {error_detail}")
                return PostResult(
                    success=False,
                    error=f"{error_type.value}: {error_detail}",
                )

        except requests.RequestException as e:
            logger.error(f"LinkedIn {operation} request failed: {e}")
            return PostResult(success=False, error=f"Request failed: {e}")

    def _auth_headers(self) -> dict:
        """Get authorization headers for API requests."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def _post_headers(self) -> dict:
        """Get headers for POST requests (includes API version)."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": LINKEDIN_VERSION,
            "Content-Type": "application/json",
        }
