# Block Talks auto-publish

Once a day at 11:00 this Mac checks the Block Talks YouTube playlist and the channel's latest
uploads. For each new video it downloads the audio, has Claude write the SEO title, description
and chapters, and creates the podcast episode on theblockopedia.com through Novamira. From the
RSS feed the episode reaches Apple, Spotify, Amazon and the other platforms on its own.

A channel upload is picked up without being added to the playlist when its title contains
"TBP Podcast", it runs at least 5 minutes (so short "TBP Interview" clips are left out) and it
was uploaded on or after 19 Oct 2026. These rules are in `config.env`.

To see which videos are waiting, without publishing anything: `./check.sh --list`

## Files

| File | What it does |
| --- | --- |
| `config.env` | Settings. `MODE=draft` saves new episodes as drafts; `MODE=publish` puts them live. The channel rules (`CHANNEL_MATCH`, `MIN_MINUTES`, `CHANNEL_SINCE`) are here too. |
| `check.sh` | The daily check. Run it by hand any time: `./check.sh`; `./check.sh --list` only lists what is waiting |
| `publish.py` | Downloads one video's audio and creates its episode. |
| `daily.sh` | The 11:30 sheet update: runs `metrics.py`, `episode_links.py` and `platforms.py` in that order. A step that fails is tried again up to 2 more times, 5 minutes apart. Run it by hand any time: `./daily.sh` |
| `metrics.py` | Podcast plays (total and by app) and OP3 downloads into the Google Sheet (Summary, Plays by platform, Daily metrics, Episodes tabs). |
| `episode_links.py` | Finds each new episode's page on every app it can reach and rewrites the Episode links tab. Found links are kept in `work/episode_links.json`; Amazon Music, Podcast Index and Podchaser links for new episodes are added there by hand. |
| `platforms.py` | Checks the 11 apps that show our show without a browser (Apple, Spotify, Podcast Index, Pocket Casts, TuneIn, Castbox, Deezer, Podverse, Podcast Guru, TrueFans, Castro) and fills "Last checked" and "Link opens today?" in the Platforms tab. It also fills column J, "Episodes the app shows (today)", as a count against the feed (for example 23/34) for Apple, Podverse, TrueFans and fyyd, and gives the ~70 automatic rows today's date, "Via Podcast Index" or "Via Apple catalogue", and that source's count. Podcast Index's own count needs a free API key (`PI_API_KEY` and `PI_API_SECRET` in config.env); without it Podverse, which copies Podcast Index, stands in. Then rebuilds the Episode matrix tab, adding a row for each new episode. The Platforms tab's Status column stays a check by hand: Audible, Listen Notes, Fountain, YouTube Music and the apps without a web page cannot be read by a script. |
| `site/tbp-podcast-play-log.php` | Copy of the website snippet that records which app each play comes from. |
| `prompt.md` | Instructions Claude follows to write the SEO copy. |
| `seen.txt` | YouTube IDs already handled. Delete a line to have that video processed again. |
| `skip.txt` | Matching channel uploads older than `CHANNEL_SINCE`, so their date is looked up only once. |
| `fails.txt` | Videos that failed; after 3 failures a video is skipped. |
| `logs/check.log` | What each check did. |
| `work/<video id>/` | Each video's details, SEO copy (`spec.json`) and result. |
| `reference/` | The scripts used for the first 23 episodes. |

## Turn the schedule on or off

On:

```bash
cp ~/Claude/blockopedia-podcast/com.blockopedia.podcast-check.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.blockopedia.podcast-check.plist
```

Off:

```bash
launchctl unload ~/Library/LaunchAgents/com.blockopedia.podcast-check.plist
```

The daily sheet job is `com.blockopedia.podcast-metrics.plist` (it runs `daily.sh`); turn it on or off the same way. Its log is `logs/metrics.log`.

## When something goes wrong

- A notification says "will retry" or "gave up": read the last lines of `logs/check.log`.
- A notification says the numbers, episode links or platform checks "were not updated": all 3 tries failed; read the last lines of `logs/metrics.log`, then run `./daily.sh` by hand.
- A draft looks wrong: fix it in wp-admin › Podcast before publishing.
- The Mac was off: nothing is lost; the next check picks up every video it missed.
