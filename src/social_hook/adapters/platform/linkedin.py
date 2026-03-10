"""LinkedIn platform adapter using REST API."""

import logging
from urllib.parse import urlencode

import requests

from social_hook.adapters.dry_run import dry_run_post_result
from social_hook.adapters.models import PostReference, PostResult, ReferenceType, ThreadResult
from social_hook.adapters.platform.base import PlatformAdapter
from social_hook.adapters.rate_limit import RateLimitState, handle_rate_limit
from social_hook.errors import ErrorType, classify_error

logger = logging.getLogger(__name__)

# LinkedIn API endpoints
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

# LinkedIn API version header
LINKEDIN_VERSION = "202501"

# Character limit for LinkedIn posts
LINKEDIN_CHAR_LIMIT = 3000


class LinkedInAdapter(PlatformAdapter):
    """LinkedIn API adapter using OAuth 2.0."""

    def __init__(self, access_token: str):
        """Initialize LinkedIn adapter with access token.

        Args:
            access_token: OAuth 2.0 access token
        """
        self.access_token = access_token
        self.author_urn: str | None = None
        self.rate_limit_state = RateLimitState()

    @staticmethod
    def get_auth_url(
        client_id: str,
        redirect_uri: str,
        state: str,
        scope: str = "w_member_social openid profile",
    ) -> str:
        """Generate OAuth authorization URL.

        Note: LinkedIn requires HTTPS redirect URI, no localhost allowed.

        Args:
            client_id: LinkedIn app client ID
            redirect_uri: HTTPS redirect URI (no localhost)
            state: CSRF protection state parameter
            scope: OAuth scopes (default includes posting permission)

        Returns:
            Authorization URL for user to visit
        """
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

        Returns:
            (True, profile_name) on success, (False, error_message) on failure
        """
        try:
            response = requests.get(
                LINKEDIN_USERINFO_URL,
                headers=self._auth_headers(),
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                # Construct author URN from 'sub' field
                sub = data.get("sub")
                if sub:
                    self.author_urn = f"urn:li:person:{sub}"

                name = data.get("name", data.get("sub", "unknown"))
                return (True, name)
            else:
                error_type = classify_error(response)
                error_msg = response.json().get("message", response.text)
                logger.warning(f"LinkedIn validation failed: {error_type} - {error_msg}")
                return (False, f"{error_type.value}: {error_msg}")

        except requests.RequestException as e:
            logger.error(f"LinkedIn validation request failed: {e}")
            return (False, f"Request failed: {e}")

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

        # Ensure we have author URN
        if not self.author_urn:
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

    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> ThreadResult:
        """LinkedIn does not support threads.

        Args:
            tweets: List of posts (only first will be considered)
            dry_run: If True, return simulated failure

        Returns:
            ThreadResult with error message
        """
        return ThreadResult(
            success=False,
            tweet_results=[],
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
