"""OCLC OAuth2 client credentials token manager with caching and retries."""

import os
import time
from typing import Optional

import requests

from src.shared.constants import OCLC_OAUTH_SCOPE, OCLC_OAUTH_URL

# Cache: (token_string, expires_at_ts). Refresh 5 minutes before expiry.
_TOKEN_CACHE: Optional[tuple[str, float]] = None
_BUFFER_SECONDS = 5 * 60  # 5 min buffer


class OCLCTokenManager:
    """Manages OCLC OAuth2 client_credentials token with cache and retries."""

    def __init__(self) -> None:
        self._wskey = ""
        self._secret = ""
        self._max_retries = 3
        self._backoff_base = 1.0

        try:
            with open(r"oclc_api_keys_github.txt") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("oclc_wskey"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            self._wskey = parts[1].strip().strip('"\'+')
                    elif line.startswith("oclc_secret"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            self._secret = parts[1].strip().strip('"\'+')
        except Exception as e:
            print(f"Could not read OCLC credentials from github file: {e}")

    def can_make_request(self) -> bool:
        """Return True if credentials are configured."""
        return bool(self._wskey and self._secret)

    def get_shared_token(self) -> Optional[str]:
        """
        Obtain shared client_credentials token from OCLC_OAUTH_URL with given scope.
        Cache token and refresh with 5-minute buffer before expiry.
        Uses retries with backoff on failure.
        """
        global _TOKEN_CACHE
        now = time.time()
        if _TOKEN_CACHE is not None:
            token, expires_at = _TOKEN_CACHE
            if expires_at > now + _BUFFER_SECONDS:
                return token
            _TOKEN_CACHE = None

        data = {
            "grant_type": "client_credentials",
            "scope": OCLC_OAUTH_SCOPE,
        }
        auth = (self._wskey, self._secret)
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    OCLC_OAUTH_URL,
                    data=data,
                    auth=auth,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
                resp.raise_for_status()
                body = resp.json()
                access_token = body.get("access_token")
                expires_in = int(body.get("expires_in", 3600))
                if not access_token:
                    return None
                expires_at = now + expires_in
                _TOKEN_CACHE = (access_token, expires_at)
                return access_token
            except requests.RequestException as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2**attempt))
        raise last_error or RuntimeError("Failed to obtain OCLC token")
