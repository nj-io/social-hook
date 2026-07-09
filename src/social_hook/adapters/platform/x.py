"""X (Twitter) platform adapter using API v2 with OAuth 2.0 Bearer token."""

import logging
from collections.abc import Callable

import requests

from social_hook.adapters.dry_run import dry_run_post_result, dry_run_thread_result
from social_hook.adapters.models import (
    PostCapability,
    PostReference,
    PostResult,
    ReferenceType,
)
from social_hook.adapters.platform.base import PlatformAdapter
from social_hook.adapters.rate_limit import RateLimitState, handle_rate_limit
from social_hook.config.yaml import TIER_CHAR_LIMITS, VALID_TIERS
from social_hook.errors import ConfigError, ErrorType, classify_x_error

logger = logging.getLogger(__name__)

# X API v2 endpoints
X_API_BASE = "https://api.x.com/2"
X_TWEETS_URL = f"{X_API_BASE}/tweets"
X_USERS_ME_URL = f"{X_API_BASE}/users/me"
X_MEDIA_UPLOAD_URL = f"{X_API_BASE}/media/upload"

# Character limit for X posts (free tier / thread tweets)
X_CHAR_LIMIT = 280


class XAdapter(PlatformAdapter):
    """X (Twitter) API v2 adapter using OAuth 2.0 Bearer token."""

    def __init__(
        self,
        access_token: str,
        *,
        tier: str = "free",
        token_refresher: Callable[[], str] | None = None,
    ):
        """Initialize X adapter with OAuth 2.0 Bearer token.

        Args:
            access_token: OAuth 2.0 Bearer token for all API calls.
            tier: Account tier (free, basic, premium, premium_plus).
            token_refresher: Optional callback that returns a fresh access token.
                Called on 401 responses to attempt token refresh and retry.

        Raises:
            ConfigError: If access_token is missing or tier is invalid.
        """
        if not access_token:
            raise ConfigError("Missing X OAuth 2.0 access token")

        if tier not in VALID_TIERS:
            raise ConfigError(f"Invalid tier '{tier}', must be one of {VALID_TIERS}")

        self.access_token = access_token
        self.tier = tier
        self.char_limit = TIER_CHAR_LIMITS[tier]
        self._token_refresher = token_refresher
        self.rate_limit_state = RateLimitState()
        self._cached_username: str | None = None

    def _auth_headers(self) -> dict:
        """Return Authorization header with current Bearer token."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def _try_refresh_on_401(self, response: requests.Response) -> bool:
        """Attempt token refresh on 401 response.

        Returns:
            True if token was refreshed (caller should retry), False otherwise.
        """
        if response.status_code == 401 and self._token_refresher:
            logger.info("Got 401, attempting token refresh...")
            try:
                self.access_token = self._token_refresher()
                return True
            except Exception as e:
                logger.warning("Token refresh failed: %s", e)
        return False

    def validate(self) -> tuple[bool, str]:
        """Validate credentials by fetching current user.

        Returns:
            (True, "@username") on success, (False, error_message) on failure
        """
        try:
            response = requests.get(X_USERS_ME_URL, headers=self._auth_headers(), timeout=10)

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.get(X_USERS_ME_URL, headers=self._auth_headers(), timeout=10)

            if response.status_code == 200:
                data = response.json().get("data", {})
                username = data.get("username", "unknown")
                self._cached_username = username
                return (True, f"@{username}")
            else:
                error_type = classify_x_error(response)
                try:
                    body = response.json()
                    error_msg = body.get("detail") or body.get("title") or response.text
                except Exception:
                    error_msg = response.text
                logger.warning(f"X validation failed: {error_type} - {error_msg}")
                return (False, f"{error_type.value}: {error_msg}")

        except requests.RequestException as e:
            logger.error(f"X validation request failed: {e}")
            return (False, f"Request failed: {e}")

    def post(
        self,
        content: str,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post a single tweet.

        Args:
            content: Tweet text (limit depends on account tier)
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success

        Returns:
            PostResult with external_id and external_url on success
        """
        if dry_run:
            return dry_run_post_result()

        # Validate content length against tier limit
        if len(content) > self.char_limit:
            return PostResult(
                success=False,
                error=f"Content exceeds {self.char_limit} character limit ({len(content)} chars)",
            )

        # Build request body
        body: dict = {"text": content}
        self._attach_media(body, media_paths)

        return self._post_tweet(body)

    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> PostResult:
        """Post a thread of connected tweets.

        Uses atomic failure: stops on first error, returns partial results.

        Args:
            tweets: List of dicts with 'content' and optional 'media_paths'
            dry_run: If True, return simulated success

        Returns:
            PostResult with part_results for per-tweet results

        Raises:
            ValueError: If tweets list is empty
        """
        if not tweets:
            raise ValueError("Thread must contain at least one tweet")

        if dry_run:
            return dry_run_thread_result(len(tweets))

        results: list[PostResult] = []
        reply_to_id: str | None = None

        for i, tweet in enumerate(tweets):
            content = tweet.get("content", "")
            media_paths = tweet.get("media_paths", [])

            # Validate content length
            if len(content) > X_CHAR_LIMIT:
                results.append(
                    PostResult(
                        success=False,
                        error=f"Tweet {i + 1} exceeds {X_CHAR_LIMIT} characters",
                    )
                )
                return PostResult(
                    success=False,
                    part_results=results,
                    error=f"Tweet {i + 1} failed: content too long",
                )

            # Build request body
            body: dict = {"text": content}

            # Add reply reference for thread chaining
            if reply_to_id:
                body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

            self._attach_media(body, media_paths)

            result = self._post_tweet(body)
            results.append(result)

            if not result.success:
                # Atomic failure: stop and return
                return PostResult(
                    success=False,
                    part_results=results,
                    error=f"Tweet {i + 1} failed: {result.error}",
                )

            reply_to_id = result.external_id

        return PostResult(success=True, part_results=results)

    def post_with_reference(
        self,
        content: str,
        reference: PostReference,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post content with a reference to an existing tweet.

        Args:
            content: Tweet text
            reference: Reference to an existing post
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success without API call

        Returns:
            PostResult with external_id and external_url on success
        """
        if reference.reference_type == ReferenceType.QUOTE:
            if dry_run:
                return dry_run_post_result()
            body: dict = {"text": content, "quote_tweet_id": reference.external_id}
            self._attach_media(body, media_paths)
            return self._post_tweet(body)

        if reference.reference_type == ReferenceType.REPLY:
            if dry_run:
                return dry_run_post_result()
            body = {
                "text": content,
                "reply": {"in_reply_to_tweet_id": reference.external_id},
            }
            self._attach_media(body, media_paths)
            return self._post_tweet(body)

        # LINK fallback: append URL to content
        content_with_url = (
            f"{content}\n\n{reference.external_url}" if reference.external_url else content
        )
        return self.post(content_with_url, media_paths, dry_run)

    def supports_reference_type(self, ref_type: ReferenceType) -> bool:
        """X supports all reference types natively."""
        return ref_type in (ReferenceType.REPLY, ReferenceType.QUOTE, ReferenceType.LINK)

    def capabilities(self) -> list[PostCapability]:
        from social_hook.adapters.models import ARTICLE, QUOTE, REPLY, SINGLE, THREAD

        return [SINGLE, THREAD, ARTICLE, QUOTE, REPLY]

    def supports_threads(self) -> bool:
        return True

    def supports_media(self) -> bool:
        return True

    def delete(self, external_id: str) -> bool:
        """Delete a tweet by ID.

        Args:
            external_id: Tweet ID to delete

        Returns:
            True if deletion succeeded
        """
        try:
            response = requests.delete(
                f"{X_TWEETS_URL}/{external_id}",
                headers=self._auth_headers(),
                timeout=10,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.delete(
                    f"{X_TWEETS_URL}/{external_id}",
                    headers=self._auth_headers(),
                    timeout=10,
                )

            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Delete request failed: {e}")
            return False

    def get_rate_limit_status(self) -> dict:
        """Return current rate limit status.

        Returns:
            Dict with rate limit info from last response
        """
        return {
            "attempts": self.rate_limit_state.attempts,
            "backoff_until": (
                self.rate_limit_state.backoff_until.isoformat()
                if self.rate_limit_state.backoff_until
                else None
            ),
        }

    def _attach_media(self, body: dict, media_paths: list[str] | None) -> None:
        """Upload and attach media to a tweet body (in-place).

        Enforces the per-(vehicle, platform) cap before upload by reading
        ``get_max_media_count("single", "x")`` from ``vehicle.py`` — this
        is the single source of truth (currently 4 via MULTI_IMAGE_X).
        Thread parts are capped separately by THREAD capability at 1.
        """
        if not media_paths:
            return
        from social_hook.vehicle import get_max_media_count

        cap = get_max_media_count("single", "x")
        if len(media_paths) > cap:
            logger.warning(
                "X single post received %d media items; cap is %d. Truncating.",
                len(media_paths),
                cap,
            )
            media_paths = media_paths[:cap]
        media_ids = self._upload_media(media_paths)
        if media_ids:
            body["media"] = {"media_ids": media_ids}

    def _post_tweet(self, body: dict) -> PostResult:
        """Internal method to post a tweet.

        Args:
            body: Request body for tweet creation

        Returns:
            PostResult with external_id and external_url on success
        """
        try:
            response = requests.post(
                X_TWEETS_URL,
                headers=self._auth_headers(),
                json=body,
                timeout=30,
            )

            # Retry once on 401
            if self._try_refresh_on_401(response):
                response = requests.post(
                    X_TWEETS_URL,
                    headers=self._auth_headers(),
                    json=body,
                    timeout=30,
                )

            if response.status_code in (200, 201):
                data = response.json().get("data", {})
                tweet_id = data.get("id")
                username = self._cached_username or "user"
                return PostResult(
                    success=True,
                    external_id=tweet_id,
                    external_url=f"https://x.com/{username}/status/{tweet_id}",
                )
            else:
                error_type = classify_x_error(response)
                if error_type == ErrorType.RATE_LIMITED:
                    self.rate_limit_state = handle_rate_limit(
                        response, self.rate_limit_state, platform="x"
                    )

                try:
                    error_body = response.json()
                    error_detail = (
                        error_body.get("detail") or error_body.get("title") or response.text
                    )
                except Exception:
                    error_detail = response.text
                logger.warning(f"Tweet failed: {error_type} - {error_detail}")
                return PostResult(
                    success=False,
                    error=f"{error_type.value}: {error_detail}",
                )

        except requests.RequestException as e:
            logger.error(f"Tweet request failed: {e}")
            return PostResult(success=False, error=f"Request failed: {e}")

    def _upload_media(self, media_paths: list[str]) -> list[str]:
        """Upload media files and return media IDs.

        Args:
            media_paths: List of file paths to upload

        Returns:
            List of media IDs for successfully uploaded files
        """
        media_ids = []

        for path in media_paths:
            try:
                with open(path, "rb") as f:
                    files = {"media": f}
                    response = requests.post(
                        X_MEDIA_UPLOAD_URL,
                        headers=self._auth_headers(),
                        files=files,
                        data={"media_category": "tweet_image"},
                        timeout=60,
                    )

                    # Retry once on 401
                    if self._try_refresh_on_401(response):
                        f.seek(0)
                        response = requests.post(
                            X_MEDIA_UPLOAD_URL,
                            headers=self._auth_headers(),
                            files={"media": f},
                            data={"media_category": "tweet_image"},
                            timeout=60,
                        )

                    if response.status_code in (200, 201):
                        data = response.json().get("data", {})
                        media_id = data.get("id")
                        if media_id:
                            media_ids.append(media_id)
                    else:
                        logger.warning(f"Media upload failed for {path}: {response.text}")

            except (OSError, requests.RequestException) as e:
                logger.error(f"Media upload error for {path}: {e}")

        return media_ids
