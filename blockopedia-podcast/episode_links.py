"""Daily update of the 'Episode links' tab: one live link per episode per app.

  python3 episode_links.py            find new links and rewrite the tab
  python3 episode_links.py --dry-run  find new links and print them, without touching the sheet

Links found once are kept in work/episode_links.json and never removed, so a page that is
slow or blocked on one day does not erase anything. Each run only adds what is missing.

Found automatically (no browser): our website, Apple Podcasts, Podverse, TuneIn, Castro,
Pocket Casts, Deezer, Spotify and TrueFans (newest episode), Castbox and Podcast Guru (newest 5),
Podcast Addict (built from the audio URL once the episode is a day old).
Amazon Music, Podcast Index and Podchaser block plain requests; their links for new episodes
are added by hand to work/episode_links.json (open the show page in a browser).
"""
import datetime
import difflib
import email.utils
import gzip
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from publish import CFG  # noqa: E402
from metrics import composio, SHEET_ID, TODAY  # noqa: E402

FEED_URL = CFG.get("FEED_URL", "https://theblockopedia.com/feed/podcast/the-blockopedia/")
STATE = os.path.join(DIR, "work", "episode_links.json")
TAB = "Episode links"
TAB_SHEET_ID = 136040423
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"

# Column order in the tab. "Website" is shown as "Our website".
PLATFORMS = ["Website", "Apple Podcasts", "Spotify", "Amazon Music", "Podcast Index", "Pocket Casts", "Podcast Addict",
             "TuneIn", "Castbox", "Deezer", "Podverse", "Podcast Guru", "Castro", "Podchaser", "TrueFans"]
APPLE_ID = "6824908621"
SPOTIFY_ID = "5RiZ15buc1CFiSjw2cEHr7"
PODVERSE_ID = "jBo6LQ5YBK"
TUNEIN_ID = "p4851879"
TUNEIN_PAGE = "https://tunein.com/podcasts/Technology-Podcasts/Block-Talks-by-The-Blockopedia-Crypto--Web3-Podcast-p4851879/"
CASTRO_PAGE = "https://castro.fm/podcast/69455251-325e-481b-89e2-32e11d5f19cf"
POCKETCASTS_ID = "ebb21e00-aeaf-013f-bb96-02fff6700f3f"
DEEZER_PAGE = "https://www.deezer.com/en/show/1003686301"
CASTBOX_PAGE = "https://castbox.fm/channel/id7461651"
GURU_PAGE = "https://app.podcastguru.io/podcast/block-talks-by-the-blockopedia-crypto-web3-podcast-ec853c3faca9184ea62023f8684fc8b0"
PODCAST_ADDICT_ID = "7322525"
TRUEFANS_PAGE = "https://truefans.fm/blockopedia-podcast"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    res = urllib.request.urlopen(req, timeout=60)
    body = res.read()
    if res.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":  # Pocket Casts always gzips
        body = gzip.decompress(body)
    return body.decode("utf-8", "replace")


def feed_episodes():
    root = ET.fromstring(get(FEED_URL))
    eps = []
    for it in root.iter("item"):
        n = it.findtext(f"{{{ITUNES}}}episode")
        if not n:
            continue
        enc = it.find("enclosure")
        eps.append({"n": int(n), "title": html.unescape(it.findtext("title") or ""), "link": it.findtext("link") or "",
                    "audio": enc.get("url") if enc is not None else "",
                    "published": email.utils.parsedate_to_datetime(it.findtext("pubDate"))})
    return sorted(eps, key=lambda e: e["n"])


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(s or "").lower().replace("’", "'")).strip()


def episode_number(title, eps):
    """Match a title from another app to our episode number; None when unsure."""
    t, best = norm(title), (0.0, None)
    for e in eps:
        full, main = norm(e["title"]), norm(e["title"].split("|")[0])
        score = max(difflib.SequenceMatcher(None, t, full).ratio(), difflib.SequenceMatcher(None, t[:len(main)], main).ratio())
        if score > best[0]:
            best = (score, e["n"])
    return best[1] if best[0] >= 0.8 else None


# ---------- one collector per app: each returns [(title, url), ...] ----------

def apple():
    d = json.loads(get(f"https://itunes.apple.com/lookup?id={APPLE_ID}&entity=podcastEpisode&limit=300"))
    return [(x["trackName"], x["trackViewUrl"].split("&uo")[0]) for x in d["results"] if x.get("kind") == "podcast-episode"]


def podverse():
    out = []
    for page in range(1, 20):
        rows = json.loads(get(f"https://api.podverse.fm/api/v1/episode?podcastId={PODVERSE_ID}&sort=most-recent&page={page}"))[0]
        out += [(x["title"], "https://podverse.fm/episode/" + x["id"]) for x in rows]
        if len(rows) < 20:
            return out
    return out


def tunein():
    url = f"https://api.tunein.com/profiles/{TUNEIN_ID}/contents?formats=mp3,aac&partnerId=RadioTime&version=6"
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            g = str(o.get("GuideId", ""))
            if g.startswith("t") and o.get("Title") and g not in seen:
                seen.add(g)
                out.append((o["Title"], f"{TUNEIN_PAGE}?topicId={g[1:]}"))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    first = json.loads(get(url))
    walk(first)
    # The first page holds 20 episodes; the "free" filter link lists all of them.
    nxt = first.get("Items", [{}])[0].get("ContainerNavigation", {}).get("Url") if first.get("Items") else None
    for item in first.get("Items", []):
        nxt = (item.get("ContainerNavigation") or {}).get("Url") or nxt
    for _ in range(5):
        if not nxt:
            break
        d = json.loads(get(nxt))
        walk(d)
        nxt = (d.get("Paging") or {}).get("Next")
    return out


def castro():
    h = get(CASTRO_PAGE)
    return [(html.unescape(t.strip()), u) for u, t in
            re.findall(r'<a href="(https://castro.fm/episode/[^"]+)" class="episode-title-link">\s*(.*?)\s*</a>', h, re.S)]


def pocket_casts():
    d = json.loads(get(f"https://podcast-api.pocketcasts.com/podcast/full/{POCKETCASTS_ID}"))
    return [(x["title"], "https://pca.st/episode/" + x["uuid"]) for x in d["podcast"]["episodes"]]


def deezer():
    h = get(DEEZER_PAGE)
    pairs = re.findall(r'"EPISODE_ID":"(\d+)"(?:(?!"EPISODE_ID").){0,3000}?"EPISODE_TITLE":"((?:[^"\\]|\\.)*)"', h, re.S)
    return [(json.loads(f'"{t}"'), f"https://www.deezer.com/en/episode/{i}") for i, t in pairs]


def spotify():
    """Spotify's embed page shows only the newest episode; daily runs catch each one in turn."""
    h = get(f"https://open.spotify.com/embed/show/{SPOTIFY_ID}")
    data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))
    out = []

    def walk(o):
        if isinstance(o, dict):
            uri = str(o.get("uri", ""))
            if uri.startswith("spotify:episode:") and (o.get("name") or o.get("title")):
                out.append((o.get("name") or o.get("title"), "https://open.spotify.com/episode/" + uri.split(":")[-1]))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return out


def castbox():
    h = get(CASTBOX_PAGE)
    out = []
    for path in sorted(set(re.findall(r'href="(/episode/[^"]+-id\d+-id\d+)"', h))):
        slug = urllib.parse.unquote(path.split("/episode/")[1].rsplit("-id", 2)[0])
        out.append((slug.replace("-", " "), "https://castbox.fm" + path))
    return out


def podcast_guru():
    h = get(GURU_PAGE)
    out = []
    for path in sorted(set(re.findall(r'href="(/podcast/[^"]+/episode/[^"]+)"', h))):
        slug = path.split("/episode/")[1].rsplit("-", 1)[0]
        out.append((slug.replace("-", " "), "https://app.podcastguru.io" + path))
    return out


def truefans():
    h = get(TRUEFANS_PAGE)
    m = re.search(r'"latestEpisode":\{.*?"_id":"([0-9a-f]{24})","title":"((?:[^"\\]|\\.)*)"', h)
    return [(json.loads(f'"{m.group(2)}"'), f"{TRUEFANS_PAGE}/{m.group(1)}")] if m else []


COLLECTORS = {"Apple Podcasts": apple, "Podverse": podverse, "TuneIn": tunein, "Castro": castro,
              "Pocket Casts": pocket_casts, "Deezer": deezer, "Spotify": spotify, "Castbox": castbox,
              "Podcast Guru": podcast_guru, "TrueFans": truefans}


def collect(eps, state):
    """Add newly found links to state; returns {platform: [episode numbers added]}."""
    added = {}

    def put(platform, n, url):
        links = state.setdefault(platform, {})
        if n and str(n) not in links:
            links[str(n)] = url
            added.setdefault(platform, []).append(n)

    now = datetime.datetime.now(datetime.timezone.utc)
    for e in eps:
        if e["link"].startswith("http"):
            put("Website", e["n"], e["link"])
        # Podcast Addict's episode page is keyed by the audio URL; it reads new feeds within hours.
        if e["audio"] and now - e["published"] > datetime.timedelta(days=1):
            put("Podcast Addict", e["n"], "https://podcastaddict.com/episode/" + urllib.parse.quote(e["audio"], safe="")
                + f"&podcastId={PODCAST_ADDICT_ID}")
    errors = {}
    for platform, fn in COLLECTORS.items():
        try:
            for title, url in fn():
                put(platform, episode_number(title, eps), url)
        except Exception as ex:  # one blocked app must not stop the others
            errors[platform] = f"{type(ex).__name__}: {ex}"[:200]
    return added, errors


# ---------- sheet ----------

def col(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_sheet(eps, state, last_n, grid_rows):
    """Rewrite the tab; returns the sheet's row count after any growth."""
    n_eps = len(eps)
    last = col(3 + len(PLATFORMS) - 1)
    total_row = 5 + n_eps
    rows = [["Block Talks — every live episode link"],
            [f"Each cell opens that episode on that app. Updated every day at 11:30; last update {TODAY}. Full URLs are listed further down."],
            [],
            ["Episode", "Title", "Live links"] + [("Our website" if p == "Website" else p) for p in PLATFORMS]]
    for i, e in enumerate(eps):
        r = 5 + i
        rows.append([f"Ep {e['n']}", e["title"], f'=COUNTIF(D{r}:{last}{r},"*Open*")']
                    + [(f'=HYPERLINK("{state.get(p, {})[str(e["n"])]}","▶ Open")' if str(e["n"]) in state.get(p, {}) else "")
                       for p in PLATFORMS])
    rows.append(["", "TOTAL LIVE EPISODE LINKS →", f"=SUM(C5:C{total_row - 1})"]
                + [f'=COUNTIF({col(3 + i)}5:{col(3 + i)}{total_row - 1},"*Open*")&" / {n_eps}"' for i in range(len(PLATFORMS))])
    rows += [[], ["ALL EPISODE LINKS — full URLs"], ["Episode", "Platform", "Link"]]
    for e in eps:
        for p in PLATFORMS:
            url = state.get(p, {}).get(str(e["n"]))
            if url:
                rows.append([f"Ep {e['n']}", "Our website" if p == "Website" else p, url])

    if len(rows) + 30 > grid_rows:  # each new episode adds about 15 rows to the URL list
        grow = len(rows) + 200 - grid_rows
        composio("GOOGLESHEETS_APPEND_DIMENSION", {"spreadsheet_id": SHEET_ID, "sheet_id": TAB_SHEET_ID, "dimension": "ROWS", "length": grow})
        grid_rows += grow
    composio("GOOGLESHEETS_CLEAR_VALUES", {"spreadsheet_id": SHEET_ID, "range": f"'{TAB}'!A1:{last}{grid_rows}"})
    composio("GOOGLESHEETS_UPDATE_VALUES_BATCH", {"spreadsheet_id": SHEET_ID, "valueInputOption": "USER_ENTERED",
                                                  "data": [{"range": f"'{TAB}'!A1", "values": rows}]})
    if n_eps != last_n:  # rows moved: reset and redraw the colours below the header
        green, light, dark = "#1B9F77", "#e5f4e4", "#0b5d45"
        fmt = [dict(range=f"D4:{last}4", bold=True, background_color=green, text_color="#ffffff", horizontal_alignment="CENTER"),
               dict(range=f"A5:{last}{grid_rows}", background_color="#ffffff", text_color="#000000", bold=False, fontSize=10,
                    horizontal_alignment="LEFT"),
               dict(range=f"C5:C{total_row - 1}", bold=True, fontSize=12, background_color=light, text_color=dark,
                    horizontal_alignment="CENTER"),
               dict(range=f"D5:{last}{total_row - 1}", horizontal_alignment="CENTER"),
               dict(range=f"A{total_row}:{last}{total_row}", bold=True, background_color=dark, text_color="#ffffff",
                    horizontal_alignment="CENTER"),
               dict(range=f"C{total_row}", fontSize=14),
               dict(range=f"A{total_row + 2}:C{total_row + 2}", bold=True, fontSize=12, background_color=dark, text_color="#ffffff"),
               dict(range=f"A{total_row + 3}:C{total_row + 3}", bold=True, background_color=green, text_color="#ffffff")]
        for f in fmt:
            composio("GOOGLESHEETS_FORMAT_CELL", dict(spreadsheet_id=SHEET_ID, sheet_name=TAB, **f))
    return grid_rows


def main():
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    last_n = state.pop("_episodes_written", None)
    grid_rows = state.pop("_grid_rows", 360)
    eps = feed_episodes()
    added, errors = collect(eps, state)
    total = sum(len(v) for v in state.values())
    report = {"date": TODAY, "episodes": len(eps), "links": total,
              "added": {p: sorted(v) for p, v in added.items()}, "errors": errors,
              "missing": {p: [e["n"] for e in eps if str(e["n"]) not in state.get(p, {})] for p in PLATFORMS}}
    report["missing"] = {p: v for p, v in report["missing"].items() if v}
    print(json.dumps(report))
    if "--dry-run" in sys.argv:
        return
    grid_rows = write_sheet(eps, state, last_n, grid_rows)
    state["_episodes_written"] = len(eps)
    state["_grid_rows"] = grid_rows
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(state, open(STATE, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
