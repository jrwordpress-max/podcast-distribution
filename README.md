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
  episode on the site through Novamira (WordPress abilities).
- `daily.sh` runs `metrics.py` (plays from the site and OP3), `episode_links.py` (each episode's
  page on every app) and `platforms.py` (daily live checks and the episode matrix), and writes them
  to the tracker sheet through the Composio CLI.
- `site/` holds the small WordPress mu-plugins the site needs (play logging, m4a MIME type).

## Setup

1. Install `yt-dlp`, `ffmpeg`, Python 3, Claude Code and the Composio CLI.
2. Fill in `config.env` (playlist, site, feed, `SHEET_ID` of your tracker sheet).
3. AI Samachar only: create `.wp.env` with `WP_API_USERNAME` and `WP_API_PASSWORD`
   (a WordPress application password). It is git-ignored; never commit it.
4. Copy the `.plist` files to `~/Library/LaunchAgents/`, replace `/Users/YOUR_USER/` with your
   home folder, and load them with `launchctl load`.

Not in this repository: credentials, downloaded audio (`work/`), logs, and the lists of videos
already handled (`seen.txt`, `fails.txt`, `skip.txt`).
