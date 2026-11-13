# Podcast distribution: Block Talks and AI Samachar

Two small automations that turn YouTube videos into podcast episodes on a WordPress site
(Seriously Simple Podcasting), so every podcast app picks them up from the RSS feed, and that
keep a Google Sheet tracker of where each show is live and how often it is played.

| Folder | Show | Feed |
| --- | --- | --- |
| `blockopedia-podcast/` | Block Talks by The Blockopedia (crypto and Web3 interviews) | https://theblockopedia.com/feed/podcast/the-blockopedia/ |
| `ai-samachar-podcast/` | AI Samachar by Rankkking (daily AI news in Hinglish) | https://podcast.rankkking.com/feed/podcast/ai-samachar/ |

Each folder has its own README with the details. In short:

- `check.sh` (launchd, hourly or daily) lists new videos with `yt-dlp`, downloads the audio,
  has Claude Code (`claude -p` with `prompt.md`) write the show notes, and `publish.py` creates the
  episode on the site through Novamira (WordPress abilities). If Claude cannot log in, the episode
  still publishes, with show notes taken from the YouTube description.
- `daily.sh` runs `metrics.py` (plays from the site and OP3), `episode_links.py` (each episode's
  page on every app) and `platforms.py` (daily live checks and the episode matrix), and writes them
  to the tracker sheet through the Composio CLI. One source failing does not drop the rest of the sheet.
- `site/` holds the small WordPress mu-plugins the site needs (play logging, m4a MIME type).
- `shared/` is the code both shows use (Claude login, upload, episode numbers, sheet retries, alerts).

## Setup on the Mac (launchd)

The `.plist` files are unchanged. After `git pull`, the jobs you already loaded keep running.

1. Install `yt-dlp`, `ffmpeg`, Python 3, Claude Code and the Composio CLI.
2. Fill in `config.env` (playlist, site, feed, `SHEET_ID` of your tracker sheet).
   Block Talks defaults to `MODE=publish`. Set `MODE=draft` if a show should wait in wp-admin.
   `CATCH_UP=1` publishes a backlog in one run, up to `CATCH_UP_MAX` (25). `CATCH_UP=0` keeps
   the old cap of `MAX_PER_RUN` (2 for Block Talks, 6 for AI Samachar).
3. AI Samachar: create `.wp.env` with `WP_API_USERNAME` and `WP_API_PASSWORD`
   (a WordPress application password). It is git-ignored; never commit it.
   Block Talks on the Mac keeps using the `novamira` CLI and its saved site login.
4. Claude, once, so a later expired Mac login does not force basic show notes:
   ```bash
   claude setup-token
   ```
   The command prints a token and does not save it. Put it in `secrets.env` at the repo root
   (or in a show folder), `chmod 600`, and do not commit it:
   ```bash
   CLAUDE_CODE_OAUTH_TOKEN=the-token-from-setup-token
   ```
   `ANTHROPIC_API_KEY` in the same file is optional. It is used when the CLI cannot log in.
   `secrets.env.example` lists every secret. Anything already exported in the environment
   wins over the file.
5. Copy the `.plist` files to `~/Library/LaunchAgents/` the first time only, replace
   `/Users/YOUR_USER/` with your home folder, and load them with `launchctl load`.
   A Mac that is already loaded does not need this again.

Notifications on the Mac are still macOS notifications (`osascript`). Set `NOTIFY_HOOK` or
`SLACK_WEBHOOK_URL` in `secrets.env` to also send them somewhere else. `NOTIFY_HOOK` is a zsh
snippet; `$TITLE` and `$BODY` are the message.

A failed check or sheet update exits non-zero. The last lines of `logs/check.log` or
`logs/metrics.log` are a short summary (`ERROR:` or `OK:`). launchd keeps scheduling the next run.

Not in this repository: credentials, downloaded audio (`work/`), logs, and the lists of videos
already handled (`seen.txt`, `fails.txt`, `skip.txt`).

## Same jobs on a server or GitHub Actions

launchd is still the Mac path. These two are extra.

**Always-on server.** Copy the repo to `/opt/podcast-distribution` (or edit the paths), install
`zsh`, `ffmpeg`, `yt-dlp`, Python 3, and the Composio CLI. Put secrets in
`/opt/podcast-distribution/secrets.env`. For Block Talks set `WP_API_USERNAME` and
`WP_API_PASSWORD` (an application password); the server has no `novamira` login unless you
install the CLI and log it in there. Set the server timezone to the Mac's timezone so the
11:00, 11:30 and 12:30 timers match the plists, then:

```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now block-talks-check.timer block-talks-daily.timer \
  ai-samachar-check.timer ai-samachar-daily.timer
```

`Persistent=true` runs a timer that was missed while the machine was off. `check.sh` then
publishes the videos that were missed, oldest upload date first.

**GitHub Actions.** `.github/workflows/podcast.yml` runs the same scripts. Schedules are UTC
and assume the Mac's clock is India Standard Time: AI Samachar check every hour at :15,
Block Talks check 05:30 UTC (11:00 IST), Block Talks sheet 06:00 UTC (11:30 IST), AI Samachar
sheet 07:00 UTC (12:30 IST). Actions can start late. Run one job by hand from the Actions tab
(`workflow_dispatch`). The workflow also runs the unit tests on pull requests.

Add these repository secrets (Actions → Secrets). None of them belong in git:

| Secret | Used for |
| --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude CLI on the runner (`claude setup-token`) |
| `ANTHROPIC_API_KEY` | Show notes if the CLI cannot log in |
| `AI_SAMACHAR_WP_USER` / `AI_SAMACHAR_WP_PASSWORD` | podcast.rankkking.com application password |
| `BLOCK_TALKS_WP_USER` / `BLOCK_TALKS_WP_PASSWORD` | theblockopedia.com application password |
| `AI_SAMACHAR_SHEET_ID` / `BLOCK_TALKS_SHEET_ID` | Tracker spreadsheets |
| `COMPOSIO_API_KEY` | Sheet writes. Also `COMPOSIO_ORG_ID` and `COMPOSIO_PROJECT_ID` for `composio login` |
| `PI_API_KEY` / `PI_API_SECRET` | Optional Podcast Index counts |
| `SLACK_WEBHOOK_URL` or `NOTIFY_HOOK` | Optional failure alerts |

Optional repository variables: `PODCAST_MODE` (`draft` or `publish`; empty uses `config.env`)
and `ANTHROPIC_MODEL` (default `claude-sonnet-4-5`).

`seen.txt` is cached between Actions runs. Each check also asks the site which YouTube ids
already have an episode, so a cold cache does not create a second post for the same video.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
