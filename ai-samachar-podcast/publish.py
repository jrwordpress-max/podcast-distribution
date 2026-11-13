"""Turn one AI Samachar YouTube video into a podcast episode on podcast.rankkking.com.

  python3 publish.py fetch <video_id>
      Download the video's details and audio into work/<video_id>/ and print the
      details (title, description, chapters) that the SEO copy is written from.

  python3 publish.py publish <video_id> <spec.json> [--status draft|publish]
      Upload the audio through Novamira and create the podcast episode with the
      SEO copy from spec.json. Safe to re-run: a video that already has an
      episode is skipped.

  python3 publish.py existing
      Print the YouTube IDs that already have an episode on the site.

  python3 publish.py autospec <video_id>
      Write basic show notes from the description when Claude is unavailable.

  python3 publish.py episode-index
      Print episode numbers already on the site, as JSON.
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(DIR, "work")
sys.path.insert(0, os.path.join(os.path.dirname(DIR), "shared"))


class PublishError(RuntimeError):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def load_config():
    from podcastlib.config import load_config as _load
    return _load(DIR)


CFG = load_config()
SITE = CFG["SITE"]
FEED_URL = CFG["FEED_URL"]
SERIES = CFG["SERIES"]  # the show's series; the site's default series belongs to Block Talks
COVER_ID = int(CFG.get("COVER_ID", "0") or 0)  # square AI Samachar cover, used when the YouTube thumbnail can't be fetched


def fail(msg, code=1):
    raise PublishError(msg, code)


# ---------- Novamira ----------
# The site is reached over the WordPress Abilities REST API with the application password in
# .wp.env (see nmrest.py), so the hourly job needs no browser sign-in.

import nmrest  # noqa: E402


def novamira(ability, payload, confirm=False):
    from podcastlib.wp import ability_result, failed
    res = nmrest.run(ability, payload)
    if failed(res):
        fail(f"novamira {ability} failed: {json.dumps(res)[:300]}")
    return {"data": ability_result(res)}


def php(code):
    data = novamira("novamira/execute-php", {"code": code}).get("data") or {}
    if "return_value" not in data:
        fail(f"execute-php failed: {json.dumps(data)[:500]}")
    return data["return_value"]


# ---------- helpers ----------

def hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:70].rstrip("-")


def para(t):
    return f"<!-- wp:paragraph -->\n<p>{t}</p>\n<!-- /wp:paragraph -->\n\n"


def head(t):
    return f'<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{t}</h3>\n<!-- /wp:heading -->\n\n'


def ul(items):
    out = '<!-- wp:list -->\n<ul class="wp-block-list">'
    for i in items:
        out += f"<!-- wp:list-item -->\n<li>{i}</li>\n<!-- /wp:list-item -->"
    return out + "</ul>\n<!-- /wp:list -->\n\n"


def esc(t):
    return html.escape(t, quote=False)


# ---------- commands ----------

def cmd_existing():
    ids = php("""
$ids = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'posts_per_page' => -1, 'fields' => 'ids']);
$out = [];
foreach ($ids as $id) { $v = get_post_meta($id, 'ssp_youtube_id', true); if ($v) { $out[] = $v; } }
return $out;
""")
    print("\n".join(ids))


def cmd_fetch(vid):
    d = os.path.join(WORK, vid)
    os.makedirs(d, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={vid}"
    r = subprocess.run(["yt-dlp", "-j", "--no-warnings", url], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        fail(f"yt-dlp could not read the video: {r.stderr.strip()[-300:]}")
    m = json.loads(r.stdout)
    if m.get("live_status") in ("is_upcoming", "is_live", "post_live"):
        fail(f"video not ready yet (live_status={m.get('live_status')})", code=3)
    meta = {k: m.get(k) for k in ("id", "title", "description", "duration", "upload_date", "channel", "tags", "webpage_url")}
    meta["chapters"] = [{"start": int(c["start_time"]), "title": c["title"].strip()} for c in (m.get("chapters") or [])]
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)

    audio = os.path.join(d, "audio.m4a")
    if not os.path.exists(audio):
        r = subprocess.run(["yt-dlp", "-f", "140/bestaudio[ext=m4a]", "--no-warnings", "--no-progress",
                            "-o", os.path.join(d, "audio.%(ext)s"), url], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not os.path.exists(audio):
            fail(f"audio download failed: {r.stderr.strip()[-300:]}")
    meta["audio_mb"] = round(os.path.getsize(audio) / 1048576, 1)
    print(json.dumps(meta, indent=1, ensure_ascii=False))


def build_content(spec, meta, vid):
    content = para(esc(spec["hook"]))
    content += head("Top stories") + ul([esc(x) for x in spec["learn"]])
    chapters = spec.get("chapters") or [[c["start"], c["title"]] for c in meta.get("chapters", [])]
    if chapters:
        content += head("Chapters") + para("<br>".join(f"{ts(s)} {esc(t)}" for s, t in chapters))
    links = [f'{esc(label)}: <a href="{u}" target="_blank" rel="noopener">{esc(u.split("//", 1)[-1].rstrip("/"))}</a>'
             for label, u in spec.get("links", [])]
    links.append(f'Watch on YouTube: <a href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">youtube.com/watch?v={vid}</a>')
    links.append('More AI Samachar: <a href="https://www.youtube.com/@Rankkking" target="_blank" rel="noopener">youtube.com/@Rankkking</a>')
    content += head("Links") + ul(links)
    if spec.get("sources"):
        content += head("Sources") + ul([f'<a href="{u}" target="_blank" rel="noopener">{esc(label)}</a>' for label, u in spec["sources"]])
    if spec.get("disclosure"):
        content += para(esc(spec["disclosure"]))
    return content


def _save_result(folder, result):
    json.dump(result, open(os.path.join(folder, "result.json"), "w"), indent=1)
    print(json.dumps(result, indent=1))


def cmd_publish(vid, spec_path, status):
    from podcastlib.episode import UploadError, episode_number_for, insert_episode, lookup_existing, upload_audio
    folder = os.path.join(WORK, vid)
    meta = json.load(open(os.path.join(folder, "meta.json")))
    spec = json.load(open(spec_path))
    for key in ("title", "hook", "learn", "seo", "meta", "kw"):
        if not spec.get(key):
            fail(f"spec.json is missing '{key}'")
    audio = os.path.join(folder, "audio.m4a")
    size = os.path.getsize(audio)
    test = os.environ.get("AS_TEST") == "1"  # test run: allow a video that already has an episode, always as a draft
    if test:
        spec["title"], status = "[TEST] " + spec["title"], "draft"
    if not test:
        # A timed-out publish may already have created the post. Do not upload or insert again.
        existing = lookup_existing(php, vid)
        if existing:
            existing.update(ok=True, video=vid, title=spec["title"], skipped=True)
            _save_result(folder, existing)
            return
    slug = slugify(spec["title"].split(" | ")[0])
    fname = f"ai-samachar-{slug[:40].rstrip('-')}-{vid}.m4a"
    rel = f"uploads/{time.strftime('%Y/%m')}/{fname}"
    try:
        upload_audio(novamira, rel, fname, audio, size)
    except UploadError as exc:
        fail(str(exc))
    data = dict(vid=vid, title=spec["title"], slug=slug, content=build_content(spec, meta, vid), excerpt=spec["hook"],
                date_recorded=f"{meta['upload_date'][:4]}-{meta['upload_date'][4:6]}-{meta['upload_date'][6:]}",
                duration=hms(meta["duration"]), filesize=f"{size / 1048576:.2f}M", filesize_raw=str(size),
                seo=spec["seo"], meta=spec["meta"], kw=spec["kw"], rel=rel, cover=COVER_ID, status=status, test=test,
                series=SERIES, episode_number=episode_number_for(folder))
    result = insert_episode(php, "ai-samachar", data)
    if not isinstance(result, dict) or result.get("error"):
        fail(f"publish failed: {result}")
    if status == "publish" and not result.get("skipped"):
        q = urllib.parse.quote(FEED_URL, safe="")
        try:
            req = urllib.request.Request(f"https://api.podcastindex.org/api/1.0/hub/pubnotify?url={q}", headers={"User-Agent": "AISamacharPublisher/1.0"})
            result["podcastindex"] = json.loads(urllib.request.urlopen(req, timeout=20).read()).get("description")
        except Exception as exc:  # the feed still updates on its own; the ping only speeds it up
            result["podcastindex"] = f"ping failed: {exc}"
    result.update(ok=True, video=vid, title=spec["title"])
    _save_result(folder, result)


def cmd_autospec(vid, overrides_path=None):
    """Write work/<vid>/spec.json from the video's description, without Claude."""
    from podcastlib.basic_spec import build_basic_spec
    folder = os.path.join(WORK, vid)
    meta = json.load(open(os.path.join(folder, "meta.json")))
    spec = build_basic_spec("ai-samachar", meta)
    if overrides_path:
        spec.update(json.load(open(overrides_path)))
    json.dump(spec, open(os.path.join(folder, "spec.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"ok": True, "spec": os.path.join(folder, "spec.json"), "title": spec["title"],
                      "sources": len(spec.get("sources") or [])}, ensure_ascii=False))


def cmd_episode_index():
    from podcastlib.episode import episode_index
    series = os.environ["EPISODE_INDEX_SERIES"] if "EPISODE_INDEX_SERIES" in os.environ else (CFG.get("SERIES") or "")
    print(json.dumps(episode_index(php, series)))


def main(argv):
    try:
        return _main(argv)
    except PublishError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return exc.code


def _main(argv):
    if argv[:1] == ["existing"]:
        cmd_existing()
    elif argv[:1] == ["episode-index"]:
        cmd_episode_index()
    elif argv[:1] == ["autospec"] and len(argv) in (2, 3):
        cmd_autospec(argv[1], argv[2] if len(argv) == 3 else None)
    elif argv[:1] == ["fetch"] and len(argv) == 2:
        cmd_fetch(argv[1])
    elif argv[:1] == ["publish"] and len(argv) >= 3:
        status = argv[argv.index("--status") + 1] if "--status" in argv else CFG.get("MODE", "draft")
        if status not in ("draft", "publish"):
            fail("status must be draft or publish")
        cmd_publish(argv[1], argv[2], status)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
