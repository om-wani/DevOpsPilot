"""Validate the Azure DevOps token the extension sends.

The widget gets its token from `SDK.getAccessToken()` and sends it as a bearer
token. There is no way to verify that token's signature locally: the signing
keys are not published. The supported check is to spend the token against the
profile API. A 200 proves it is genuine and tells us who the caller is.

Without this the chat endpoint is an open door to an Azure OpenAI key.
"""

import hashlib
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

PROFILE_URL = "https://app.vssps.visualstudio.com/_apis/profile/profiles/me"
API_VERSION = "7.1"
TIMEOUT = 10

# Validated tokens are cached so a chat request does not pay a round trip to
# the profile API every time. Short enough that a revoked token stops working
# quickly.
CACHE_TTL_SECONDS = 300

_cache = {}


class AuthError(Exception):
    """The caller's token is missing or not valid."""

    def __init__(self, message="Sign in to Azure DevOps to use this extension."):
        super().__init__(message)
        self.message = message


def _cache_key(token):
    # Never keep the raw token in memory as a dict key.
    return hashlib.sha256(token.encode()).hexdigest()


def _cached(key):
    entry = _cache.get(key)
    if not entry:
        return None
    user, expires_at = entry
    if expires_at < time.monotonic():
        _cache.pop(key, None)
        return None
    return user


def verify_token(token):
    """Return the caller's identity, or raise AuthError.

    Identity is `{"id": ..., "name": ...}` taken from the Azure DevOps profile.
    """
    if not token or not token.strip():
        raise AuthError()

    key = _cache_key(token)
    cached = _cached(key)
    if cached:
        return cached

    try:
        response = requests.get(
            PROFILE_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"api-version": API_VERSION},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        # Never surface the transport error to the client.
        raise AuthError("Could not reach Azure DevOps to verify your session.")

    # Azure DevOps does not return 401 for a bad token. It returns 203 with an
    # HTML sign-in page, which passes `response.ok`. Demand 200 and real JSON,
    # or an invalid token parses as a crash instead of a rejection.
    if response.status_code != 200:
        raise AuthError()
    if "json" not in response.headers.get("content-type", ""):
        raise AuthError()

    try:
        profile = response.json()
    except ValueError:
        raise AuthError()

    user = {
        "id": profile.get("id", ""),
        "name": profile.get("displayName", ""),
    }
    if not user["id"]:
        raise AuthError("Could not verify your Azure DevOps session.")

    _cache[key] = (user, time.monotonic() + CACHE_TTL_SECONDS)
    return user


def bearer_token(authorization_header):
    """Pull the token out of an `Authorization: Bearer <token>` header."""
    if not authorization_header:
        raise AuthError()

    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError()
    return token.strip()


def clear_cache():
    """Drop every cached validation. Used by tests."""
    _cache.clear()
