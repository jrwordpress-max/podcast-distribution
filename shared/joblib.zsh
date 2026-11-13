# Shared shell helpers for check.sh and daily.sh.
# Source this from a zsh script after DIR is set to the show folder.
# launchd on the Mac keeps working: osascript notifications stay, and every
# variable still comes from config.env when the environment does not set it.

podcast_load_env() {
  local root="${DIR:h}"
  local -A preset
  local k
  # Values already exported (a server, launchd, or GitHub Actions) win over the file.
  for k in MODE SHEET_ID PLAYLIST_ID FEED_URL SITE SERIES MAX_PER_RUN CATCH_UP CATCH_UP_MAX \
           MIN_MINUTES COVER_ID PI_API_KEY PI_API_SECRET CHANNEL_ID CHANNEL_MATCH CHANNEL_SINCE \
           CHANNEL_SCAN CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL \
           WP_API_USERNAME WP_API_PASSWORD NOTIFY_HOOK SLACK_WEBHOOK_URL \
           COMPOSIO_API_KEY COMPOSIO_ORG_ID COMPOSIO_PROJECT_ID; do
    [[ -n "${(P)k:-}" ]] && preset[$k]="${(P)k}"
  done
  source "$DIR/config.env"
  [[ -f "$root/secrets.env" ]] && source "$root/secrets.env"
  [[ -f "$DIR/secrets.env" ]] && source "$DIR/secrets.env"
  [[ -f "$DIR/.wp.env" ]] && source "$DIR/.wp.env"
  for k in ${(k)preset}; do
    eval "$k=${(q)preset[$k]}"
  done
  for k in MODE SHEET_ID PLAYLIST_ID FEED_URL SITE SERIES MAX_PER_RUN CATCH_UP CATCH_UP_MAX \
           MIN_MINUTES COVER_ID PI_API_KEY PI_API_SECRET CHANNEL_ID CHANNEL_MATCH CHANNEL_SINCE \
           CHANNEL_SCAN CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL \
           WP_API_USERNAME WP_API_PASSWORD NOTIFY_HOOK SLACK_WEBHOOK_URL \
           COMPOSIO_API_KEY COMPOSIO_ORG_ID COMPOSIO_PROJECT_ID; do
    [[ -n "${(P)k:-}" ]] && export "$k"
  done
}

podcast_notify() {
  local title="$1" body="$2"
  local root="${DIR:h}"
  print -r -- "NOTIFY: ${title}: ${body}"
  if [[ -n "${NOTIFY_HOOK:-}" ]]; then
    TITLE="$title" BODY="$body" zsh -c "$NOTIFY_HOOK" -- "$title" "$body" \
      || print -r -- "WARN: NOTIFY_HOOK failed"
  fi
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    TITLE="$title" BODY="$body" python3 "$root/shared/podcastlib/notify_slack.py" "$title" "$body" || true
  fi
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${body//\"/\'}\" with title \"${title//\"/\'}\"" >/dev/null 2>&1 || true
  fi
}

# Log to the show's log file, same as the launchd jobs always have.
# A server or GitHub Actions run prints the tail of this file after the job
# so a failure summary is visible there too.
podcast_log_to() {
  mkdir -p "$(dirname "$1")"
  exec >>"$1" 2>&1
}

podcast_retry() {
  local title="$1" label="$2" script="$3"
  local try sleep_s=${RETRY_SLEEP:-300}
  local n
  for try in 1 2 3; do
    python3 "$script" && return 0
    n=$?
    if (( try < 3 )); then
      print -r -- "$script failed (try $try of 3, exit $n), trying again in $sleep_s seconds"
      sleep "$sleep_s"
    fi
  done
  podcast_notify "$title" "$label were not updated. See logs/metrics.log"
  return 1
}

podcast_run_daily() {
  local title="$1"
  local -a failed
  local label script
  failed=()
  for label script in \
      "Daily numbers" metrics.py \
      "Episode links" episode_links.py \
      "Platform checks" platforms.py; do
    podcast_retry "$title" "$label" "$script" || failed+=("$label")
  done
  if (( ${#failed} )); then
    local msg="ERROR: sheet update incomplete: ${(j:, :)failed}"
    print -r -- "$msg"
    podcast_notify "$title" "$msg"
    exit 1
  fi
  print -r -- "OK: sheet update finished"
  exit 0
}
