#!/bin/bash
# Run one show script and print the log tail. The script itself appends to
# logs/check.log or logs/metrics.log, which is what launchd reads on the Mac.
set -u
dir="$1"
script="$2"
cd "$dir"
set +e
zsh "./$script"
code=$?
log="logs/check.log"
[[ "$script" == "daily.sh" ]] && log="logs/metrics.log"
echo "----- ${dir}/${log} (tail) -----"
tail -n 80 "$log" 2>/dev/null || true
exit "$code"
