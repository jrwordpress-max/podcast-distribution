#!/bin/zsh
# Checks the AI Samachar YouTube playlist (see config.env) and turns each new full episode
# into a podcast episode on podcast.rankkking.com. Run by launchd every hour; safe to run by
# hand: ./check.sh
# ./check.sh --list only prints the videos waiting to be processed; it publishes nothing.
#
# An expired or missing Claude login does not stop the episode. Show notes are written by
# the Claude CLI when it can log in (including CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY),
# and otherwise from the YouTube description.
DIR=${0:A:h}
cd "$DIR" || exit 1
source "$DIR/../shared/joblib.zsh"
podcast_load_env
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SHOW_NAME="AI Samachar podcast"
SHARED="$DIR/../shared/podcastlib"
mkdir -p logs work
touch seen.txt fails.txt
[[ $1 == --list ]] && LIST=1
if [[ -z $LIST ]]; then
  podcast_log_to logs/check.log
  echo "== $(date '+%F %T') check (mode=$MODE catch_up=${CATCH_UP:-1})"
fi

# One run at a time; a lock older than 2 hours is left over from a crash.
if [[ -z $LIST ]]; then
  if ! mkdir .lock 2>/dev/null; then
    if [[ -n $(find .lock -maxdepth 0 -mmin +120) ]]; then rm -rf .lock && mkdir .lock; else echo "another check is running"; exit 0; fi
  fi
  trap 'rm -rf "$DIR/.lock"' EXIT
  # Videos already on the site count as seen, so a fresh machine does not publish them again.
  if python3 publish.py existing > work/on_site.txt 2>work/on_site.err; then
    while IFS= read -r id; do
      [[ -z $id || $id == \{* ]] && continue
      grep -qxF -- "$id" seen.txt || print -r -- "$id" >> seen.txt
    done < work/on_site.txt
  else
    echo "WARN: could not list episodes already on the site; continuing with seen.txt"
  fi
fi

fmt='%(id)s\t%(upload_date)s\t%(timestamp)s\t%(duration)s\t%(title)s'
raw=$(yt-dlp --flat-playlist --print "$fmt" "https://www.youtube.com/playlist?list=$PLAYLIST_ID" 2>/dev/null) || true
if [[ -z $raw ]]; then
  echo "ERROR: could not read the playlist (offline?)"
  [[ -z $LIST ]] && podcast_notify "$SHOW_NAME" "Could not read the YouTube playlist. See logs/check.log"
  exit 1
fi

min_seconds=$(( MIN_MINUTES * 60 ))
if [[ -n $LIST ]]; then
  print -r -- "$raw" | python3 "$SHARED/candidates.py" --seen "$DIR/seen.txt" \
    --min-seconds "$min_seconds" --duration-filter yes --format human
  exit $?
fi

print -r -- "$raw" | python3 "$SHARED/candidates.py" --seen "$DIR/seen.txt" --min-seconds "$min_seconds" \
  --duration-filter yes --fill-dates --format ids --pending "$DIR/work/pending.json" > work/queue_ids.txt
queue_status=$?
if (( queue_status != 0 )); then
  echo "ERROR: could not build the list of new videos"
  podcast_notify "$SHOW_NAME" "Could not build the list of new videos. See logs/check.log"
  exit 1
fi
ids=()
while IFS= read -r id; do
  [[ -n $id ]] && ids+=("$id")
done < work/queue_ids.txt
echo "new videos: ${#ids[@]}"
(( ${#ids[@]} == 0 )) && { echo "OK: nothing waiting"; exit 0; }

python3 "$SHARED/plan.py" --show-dir "$DIR" --pending "$DIR/work/pending.json" \
  || echo "WARN: episode numbers could not be planned; each new episode uses the next free number"
limit=$(python3 "$SHARED/queue.py" --backlog ${#ids[@]} --max ${MAX_PER_RUN:-2} --catch-up ${CATCH_UP:-1} --catch-up-max ${CATCH_UP_MAX:-25})
echo "this run publishes up to $limit (catch_up=${CATCH_UP:-1}, max_per_run=${MAX_PER_RUN:-2})"

done_count=0
published=()
failed=()
fallbacks=()
auth_needed=0
for id in $ids; do
  (( done_count >= limit )) && break
  echo "-- $id"
  python3 publish.py fetch "$id" > "work/fetch_$id.log" 2>&1
  code=$?
  if (( code != 0 )); then
    echo "fetch failed ($code): $(tail -c 300 work/fetch_$id.log)"
    # Exit 3 means the premiere is not ready yet. That is not a failure of this video.
    if (( code != 3 )); then
      failed+=("$id")
    fi
    continue
  fi
  if python3 "$SHARED/shownotes.py" --show-dir "$DIR" --video "$id" --mode "$MODE"; then
    print -r -- "$id" >> seen.txt
    info=$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("Ep %s (%s): %s" % (r.get("episode", "?"), r.get("status"), r.get("title")))' "work/$id/result.json")
    podcast_notify "$SHOW_NAME" "$info"
    [[ -f work/$id/basic_notes ]] && fallbacks+=("$id")
    [[ -f work/$id/auth_needed ]] && auth_needed=1
    rm -f "work/$id/audio.m4a"   # the copy on the website is the one that counts
    published+=("$id")
    done_count=$((done_count + 1))
  else
    # After 3 failed tries, stop retrying this video so it does not cost a Claude run every hour.
    print -r -- "$id" >> fails.txt
    if (( $(grep -cxF -- "$id" fails.txt) >= 3 )); then
      print -r -- "$id" >> seen.txt
      podcast_notify "$SHOW_NAME: gave up" "Video $id failed 3 times. See logs/check.log"
    else
      podcast_notify "$SHOW_NAME: will retry" "Video $id was not published. See logs/check.log"
    fi
    failed+=("$id")
  fi
done

if (( auth_needed )); then
  podcast_notify "$SHOW_NAME: Claude login needed" "Episodes still publish, with simpler show notes. Run: claude setup-token"
fi
if (( ${#published} == 0 && ${#failed} == 0 )); then
  echo "OK: nothing published this run"
  exit 0
fi
python3 "$SHARED/report.py" --published "${(j:,:)published}" --failed "${(j:,:)failed}" --fallback "${(j:,:)fallbacks}"
code=$?
if (( code != 0 )); then
  podcast_notify "$SHOW_NAME: check failed" "See the ERROR line in logs/check.log"
fi
exit $code
