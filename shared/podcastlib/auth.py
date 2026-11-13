"""Detect a Claude CLI login failure. The episode still publishes after this."""

# The same phrases check.sh used to look for, plus the setup-token expiry text.
AUTH_MARKERS = (
    "failed to authenticate",
    "not logged in",
    "invalid api key",
    "oauth session expired",
    "oauth token has expired",
    "please run /login",
    "/login",
    "claude auth login",
    "claude setup-token",
)


def is_auth_failure(text):
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in AUTH_MARKERS)
