#!/bin/zsh
# Daily AI Samachar sheet update, run by launchd at 12:30:
# play numbers, then episode links, then the platform checks and the Episode matrix.
# A step that fails (the website or an app timing out) is tried again up to 2 more
# times, 5 minutes apart, before a notification says it was not updated.
DIR=${0:A:h}
cd "$DIR" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
exec >>logs/metrics.log 2>&1
echo "== $(date '+%F %T')"

notify() { osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1; }

run() {  # run <what, for the notification> <script>
  for try in 1 2 3; do
    python3 "$2" && return 0
    if (( try < 3 )); then echo "$2 failed (try $try of 3), trying again in 5 minutes"; sleep 300; fi
  done
  notify "AI Samachar podcast" "$1 were not updated. See logs/metrics.log"
  return 1
}

run "Daily numbers" metrics.py
run "Episode links" episode_links.py
run "Platform checks" platforms.py
