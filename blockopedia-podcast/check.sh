#!/bin/zsh
# Checks the Block Talks YouTube playlist and the channel's matching uploads (see
# config.env) and turns each new video into a podcast episode. Run by launchd daily at
# 11:00; safe to run by hand: ./check.sh
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

ids=$(yt-dlp --flat-playlist --print id "https://www.youtube.com/playlist?list=$PLAYLIST_ID" 2>/dev/null)
if [[ -z $ids ]]; then echo "could not read the playlist (offline?)"; exit 0; fi
touch seen.txt skip.txt
from_playlist=()
for id in ${(f)ids}; do grep -qxF -- "$id" seen.txt || from_playlist+=("$id"); done

# Channel uploads, newest first. A matching video older than CHANNEL_SINCE goes to
# skip.txt, so its upload date is looked up only once.
from_channel=()
if [[ -n $CHANNEL_ID ]]; then
  uploads=$(yt-dlp --flat-playlist --playlist-end "${CHANNEL_SCAN:-30}" --print "%(id)s %(duration)s %(title)s" \
    "https://www.youtube.com/channel/$CHANNEL_ID/videos" 2>/dev/null)
  [[ -z $uploads ]] && echo "could not read the channel uploads"
  for line in ${(f)uploads}; do
    id=${line%% *}; rest=${line#* }; secs=${rest%% *}; secs=${secs%.*}; title=${rest#* }
    [[ ${title:l} == *${CHANNEL_MATCH:l}* ]] || continue
    [[ $secs == <-> ]] && (( secs >= MIN_MINUTES * 60 )) || continue
    grep -qxF -- "$id" seen.txt skip.txt && continue
    (( ${from_playlist[(Ie)$id]} )) && continue
    day=$(yt-dlp --skip-download --print upload_date "https://www.youtube.com/watch?v=$id" 2>/dev/null)
    if [[ $day != <-> ]]; then echo "no upload date yet for $id, trying again next check"; continue; fi
    if (( day < CHANNEL_SINCE )); then echo "$id" >> skip.txt; continue; fi
    from_channel+=("$id")
    [[ -n $LIST ]] && print -r -- "$id | $day | $(( secs / 60 )) min | $title"
  done
fi

# The playlist and the channel both list newest first; publish oldest first.
new=(${(Oa)from_playlist} ${(Oa)from_channel})
echo "new videos: ${#new[@]} (playlist ${#from_playlist[@]}, channel ${#from_channel[@]})"
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
  if [[ -f work/$id/result.json ]]; then
    echo "$id" >> seen.txt
    info=$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("Ep %s (%s): %s" % (r.get("episode", "?"), r.get("status"), r.get("title")))' "work/$id/result.json")
    notify "Block Talks podcast" "$info"
    rm -f "work/$id/audio.m4a"   # the copy on the website is the one that counts
    done_count=$((done_count + 1))
  elif [[ $reply == *(Failed to authenticate|Not logged in|Invalid API key|/login)* ]]; then
    # The Claude login on this Mac has expired. That is not the video's fault, so it is not
    # counted as a failure; every waiting video is tried again once the login is back.
    echo "Claude is not signed in; stopping until it is"
    notify "Block Talks podcast: Claude login needed" "New episodes are waiting. Run: claude auth login"
    break
  else
    # After 3 failed tries, stop retrying this video so it doesn't cost a Claude run every day.
    echo "$id" >> fails.txt
    if (( $(grep -cxF -- "$id" fails.txt) >= 3 )); then
      echo "$id" >> seen.txt
      notify "Block Talks podcast: gave up" "Video $id failed 3 times. See logs/check.log"
    else
      notify "Block Talks podcast: will retry" "Video $id was not published. See logs/check.log"
    fi
  fi
done
