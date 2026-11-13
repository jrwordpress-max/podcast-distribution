"""Daily podcast play numbers for Block Talks, written to the Google Sheet.

  python3 metrics.py            collect today's numbers and update the sheet
  python3 metrics.py --dry-run  collect and print, without touching the sheet

Sources:
  total plays     Seriously Simple Stats table on theblockopedia.com (since 21 Oct 2026)
  plays by app    tbp_podcast_plays table, filled by the site snippet site/tbp-podcast-play-log.php
                  (since 23 Oct 2026; one play per listener, episode and app per 24 hours)
  OP3 downloads   op3.dev public API (independent, IAB-style counting)

The sheet is written through the Composio CLI (Google account the Google account connected in Composio).
"""
import datetime
import html
import json
import os
import sys
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
sys.path.insert(0, os.path.join(os.path.dirname(DIR), "shared"))
from publish import CFG, php  # noqa: E402  (shares config and the Novamira helper)
from podcastlib.composio_client import composio as _composio  # noqa: E402
from podcastlib.sources import call_with_retries  # noqa: E402

SHEET_ID = CFG["SHEET_ID"]
PODCAST_GUID = "9fc9fc1c-3b5b-564a-adca-da42442277e0"
OP3_TOKEN = "preview07ce"  # OP3's public read-only preview token
TODAY = datetime.date.today().isoformat()
# Fixed columns in the Daily metrics tab; every other app is added into "Other apps".
DAILY_APPS = ["Apple Podcasts", "Spotify", "Amazon Music", "Pocket Casts", "Castbox", "Podcast Addict", "Overcast", "Player FM"]
WEBSITE = ("Website player", "Website download", "Web browser")


# ---------- collect ----------

def site_stats():
    return php(r"""
global $wpdb; $t = $wpdb->prefix . 'ssp_stats'; $p = $wpdb->prefix . 'tbp_podcast_plays';
$week = time() - 7 * 86400; $week_dt = gmdate('Y-m-d H:i:s', $week);
$out = ['total' => (int) $wpdb->get_var("SELECT COUNT(*) FROM $t"),
        'unique' => (int) $wpdb->get_var("SELECT COUNT(DISTINCT ip_address) FROM $t"),
        'last7' => (int) $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $t WHERE date > %d", $week)),
        'platforms' => $wpdb->get_results($wpdb->prepare("SELECT platform, COUNT(*) plays, SUM(created > %s) plays7, COUNT(DISTINCT ip_hash) listeners FROM $p GROUP BY platform ORDER BY plays DESC", $week_dt), ARRAY_A),
        'tracked_since' => $wpdb->get_var("SELECT MIN(created) FROM $p"),
        'episodes' => []];
$counts = []; foreach ($wpdb->get_results("SELECT post_id, COUNT(*) c, SUM(date > $week) w FROM $t GROUP BY post_id", ARRAY_A) as $r) { $counts[$r['post_id']] = $r; }
$top = []; foreach ($wpdb->get_results("SELECT post_id, platform, COUNT(*) c FROM $p GROUP BY post_id, platform ORDER BY c DESC", ARRAY_A) as $r) { if (!isset($top[$r['post_id']])) { $top[$r['post_id']] = $r['platform'] . ' (' . $r['c'] . ')'; } }
foreach (get_posts(['post_type' => 'podcast', 'post_status' => 'publish', 'posts_per_page' => -1]) as $e) {
  $c = $counts[$e->ID] ?? ['c' => 0, 'w' => 0];
  $out['episodes'][] = ['ep' => (int) get_post_meta($e->ID, 'itunes_episode_number', true), 'title' => $e->post_title,
    'plays' => (int) $c['c'], 'plays7' => (int) $c['w'], 'top' => $top[$e->ID] ?? '', 'url' => get_permalink($e)];
}
return $out;
""")


def op3_downloads():
    show = json.load(urllib.request.urlopen(f"https://op3.dev/api/1/shows/{PODCAST_GUID}?token={OP3_TOKEN}", timeout=30))["showUuid"]
    total, cont = 0, None
    while True:
        url = f"https://op3.dev/api/1/downloads/show/{show}?token={OP3_TOKEN}&limit=20000&format=json"
        if cont:
            url += f"&continuationToken={cont}"
        d = json.load(urllib.request.urlopen(url, timeout=60))
        total += len(d.get("rows", []))
        cont = d.get("continuationToken")
        if not cont:
            return total


# ---------- Google Sheet (Composio CLI) ----------

def composio(slug, args):
    """Sheet call. Empty or non-JSON Composio output is retried, then raised."""
    os.makedirs(os.path.join(DIR, "work"), exist_ok=True)
    return _composio(slug, args, work_dir=os.path.join(DIR, "work"))


def write_sheet(site, op3):
    plat = {r["platform"]: {k: int(r[k] or 0) for k in ("plays", "plays7", "listeners")} for r in site["platforms"]}
    tracked = sum(p["plays"] for p in plat.values())
    since = (site.get("tracked_since") or TODAY)[:10]
    top_ep = max(site["episodes"], key=lambda e: e["plays"]) if site.get("episodes") else {"plays": 0, "title": "—"}
    top_app = max(plat.items(), key=lambda kv: kv[1]["plays"]) if plat else ("—", {"plays": 0})

    # Plays by platform: biggest first.
    by_platform = [["Platform", "Plays", "Plays last 7 days", "Unique listeners", "Share of plays"]]
    for name, p in sorted(plat.items(), key=lambda kv: -kv[1]["plays"]):
        by_platform.append([name, p["plays"], p["plays7"], p["listeners"], round(p["plays"] / tracked, 4) if tracked else 0])
    by_platform.append(["Total", tracked, sum(p["plays7"] for p in plat.values()), "", 1 if tracked else 0])
    notes = [["Notes"], [f"Counted per app since {since}. One play per listener, episode and app per 24 hours; bots are skipped."],
             ["Spotify and YouTube Music copy the audio to their own servers, so most of their plays only show in Spotify for Creators and YouTube Studio."],
             [f"Updated {TODAY}."]]

    # Daily metrics: one row per day (a re-run on the same day overwrites that day's row).
    col = composio("GOOGLESHEETS_VALUES_GET", {"spreadsheet_id": SHEET_ID, "range": "'Daily metrics'!A:A"}).get("values", [])
    dates = [r[0] if r else "" for r in col]
    row = dates.index(TODAY) + 1 if TODAY in dates else len(dates) + 1
    prev = row - 1
    delta = lambda c: f"={c}{row}-{c}{prev}" if prev > 1 else ""
    named = set(DAILY_APPS) | set(WEBSITE)
    op3_cell = "" if op3 is None else op3
    daily = [TODAY, site["total"], delta("B"), site["unique"], site["last7"], op3_cell, delta("F")]
    daily += [plat.get(a, {}).get("plays", 0) for a in DAILY_APPS]
    daily += [sum(plat.get(w, {}).get("plays", 0) for w in WEBSITE), sum(p["plays"] for n, p in plat.items() if n not in named)]
    daily_header = ["Date", "Total plays", "New plays since last day", "Unique listeners", "Plays last 7 days", "OP3 downloads",
                    "New OP3 downloads"] + DAILY_APPS + ["Website", "Other apps"]

    episodes = [["Ep", "Title", "Total plays", "Plays last 7 days", "Top platform (plays)", "Episode page"]]
    for e in sorted(site["episodes"], key=lambda e: -e["ep"]):
        episodes.append([e["ep"], html.unescape(e["title"]), e["plays"], e["plays7"], e["top"], e["url"]])

    for rng in ("'Plays by platform'!A:G", "Episodes!A:H"):
        composio("GOOGLESHEETS_CLEAR_VALUES", {"spreadsheet_id": SHEET_ID, "range": rng})
    composio("GOOGLESHEETS_UPDATE_VALUES_BATCH", {"spreadsheet_id": SHEET_ID, "valueInputOption": "USER_ENTERED", "data": [
        {"range": f"'Plays by platform'!A1:E{len(by_platform)}", "values": by_platform},
        {"range": "'Plays by platform'!G1:G4", "values": notes},
        {"range": "'Daily metrics'!A1:Q1", "values": [daily_header]},
        {"range": f"'Daily metrics'!A{row}:Q{row}", "values": [daily]},
        {"range": f"Episodes!A1:F{len(episodes)}", "values": episodes},
        {"range": "Summary!A2", "values": [[f"Platform counts update from the Platforms tab. Play numbers update every day at 11:30; last update {TODAY}."]]},
        {"range": "Summary!A29:C41", "values": [
            ["PODCAST PLAYS", "Count", "Notes"],
            ["Total plays (since 21 Oct)", site["total"], "All apps and the website; Seriously Simple Stats; includes our own test plays"],
            ["Unique listeners", site["unique"], "Counted by IP address"],
            ["Plays in the last 7 days", site["last7"], ""],
            [f"Plays counted by app (since {since})", tracked, "Full split in the Plays by platform tab"],
            ["Top platform", top_app[1]["plays"], top_app[0]],
            ["Most played episode", top_ep["plays"], html.unescape(top_ep["title"])],
            ["OP3 independent downloads", op3_cell, "IAB-style count from op3.dev" if op3 is not None else "Unavailable this run; the other numbers were still written"],
            ["", "", ""], ["", "", ""], ["", "", ""], ["", "", ""], ["", "", ""]]},
    ]})
    return row


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        site = call_with_retries(site_stats)
    except Exception as exc:
        print("ERROR: site stats failed: %s" % exc)
        return 1
    op3 = None
    try:
        op3 = call_with_retries(op3_downloads)
    except Exception as exc:
        # OP3 is an extra count. The sheet still updates from the site.
        print("WARN: OP3 downloads failed: %s" % exc)
    print(json.dumps({"date": TODAY, "plays": site["total"], "unique": site["unique"], "last7": site["last7"],
                      "op3": op3, "by_platform": {r["platform"]: int(r["plays"]) for r in site["platforms"]}}))
    if "--dry-run" not in argv:
        try:
            print("wrote Daily metrics row", write_sheet(site, op3))
        except Exception as exc:
            print("ERROR: sheet update failed: %s" % exc)
            return 1
    if op3 is None:
        print("WARN: completed with OP3 unavailable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
