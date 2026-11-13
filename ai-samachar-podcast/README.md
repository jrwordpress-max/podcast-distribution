# AI Samachar – Audio Podcast

Standalone project: daily audio distribution of AI Samachar (Rankkking) to podcast platforms.

- Tracker: a Google Sheet (its ID goes in `config.env` as `SHEET_ID`); same layout as Block Talks, updated daily at 12:30.

## How it runs (since 11 Nov 2026)

Every hour this Mac checks the YouTube playlist "AI Samachar: Daily AI News (Hinglish)" on @Rankkking.
For each new full episode (Shorts under 3 minutes are skipped) it downloads the audio, has Claude
write the show notes, and publishes the episode on podcast.rankkking.com in the "AI Samachar by
Rankkking" series. Podcast apps pick it up from the feed:

https://podcast.rankkking.com/feed/podcast/ai-samachar/

The site's default feed (`/feed/podcast/podcast-rankkking-com/`) still redirects to Block Talks on
theblockopedia.com. AI Samachar never uses it; leave its redirect on.

| File | What it does |
| --- | --- |
| `config.env` | Settings: playlist, minimum length, series, feed, cover, `MODE` (publish or draft), most videos per check. |
| `check.sh` | The hourly check. Run it by hand any time: `./check.sh`; `./check.sh --list` only lists what is waiting. |
| `publish.py` | Downloads one video's audio and creates its episode. |
| `nmrest.py` | Talks to the site (Novamira abilities over the WordPress REST API). |
| `.wp.env` | The site's application password. Private file; never share or commit it. |
| `prompt.md` | Instructions Claude follows to write the show notes. |
| `seen.txt` / `fails.txt` | Videos already handled / failed; after 3 failures a video is skipped. |
| `logs/check.log` | What each check did. |
| `com.rankkking.ai-samachar-check.plist` | The hourly schedule (launchd). |
| `daily.sh` + `com.rankkking.ai-samachar-sheet.plist` | Daily at 12:30: `metrics.py` (plays, OP3), `episode_links.py` (Episode links tab), `platforms.py` (Platforms checks, Episode matrix) into the tracker sheet. Log: `logs/metrics.log`. |
| `site/podcast-play-log.php` | Copy of the site snippet (mu-plugin) that records which app each play comes from. |

Show notes are written by Claude (`claude -p` with `prompt.md`). Put a long-lived token in
`secrets.env` as `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or set `ANTHROPIC_API_KEY`.
If neither works, `check.sh` still publishes the episode, with show notes built from the YouTube
description, and a notification says the login needs refreshing. A failed check exits non-zero;
the summary is the last lines of `logs/check.log`. See the repo README for the server, GitHub
Actions, and the full secret list. `CATCH_UP=1` publishes a backlog in one run (up to `CATCH_UP_MAX`).

On the site, `wp-content/mu-plugins/podcast-m4a-mime.php` (copy in `site/`) makes WordPress label .m4a
audio as `audio/x-m4a`, and `wp-content/uploads/.htaccess` serves it as `audio/mp4`. Without them the
feed calls the audio MP3 and some apps refuse it.

Turn the schedule on:

```bash
cp ~/Claude/ai-samachar-podcast/com.rankkking.ai-samachar-check.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.rankkking.ai-samachar-check.plist
```

Off:

```bash
launchctl unload ~/Library/LaunchAgents/com.rankkking.ai-samachar-check.plist
```

When the show goes live on an app, fill its ID or page in at the top of `episode_links.py`
(and `PI_FEED_ID` in `platforms.py` for Podcast Index), and set its Status to Published in the
Platforms tab. From then on its episode links and daily checks fill in by themselves.

## Tools
- ffmpeg (no Homebrew on this Mac): /Users/YOUR_USER/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1 (from `pip install --user imageio-ffmpeg`)
- Loudness check: `ffmpeg -i file.mp3 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=summary -f null -`

## Status
- 11 Nov 2026 (night): Spotify live. Podcast Guru (found on its own, `GURU_PAGE` filled in) and Player FM (https://player.fm/series/ai-samachar-by-rankkking) live. Anghami submitted (podcast id 10252). Still to do, each needs a team login in Chrome: Amazon Music (feed entered, sign-in pending), TuneIn, Goodpods, Deezer (blank page from India); Castbox once Apple lists the show; Apple retry on 12 Nov; YouTube Music playlist by the channel owner.
- 11 Nov 2026 (evening): Spotify submitted through Spotify for Creators (the feed owner email): https://open.spotify.com/show/3EKJcjxah5UoJrOQ6QIAfY (shows up within a few hours). Podverse picked the show up from Podcast Index: https://podverse.fm/podcast/JAxT8B5Xy- (IDs filled in `episode_links.py`). Apple: Apple ID and Podcasts Connect account made, but Add Show failed 3 times with Apple's "Unexpected error creating show from feed" (HTTP 500); the feed checks out, so try again on 12 Nov and contact Apple if it persists. Amazon Music / Audible, YouTube Music and the other login apps are still to do.
- 11 Nov 2026: series "AI Samachar by Rankkking" created on podcast.rankkking.com (new feed and podcast:guid 319f1aba-352b-572d-8e80-29f49bc77788), Episodes 1–7 (5–11 Nov) published, hourly check on. Submitted the same day: Pocket Casts (https://pca.st/g53ud8yo) and Podcast Addict (https://podcastaddict.com/podcast/ai-samachar-by-rankkking/7364334) live; Podcast Index live (https://podcastindex.org/podcast/8110881); Listen Notes not submitted (it accepts only human-recorded audio, AI Samachar uses an AI voice).
- Phase 0 (2 Nov 2026): folder, tracker, ffmpeg done. EP5 audio: -16.0 LUFS, -1.2 dBTP true peak, 5:39, MP3 128 kbps mono 44.1 kHz – pass.
