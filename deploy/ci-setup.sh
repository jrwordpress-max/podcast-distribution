#!/bin/bash
# Tools for a GitHub Actions or other Linux run. The Mac does not use this.
# Pass "daily" to also install the Composio CLI (the sheet job). The episode
# check only needs yt-dlp, ffmpeg and, when CLAUDE_CODE_OAUTH_TOKEN is set,
# the Claude Code CLI. ANTHROPIC_API_KEY works without that CLI.
set -euo pipefail
kind="${1:-check}"
sudo apt-get update
sudo apt-get install -y zsh ffmpeg curl ca-certificates
python3 -m pip install -U yt-dlp
if [[ "$kind" == "daily" || "$kind" == "all" ]]; then
  if [[ -n "${COMPOSIO_API_KEY:-}" ]]; then
    curl -fsSL https://composio.dev/install | COMPOSIO_INSTALL_PLUGINS=0 sh
    export PATH="$HOME/.local/bin:$PATH"
    if [[ -n "${COMPOSIO_ORG_ID:-}" && -n "${COMPOSIO_PROJECT_ID:-}" ]]; then
      composio login --api-key "$COMPOSIO_API_KEY" --org-id "$COMPOSIO_ORG_ID" --project-id "$COMPOSIO_PROJECT_ID"
    fi
  else
    echo "WARN: COMPOSIO_API_KEY is not set; the sheet job can only work if composio login was already stored"
  fi
fi
if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
  curl -fsSL https://claude.ai/install.sh | bash \
    || echo "WARN: Claude CLI install failed. Set ANTHROPIC_API_KEY to write show notes without the CLI."
fi
echo "$HOME/.local/bin" >> "${GITHUB_PATH:-/dev/null}" || true
