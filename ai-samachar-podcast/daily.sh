#!/bin/zsh
# Daily AI Samachar sheet update, run by launchd at 12:30:
# play numbers, then episode links, then the platform checks and the Episode matrix.
# A step that fails (the website or an app timing out) is tried again up to 2 more
# times, 5 minutes apart. One failed source inside metrics.py does not skip the
# rest of that script. The job exits non-zero when a step still failed, and the
# last lines of logs/metrics.log name which step.
DIR=${0:A:h}
cd "$DIR" || exit 1
source "$DIR/../shared/joblib.zsh"
podcast_load_env
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p logs
podcast_log_to logs/metrics.log
echo "== $(date '+%F %T')"
podcast_run_daily "AI Samachar podcast"
