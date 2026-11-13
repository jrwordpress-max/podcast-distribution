#!/bin/zsh
# Checks the AI Samachar YouTube playlist (see config.env) and turns each new full episode
# into a podcast episode on podcast.rankkking.com. Run by launchd every hour; safe to run by
# hand: ./check.sh
# ./check.sh --list only prints the videos waiting to be processed; it publishes nothing.
DIR=${0:A:h}
cd "$DIR" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
source "$DIR/config.env"
mkdir -p logs work
[[ $1 == --list ]] && LIST=1
if [[ -z $LIST ]]; then
  exec >>logs/check.log 2>&1
  echo "== $(date '+%F %T') check (mode=$MODE)"
fi

notify() { osascript -e "display notification \"${2//\"/\'}\" with title \"${1//\"/\'}\"" >/dev/null 2>&1; }

# One run at a time; a lock older than 2 hours is left over from a crash.
if [[ -z $LIST ]]; then
  if ! mkdir .lock 2>/dev/null; then
    if [[ -n $(find .lock -maxdepth 0 -mmin +120) ]]; then rm -rf .lock && mkdir .lock; else echo "another check is running"; exit 0; fi
  fi
  trap 'rm -rf "$DIR/.lock"' EXIT
fi

lines=$(yt-dlp --flat-playlist --print "%(id)s %(duration)s %(title)s" "https://www.youtube.com/playlist?list=$PLAYLIST_ID" 2>/dev/null)
if [[ -z $lines ]]; then echo "could not read the playlist (offline?)"; exit 0; fi
touch seen.txt
from_playlist=()
for line in ${(f)lines}; do
  id=${line%% *}; rest=${line#* }; secs=${rest%% *}; secs=${secs%.*}; title=${rest#* }
  # Shorts and hidden videos have no usable length; only full episodes count.
  [[ $secs == <-> ]] && (( secs >= MIN_MINUTES * 60 )) || continue
  grep -qxF -- "$id" seen.txt && continue
  from_playlist+=("$id")
  [[ -n $LIST ]] && print -r -- "$id | $(( secs / 60 )) min | $title"
done

# The playlist lists newest first; publish oldest first.
new=(${(Oa)from_playlist})
echo "new videos: ${#new[@]}"
[[ -n $LIST ]] && exit 0
(( ${#new[@]} == 0 )) && exit 0

done_count=0
for id in $new; do
  (( done_count >= MAX_PER_RUN )) && break
  echo "-- $id"
  # Download first, so Claude only runs for a video that is ready (not a scheduled premiere).
  if ! python3 publish.py fetch "$id" > "work/fetch_$id.log" 2>&1; then
    echo "fetch failed: $(tail -c 300 work/fetch_$id.log)"
    continue
  fi
  prompt=${$(<prompt.md)//\{\{VIDEO_ID\}\}/$id}
  prompt=${prompt//\{\{MODE\}\}/$MODE}
  reply=$(claude -p "$prompt" \
    --allowedTools "Bash(python3 publish.py:*)" "Read" "Write" "Edit" \
    --permission-mode acceptEdits --strict-mcp-config --no-session-persistence 2>&1)
  echo "$reply" | tail -5
  # When the Claude login on this Mac has expired, build the show notes straight from the
  # video's description instead, so the daily episode still goes out.
  if [[ ! -f work/$id/result.json && $reply == *(Failed to authenticate|Not logged in|Invalid API key|/login)* ]]; then
    echo "Claude is not signed in; publishing with show notes from the description"
    notify "AI Samachar podcast: Claude login needed" "Episodes still publish, with simpler show notes. Run: claude auth login"
    python3 publish.py autospec "$id" > /dev/null && python3 publish.py publish "$id" "work/$id/spec.json" --status "$MODE" | tail -3
  fi
  if [[ -f work/$id/result.json ]]; then
    echo "$id" >> seen.txt
    info=$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("Ep %s (%s): %s" % (r.get("episode", "?"), r.get("status"), r.get("title")))' "work/$id/result.json")
    notify "AI Samachar podcast" "$info"
    rm -f "work/$id/audio.m4a"   # the copy on the website is the one that counts
    done_count=$((done_count + 1))
  else
    # After 3 failed tries, stop retrying this video so it does not cost a Claude run every hour.
    echo "$id" >> fails.txt
    if (( $(grep -cxF -- "$id" fails.txt) >= 3 )); then
      echo "$id" >> seen.txt
      notify "AI Samachar podcast: gave up" "Video $id failed 3 times. See logs/check.log"
    else
      notify "AI Samachar podcast: will retry" "Video $id was not published. See logs/check.log"
    fi
  fi
done
