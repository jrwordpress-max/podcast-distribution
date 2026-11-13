"""Turn one Block Talks YouTube video into a podcast episode on theblockopedia.com.

  python3 publish.py fetch <video_id>
      Download the video's details and audio into work/<video_id>/ and print the
      details (title, description, chapters) that the SEO copy is written from.

  python3 publish.py publish <video_id> <spec.json> [--status draft|publish]
      Upload the audio through Novamira and create the podcast episode with the
      SEO copy from spec.json. Safe to re-run: a video that already has an
      episode is skipped.

  python3 publish.py existing
      Print the YouTube IDs that already have an episode on the site.
"""
import base64
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


def load_config():
    cfg = {}
    for line in open(os.path.join(DIR, "config.env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


CFG = load_config()
SITE = CFG["SITE"]
FEED_URL = CFG["FEED_URL"]
COVER_ID = 54994  # square TBP cover, used when the YouTube thumbnail can't be fetched


def fail(msg, code=1):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(code)


# ---------- Novamira ----------

def novamira(ability, payload, confirm=False):
    path = os.path.join(WORK, f".nm_{os.getpid()}.json")
    json.dump(payload, open(path, "w"))
    cmd = ["novamira", "--site", SITE, "run", ability, "--input", "@" + path, "--json"]
    if confirm:
        cmd.append("--yes")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
    finally:
        os.remove(path)
    start = out.find("{")
    if start < 0:
        fail(f"novamira {ability} gave no JSON: {out[-300:]}")
    return json.loads(out[start:])


def php(code):
    res = novamira("novamira/execute-php", {"code": code}, confirm=True)
    data = res.get("data") or {}
    if "return_value" not in data:
        fail(f"execute-php failed: {json.dumps(res)[:500]}")
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
    content += head("What you&#8217;ll learn") + ul([esc(x) for x in spec["learn"]])
    chapters = spec.get("chapters") or [[c["start"], c["title"]] for c in meta.get("chapters", [])]
    if chapters:
        content += head("Chapters") + para("<br>".join(f"{ts(s)} {esc(t)}" for s, t in chapters))
    links = [f'{esc(label)}: <a href="{u}" target="_blank" rel="noopener">{esc(u.split("//", 1)[-1].rstrip("/"))}</a>'
             for label, u in spec.get("links", [])]
    links.append(f'Watch on YouTube: <a href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">youtube.com/watch?v={vid}</a>')
    links.append('More Block Talks: <a href="https://theblockopedia.com/blocktalks-audio-podcast/">theblockopedia.com/blocktalks-audio-podcast</a>')
    return content + head("Links") + ul(links)


PUBLISH_PHP = r"""
$d = json_decode(base64_decode('%s'), true);
add_filter('wp_redirect', '__return_false', 9999);
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
$found = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'meta_key' => 'ssp_youtube_id', 'meta_value' => $d['vid'], 'fields' => 'ids']);
if ($found && empty($d['test'])) { return ['skipped' => true, 'post_id' => $found[0], 'status' => get_post_status($found[0]), 'url' => get_permalink($found[0])]; }
$file = WP_CONTENT_DIR . '/' . $d['rel'];
if (!file_exists($file) || filesize($file) != (int) $d['filesize_raw']) { return ['error' => 'audio file missing or wrong size', 'size' => file_exists($file) ? filesize($file) : null]; }
$url = content_url($d['rel']);
$att = attachment_url_to_postid($url);
if (!$att) {
  $att = wp_insert_attachment(['post_mime_type' => 'audio/mp4', 'post_title' => $d['title'], 'post_status' => 'inherit'], $file);
  wp_update_attachment_metadata($att, ['filesize' => (int) $d['filesize_raw'], 'mime_type' => 'audio/mp4']);
}
global $wpdb;
$n = (int) $wpdb->get_var("SELECT MAX(CAST(pm.meta_value AS UNSIGNED)) FROM {$wpdb->postmeta} pm JOIN {$wpdb->posts} p ON p.ID = pm.post_id WHERE pm.meta_key = 'itunes_episode_number' AND p.post_type = 'podcast' AND p.post_status IN ('publish','draft','future','pending')") + 1;
$sid = (int) get_option('ss_podcasting_default_series');
$pid = wp_insert_post(['post_type' => 'podcast', 'post_status' => $d['status'], 'post_title' => $d['title'], 'post_name' => $d['slug'], 'post_content' => $d['content'], 'post_excerpt' => $d['excerpt'], 'post_author' => 1], true);
if (is_wp_error($pid)) { return ['error' => $pid->get_error_message()]; }
wp_set_object_terms($pid, [$sid], 'series');
$meta = ['audio_file' => $url, 'enclosure' => $url, 'duration' => $d['duration'], 'filesize' => $d['filesize'], 'filesize_raw' => $d['filesize_raw'], 'episode_type' => 'audio', 'itunes_episode_type' => 'full', 'itunes_episode_number' => (string) $n, 'date_recorded' => $d['date_recorded'], 'ssp_youtube_id' => empty($d['test']) ? $d['vid'] : '', 'rank_math_title' => $d['seo'], 'rank_math_description' => $d['meta'], 'rank_math_focus_keyword' => $d['kw']];
foreach ($meta as $k => $v) { update_post_meta($pid, $k, $v); }
$thumb = 'cover';
$tmp = download_url('https://i.ytimg.com/vi/' . $d['vid'] . '/maxresdefault.jpg', 15);
if (is_wp_error($tmp)) { $tmp = download_url('https://i.ytimg.com/vi/' . $d['vid'] . '/hqdefault.jpg', 15); }
if (!is_wp_error($tmp)) {
  $img = media_handle_sideload(['name' => $d['slug'] . '-block-talks.jpg', 'tmp_name' => $tmp], $pid, $d['title']);
  if (!is_wp_error($img)) { update_post_meta($img, '_wp_attachment_image_alt', $d['title']); set_post_thumbnail($pid, $img); $thumb = 'youtube'; } else { @unlink($tmp); }
}
if ($thumb === 'cover') { set_post_thumbnail($pid, (int) $d['cover']); }
clean_post_cache($pid);
return ['post_id' => $pid, 'episode' => $n, 'status' => get_post_status($pid), 'thumbnail' => $thumb, 'url' => get_permalink($pid), 'edit' => admin_url('post.php?post=' . $pid . '&action=edit')];
"""


def cmd_publish(vid, spec_path, status):
    d = os.path.join(WORK, vid)
    meta = json.load(open(os.path.join(d, "meta.json")))
    spec = json.load(open(spec_path))
    for k in ("title", "hook", "learn", "seo", "meta", "kw"):
        if not spec.get(k):
            fail(f"spec.json is missing '{k}'")
    audio = os.path.join(d, "audio.m4a")
    size = os.path.getsize(audio)
    test = os.environ.get("BT_TEST") == "1"  # test run: allow a video that already has an episode, always as a draft
    if test:
        spec["title"], status = "[TEST] " + spec["title"], "draft"
    slug = slugify(spec["title"].split(" | ")[0])
    fname = f"blocktalks-{slug[:40].rstrip('-')}-{vid}.m4a"
    rel = f"uploads/{time.strftime('%Y/%m')}/{fname}"

    # Upload the audio through a one-time Novamira upload link (multipart; plain PUT truncates large files).
    link = novamira("novamira/create-upload-link", {"path": "wp-content/" + rel, "expires_in": 1800,
                                                     "max_bytes": size + 1024, "overwrite": True}).get("data") or {}
    if link.get("upload_url") and link.get("upload_token"):
        r = subprocess.run(["curl", "-s", "-m", "1500", "-H", f"{link.get('token_header', 'X-Novamira-Upload-Token')}: {link['upload_token']}",
                            "-F", f"file=@{audio};filename={fname};type=audio/mp4", link["upload_url"], "-w", "\n%{http_code}"],
                           capture_output=True, text=True)
        code = r.stdout.strip().rsplit("\n", 1)[-1]
        if code != "200":
            fail(f"audio upload failed (HTTP {code}): {r.stdout[-300:]}")

    data = dict(vid=vid, title=spec["title"], slug=slug, content=build_content(spec, meta, vid), excerpt=spec["hook"],
                date_recorded=f"{meta['upload_date'][:4]}-{meta['upload_date'][4:6]}-{meta['upload_date'][6:]}",
                duration=hms(meta["duration"]), filesize=f"{size / 1048576:.2f}M", filesize_raw=str(size),
                seo=spec["seo"], meta=spec["meta"], kw=spec["kw"], rel=rel, cover=COVER_ID, status=status, test=test)
    result = php(PUBLISH_PHP % base64.b64encode(json.dumps(data).encode()).decode())
    if not isinstance(result, dict) or result.get("error"):
        fail(f"publish failed: {result}")
    if status == "publish" and not result.get("skipped"):
        q = urllib.parse.quote(FEED_URL, safe="")
        try:
            req = urllib.request.Request(f"https://api.podcastindex.org/api/1.0/hub/pubnotify?url={q}", headers={"User-Agent": "BlockTalksPublisher/1.0"})
            result["podcastindex"] = json.loads(urllib.request.urlopen(req, timeout=20).read()).get("description")
        except Exception as e:  # the feed still updates on its own; the ping only speeds it up
            result["podcastindex"] = f"ping failed: {e}"
    result.update(ok=True, video=vid, title=spec["title"])
    json.dump(result, open(os.path.join(d, "result.json"), "w"), indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["existing"]:
        cmd_existing()
    elif a[:1] == ["fetch"] and len(a) == 2:
        cmd_fetch(a[1])
    elif a[:1] == ["publish"] and len(a) >= 3:
        st = a[a.index("--status") + 1] if "--status" in a else CFG.get("MODE", "draft")
        if st not in ("draft", "publish"):
            fail("status must be draft or publish")
        cmd_publish(a[1], a[2], st)
    else:
        print(__doc__)
        sys.exit(2)
