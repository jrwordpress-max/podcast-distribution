"""Load a show's config.env. Environment variables and secret files override it.

Secret files are never required. A missing file is skipped. Values already set in
the environment win, so a server or GitHub Actions secret is not replaced by the
placeholder in config.env.
"""
import os

# Keys a server may set. Empty values do not override the file.
ENV_OVERLAY = (
    "MODE", "SHEET_ID", "PLAYLIST_ID", "FEED_URL", "SITE", "SERIES",
    "MAX_PER_RUN", "CATCH_UP", "CATCH_UP_MAX", "MIN_MINUTES", "COVER_ID",
    "PI_API_KEY", "PI_API_SECRET",
    "CHANNEL_ID", "CHANNEL_MATCH", "CHANNEL_SINCE", "CHANNEL_SCAN",
    "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
    "WP_API_USERNAME", "WP_API_PASSWORD", "NOTIFY_HOOK", "SLACK_WEBHOOK_URL",
    "COMPOSIO_API_KEY", "COMPOSIO_ORG_ID", "COMPOSIO_PROJECT_ID",
)


def parse_env_file(path):
    cfg = {}
    if not path or not os.path.isfile(path):
        return cfg
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = _unquote(value.strip())
    return cfg


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def secret_file_paths(show_dir):
    show_dir = os.path.abspath(show_dir)
    root = os.path.dirname(show_dir)
    return (
        os.path.join(root, "secrets.env"),
        os.path.join(show_dir, "secrets.env"),
        os.path.join(show_dir, ".wp.env"),
    )


def load_secret_files(show_dir, environ=None):
    """Copy secrets into environ when that variable is not already set."""
    environ = os.environ if environ is None else environ
    for path in secret_file_paths(show_dir):
        for key, value in parse_env_file(path).items():
            if value and not environ.get(key):
                environ[key] = value


def load_config(show_dir, environ=None):
    environ = os.environ if environ is None else environ
    cfg = parse_env_file(os.path.join(show_dir, "config.env"))
    load_secret_files(show_dir, environ)
    for key in ENV_OVERLAY:
        value = environ.get(key)
        if value:
            cfg[key] = value
    return cfg
