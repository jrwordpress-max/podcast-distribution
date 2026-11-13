"""Daily update of the Platforms tab's live checks and of the Episode matrix tab.

  python3 platforms.py            check the apps and rewrite both tabs
  python3 platforms.py --dry-run  check the apps and print the result, without touching the sheet

Platforms tab: for each app we can check without a browser, "Link opens today?" becomes Yes
when the app returns our show today (No when it does not), and "Last checked" becomes today.
Apps that block plain requests (Amazon Music, Podcast Addict, Player FM, Podchaser, Anghami,
Metacast, Podlink) or have no web page keep their last values. The Status column is never changed here: moving
an app to Published stays a check by hand.

Column J ("Episodes the app shows") holds how many episodes an app lists today against the feed,
for the apps that can be counted without a browser. The ~70 automatic apps get the Podcast Index
count (through Podverse when no Podcast Index API key is set), and their "Last checked" moves to
today with "Via Podcast Index" / "Via Apple catalogue", since that source is what they read.

Episode matrix tab: one row per episode in the feed, one column per app, rebuilt every day from
the Platforms tab's status and the Episode links tab's links:
  ✓  the Episode links tab has this episode's page on this app (the website always counts)
  ✗  the app is one we find episode pages on and this episode is not there yet, or "Not found yet"
  ◐  the app is live but we cannot see single episodes there, or it is automatic and unchecked
  ⏳ submitted, under review   🔒 login required   — not available to us
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import episode_links as el  # noqa: E402  (collectors, feed reader, sheet helpers)
from metrics import composio, SHEET_ID, TODAY  # noqa: E402

MATRIX = "Episode matrix"
MATRIX_SHEET_ID = 1583476833
FIRST_ROW = 5  # first episode row in the Episode matrix tab
WEBSITE_HEADER = "Website (theblockopedia.com)"

# Apps whose own page or API shows our show without a browser. The collectors are the ones
# episode_links.py already uses; a page check needs a 200 answer that names the show.
# Amazon Music is left out: its page often comes back as an empty app shell without the show.
PAGE_CHECKS = {"Podcast Index": "https://podcastindex.org/podcast/8081068"}
PI_FEED_ID = 8081068      # our Podcast Index record
PI_OLD_FEED_ID = 8079171  # old duplicate ("Blockopedia Podcast", rankkking feed URL)


def check(platform):
    """True when the app shows our show today, False when it does not, None when we cannot tell."""
    try:
        if platform in el.COLLECTORS:
            return len(el.COLLECTORS[platform]()) > 0
        if platform in PAGE_CHECKS:
            return bool(re.search(r"Blockopedia|Block Talks", el.get(PAGE_CHECKS[platform])))
    except Exception as ex:  # a timeout or a block is a failed check, not proof the show is gone
        print(f"{platform}: {type(ex).__name__}: {str(ex)[:120]}")
        return False
    return None


# ---------- episode counts (column J, "Episodes the app shows") ----------
# The ~70 "automatic" apps have no page we can open; they show what Podcast Index holds. Podcast
# Index's own API needs a free key (PI_API_KEY and PI_API_SECRET in config.env); without one,
# Podverse stands in, because it copies its episode list from Podcast Index.

def pi_api(path):
    key, secret = el.CFG.get("PI_API_KEY"), el.CFG.get("PI_API_SECRET")
    if not key or not secret:
        return None
    now = str(int(time.time()))
    req = urllib.request.Request("https://api.podcastindex.org/api/1.0/" + path, headers={
        "User-Agent": "BlockTalksPublisher/1.0", "X-Auth-Key": key, "X-Auth-Date": now,
        "Authorization": hashlib.sha1((key + secret + now).encode()).hexdigest()})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def truefans_count():
    m = re.search(r'"episodeCount":(\d+)', el.get(el.TRUEFANS_PAGE))
    return int(m.group(1)) if m else None


def fyyd_count():
    """Episodes fyyd lists for our show; 0 when fyyd does not list the show at all."""
    q = urllib.parse.quote("Blockopedia")
    d = json.loads(el.get(f"https://api.fyyd.de/0.2/search/podcast?term={q}"))
    shows = [x for x in d.get("data") or [] if "blockopedia" in (x.get("title") or "").lower()]
    return max((int(x.get("episode_count") or 0) for x in shows), default=0)


def episode_counts():
    """{name: number of episodes the app shows today, or None when the check failed}."""
    out = {}

    def run(name, fn):
        try:
            out[name] = fn()
        except Exception as ex:  # one blocked app must not stop the others
            print(f"count {name}: {type(ex).__name__}: {str(ex)[:120]}")
            out[name] = None

    run("Podcast Index", lambda: (pi_api(f"podcasts/byfeedid?id={PI_FEED_ID}") or {}).get("feed", {}).get("episodeCount"))
    run("Podverse", lambda: len(el.podverse()))
    run("Apple Podcasts", lambda: len(el.apple()))
    run("TrueFans", truefans_count)
    run("fyyd", fyyd_count)
    return out


def count_updates(rows, counts, n_feed):
    """Column J for every row we can say something about, plus Last checked / Link opens today? for
    the automatic rows (they have no page of their own, so the source's count is what we can check)."""
    index = counts.get("Podcast Index")
    via = "Podcast Index" if index is not None else "Podverse"
    index = index if index is not None else counts.get("Podverse")
    frac = lambda n: f"{n}/{n_feed}" if n is not None else "check failed"
    j, hi = {}, {}
    for i, row in enumerate(rows):
        row = row + [""] * (9 - len(row))
        name, how, status, r = row[1], row[2], row[3], i + 2
        if name == "fyyd":
            n = counts.get("fyyd")
            j[r] = "Not listed yet" if n == 0 else frac(n)
        elif name in counts and name != "Podcast Index":
            j[r] = frac(counts[name])
        elif name == "Podcast Index":
            j[r] = f"{frac(index)} (via {via})" if via != "Podcast Index" else frac(index)
        elif status.startswith("Auto") and "Apple" in how:
            j[r] = f"Apple {frac(counts.get('Apple Podcasts'))}"
        elif status.startswith("Auto"):
            j[r] = f"Podcast Index {frac(index)}"
        if status.startswith("Auto"):
            hi[r] = [TODAY, "Via Apple catalogue" if "Apple" in how else "Via Podcast Index"]
    return j, hi


def read(ranges):
    d = composio("GOOGLESHEETS_BATCH_GET", {"spreadsheet_id": SHEET_ID, "ranges": ranges, "valueRenderOption": "FORMATTED_VALUE"})
    return [vr.get("values", []) for vr in d["valueRanges"]]


def platform_updates(rows):
    """Rows of the Platforms tab (header excluded) -> {sheet row: [Last checked, Link opens today?]}."""
    updates, report = {}, {}
    for i, row in enumerate(rows):
        row = row + [""] * (9 - len(row))
        name = row[1]
        if not name.strip():
            continue
        ok = check(name)
        if ok is None:
            continue
        # A failed check is tried once more, so one slow answer does not mark an app down.
        if not ok:
            ok = check(name)
        report[name] = "Yes" if ok else "No"
        updates[i + 2] = [TODAY, "Yes" if ok else "No – not found today"]
    return updates, report


def symbol(header, n, status, state):
    if header == WEBSITE_HEADER:
        return "✓"
    if header in el.PLATFORMS:  # apps whose episode pages we collect
        if str(n) in state.get(header, {}):
            return "✓"
        if status.startswith("Published") or status == "Not found yet":
            return "✗"
    if status.startswith("Published") or status.startswith("Auto"):
        return "◐"
    if status.startswith("Submitted"):
        return "⏳"
    if status == "Login required":
        return "🔒"
    if status == "Not available":
        return "—"
    if status == "Not found yet":
        return "✗"
    return ""


def write_matrix(eps, statuses, state, matrix):
    header = matrix[3]
    last = el.col(len(header) - 1)
    have = sum(1 for r in matrix[FIRST_ROW - 1:] if r and str(r[0]).startswith("Ep "))
    n_eps = len(eps)
    # Keep the tab's formatting: new episode rows are inserted above the total row and copy the
    # look of the episode row above them; rows for episodes no longer in the feed are removed.
    if n_eps > have:
        composio("GOOGLESHEETS_INSERT_DIMENSION", {"spreadsheet_id": SHEET_ID, "insert_dimension": {
            "range": {"sheet_id": MATRIX_SHEET_ID, "dimension": "ROWS", "start_index": FIRST_ROW - 1 + have,
                      "end_index": FIRST_ROW - 1 + n_eps}, "inherit_from_before": True}})
    elif n_eps < have:
        composio("GOOGLESHEETS_DELETE_DIMENSION", {"spreadsheet_id": SHEET_ID, "delete_dimension_request": {
            "range": {"sheet_id": MATRIX_SHEET_ID, "dimension": "ROWS", "start_index": FIRST_ROW - 1 + n_eps,
                      "end_index": FIRST_ROW - 1 + have}}})
    end = FIRST_ROW + n_eps - 1
    rows = []
    for i, e in enumerate(eps):
        r = FIRST_ROW + i
        rows.append([f"Ep {e['n']}", e["title"], f'=COUNTIF(D{r}:{last}{r},"✓")']
                    + [symbol(h, e["n"], statuses.get(h, ""), state) for h in header[3:]])
    total = ["", "Episodes live on platform  ·  TOTAL →", f"=SUM(C{FIRST_ROW}:C{end})"] + \
            [f'=COUNTIF({el.col(j)}{FIRST_ROW}:{el.col(j)}{end},"✓")&" / {n_eps}"' for j in range(3, len(header))]
    legend = (matrix[1][0] if len(matrix) > 1 and matrix[1] else "").split("  ·  ")[0]
    day = datetime.date.fromisoformat(TODAY).strftime("%-d %b %Y")
    composio("GOOGLESHEETS_UPDATE_VALUES_BATCH", {"spreadsheet_id": SHEET_ID, "valueInputOption": "USER_ENTERED", "data": [
        {"range": f"'{MATRIX}'!A2", "values": [[f"{legend}  ·  Updated {day} from the Platforms and Episode links tabs"]]},
        {"range": f"'{MATRIX}'!A{FIRST_ROW}:{last}{end + 1}", "values": rows + [total]}]})


def main():
    platform_rows, matrix = read(["Platforms!A2:I", f"'{MATRIX}'!A1:{el.col(109)}"])
    updates, report = platform_updates(platform_rows)
    statuses = {r[1]: (r[3] if len(r) > 3 else "") for r in platform_rows if len(r) > 1}
    eps = el.feed_episodes()
    state = json.load(open(el.STATE)) if os.path.exists(el.STATE) else {}
    counts = episode_counts()
    j_col, auto_hi = count_updates(platform_rows, counts, len(eps))
    print(json.dumps({"date": TODAY, "checked": report, "episodes": len(eps), "counts": counts}))
    if "--dry-run" in sys.argv:
        return
    for r, v in auto_hi.items():
        updates.setdefault(r, v)
    data = [{"range": f"Platforms!H{r}:I{r}", "values": [v]} for r, v in sorted(updates.items())]
    data += [{"range": "Platforms!J1", "values": [["Episodes the app shows (today)"]]}]
    data += [{"range": f"Platforms!J{r}", "values": [[v]]} for r, v in sorted(j_col.items())]
    composio("GOOGLESHEETS_UPDATE_VALUES_BATCH", {"spreadsheet_id": SHEET_ID, "valueInputOption": "USER_ENTERED", "data": data})
    write_matrix(eps, statuses, state, matrix)
    print(f"wrote {len(updates)} platform checks and {len(eps)} Episode matrix rows")


if __name__ == "__main__":
    main()
