"""X (Twitter) platform adapter using API v2."""

import logging
from typing import Optional

import requests
from requests_oauthlib import OAuth1

from social_hook.adapters.dry_run import dry_run_post_result, dry_run_thread_result
from social_hook.adapters.models import PostResult, ThreadResult
from social_hook.adapters.platform.base import PlatformAdapter
from social_hook.adapters.rate_limit import RateLimitState, handle_rate_limit
from social_hook.errors import ConfigError, ErrorType, classify_x_error

logger = logging.getLogger(__name__)

# X API v2 endpoints
X_API_BASE = "https://api.x.com/2"
X_TWEETS_URL = f"{X_API_BASE}/tweets"
X_USERS_ME_URL = f"{X_API_BASE}/users/me"
X_MEDIA_UPLOAD_URL = f"{X_API_BASE}/media/upload"

# Character limit for X posts
X_CHAR_LIMIT = 280


class XAdapter(PlatformAdapter):
    """X (Twitter) API v2 adapter using OAuth 1.0a."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
    ):
        """Initialize X adapter with OAuth 1.0a credentials.

        Args:
            api_key: X API key (consumer key)
            api_secret: X API secret (consumer secret)
            access_token: User access token
            access_token_secret: User access token secret

        Raises:
            ConfigError: If any credentials are missing
        """
        if not all([api_key, api_secret, access_token, access_token_secret]):
            raise ConfigError("Missing required X API credentials")

        self.auth = OAuth1(
            api_key,
            client_secret=api_secret,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret,
        )
        self.rate_limit_state = RateLimitState()
        self._cached_username: Optional[str] = None

    def validate(self) -> tuple[bool, str]:
        """Validate credentials by fetching current user.

        Returns:
            (True, "@username") on success, (False, error_message) on failure
        """
        try:
            response = requests.get(X_USERS_ME_URL, auth=self.auth, timeout=10)

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
        media_paths: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post a single tweet.

        Args:
            content: Tweet text (max 280 characters)
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success

        Returns:
            PostResult with external_id and external_url on success
        """
        if dry_run:
            return dry_run_post_result()

        # Validate content length
        if len(content) > X_CHAR_LIMIT:
            return PostResult(
                success=False,
                error=f"Content exceeds {X_CHAR_LIMIT} character limit ({len(content)} chars)",
            )

        # Build request body
        body: dict = {"text": content}

        # Upload and attach media if present
        if media_paths:
            media_ids = self._upload_media(media_paths)
            if media_ids:
                body["media"] = {"media_ids": media_ids}

        return self._post_tweet(body)

    def post_thread(
        self, tweets: list[dict], dry_run: bool = False
    ) -> ThreadResult:
        """Post a thread of connected tweets.

        Uses atomic failure: stops on first error, returns partial results.

        Args:
            tweets: List of dicts with 'content' and optional 'media_paths'
            dry_run: If True, return simulated success

        Returns:
            ThreadResult with per-tweet results

        Raises:
            ValueError: If tweets list is empty
        """
        if not tweets:
            raise ValueError("Thread must contain at least one tweet")

        if dry_run:
            return dry_run_thread_result(len(tweets))

        results: list[PostResult] = []
        reply_to_id: Optional[str] = None

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
                return ThreadResult(
                    success=False,
                    tweet_results=results,
                    error=f"Tweet {i + 1} failed: content too long",
                )

            # Build request body
            body: dict = {"text": content}

            # Add reply reference for thread chaining
            if reply_to_id:
                body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

            # Upload and attach media if present
            if media_paths:
                media_ids = self._upload_media(media_paths)
                if media_ids:
                    body["media"] = {"media_ids": media_ids}

            result = self._post_tweet(body)
            results.append(result)

            if not result.success:
                # Atomic failure: stop and return
                return ThreadResult(
                    success=False,
                    tweet_results=results,
                    error=f"Tweet {i + 1} failed: {result.error}",
                )

            reply_to_id = result.external_id

        return ThreadResult(success=True, tweet_results=results)

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
                auth=self.auth,
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
                auth=self.auth,
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
                    body = response.json()
                    error_detail = body.get("detail") or body.get("title") or response.text
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
                        auth=self.auth,
                        files=files,
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
