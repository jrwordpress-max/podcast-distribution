"""Build one PHP payload per episode (publishes it on theblockopedia.com) and a manifest."""
import glob
import html
import json
import os
import re
import sys

S = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = sys.argv[1]
sys.path.insert(0, S)
from episodes_spec import EP, CHAPTER_FIX  # noqa: E402

COVER_ID = 54994


def hms(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def slugify(t):
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return t[:70].rstrip("-")


def para(t):
    return f"<!-- wp:paragraph -->\n<p>{t}</p>\n<!-- /wp:paragraph -->\n\n"


def head(t):
    return f'<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{t}</h3>\n<!-- /wp:heading -->\n\n'


def ul(items):
    out = '<!-- wp:list -->\n<ul class="wp-block-list">'
    for i in items:
        out += f"<!-- wp:list-item -->\n<li>{i}</li>\n<!-- /wp:list-item -->"
    return out + "</ul>\n<!-- /wp:list -->\n\n"


rows = [l.split("|", 4) for l in open(os.path.join(S, "pl.txt")).read().splitlines() if l.strip()]
eps = []
for pos, vid, _dur, _ch, _title in rows:
    meta = json.load(open(os.path.join(S, "meta", f"{pos}.json")))
    files = glob.glob(os.path.join(AUDIO_DIR, f"*[[]{vid}[]].m4a"))
    assert len(files) == 1, (pos, vid, files)
    eps.append(dict(pos=pos, vid=vid, meta=meta, file=files[0]))

eps.sort(key=lambda e: e["meta"]["upload_date"])
manifest = []
for n, e in enumerate(eps, start=1):
    spec = EP[e["pos"]]
    m = e["meta"]
    esc = lambda t: html.escape(t, quote=False)
    content = para(esc(spec["hook"]))
    content += head("What you&#8217;ll learn") + ul([esc(x) for x in spec["learn"]])
    chapters = m.get("chapters") or []
    if chapters:
        lines = [f"{ts(c['start_time'])} {esc(CHAPTER_FIX.get(c['title'].strip(), c['title'].strip()))}" for c in chapters]
        content += head("Chapters") + para("<br>".join(lines))
    links = [f'{esc(label)}: <a href="{url}" target="_blank" rel="noopener">{esc(url.split("//")[1].rstrip("/"))}</a>' for label, url in spec["links"]]
    links.append(f'Watch on YouTube: <a href="https://www.youtube.com/watch?v={e["vid"]}" target="_blank" rel="noopener">youtube.com/watch?v={e["vid"]}</a>')
    links.append('More Block Talks: <a href="https://theblockopedia.com/blocktalks-audio-podcast/">theblockopedia.com/blocktalks-audio-podcast</a>')
    content += head("Links") + ul(links)

    d = m["upload_date"]
    date_gmt = f"{d[:4]}-{d[4:6]}-{d[6:]} 12:00:00"
    size = os.path.getsize(e["file"])
    slug = slugify(spec["title"].split(" | ")[0])
    fname = f"blocktalks-ep{n:02d}-{slug[:40].rstrip('-')}.m4a"
    data = dict(
        n=n, vid=e["vid"], title=spec["title"], slug=slug, content=content,
        excerpt=spec["hook"], date_gmt=date_gmt, date_recorded=date_gmt[:10],
        duration=hms(m["duration"]), filesize=f"{size / 1048576:.2f}M", filesize_raw=str(size),
        seo=spec["seo"], meta=spec["meta"], kw=spec["kw"], fname=fname, cover=COVER_ID,
    )
    php = r"""
$d = json_decode(base64_decode('%s'), true);
add_filter('wp_redirect', '__return_false', 9999);
require_once ABSPATH . 'wp-admin/includes/image.php';
$found = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'meta_key' => 'ssp_youtube_id', 'meta_value' => $d['vid'], 'fields' => 'ids']);
if ($found) { return ['skipped' => true, 'post_id' => $found[0]]; }
$file = WP_CONTENT_DIR . '/uploads/2026/10/' . $d['fname'];
if (!file_exists($file) || filesize($file) != (int) $d['filesize_raw']) { return ['error' => 'audio file missing or wrong size', 'size' => file_exists($file) ? filesize($file) : null]; }
$url = content_url('uploads/2026/10/' . $d['fname']);
$att = attachment_url_to_postid($url);
if (!$att) {
  $att = wp_insert_attachment(['post_mime_type' => 'audio/mp4', 'post_title' => $d['title'], 'post_status' => 'inherit'], $file);
  wp_update_attachment_metadata($att, ['filesize' => (int) $d['filesize_raw'], 'mime_type' => 'audio/mp4']);
}
$sid = (int) get_option('ss_podcasting_default_series');
$pid = wp_insert_post(['post_type' => 'podcast', 'post_status' => 'publish', 'post_title' => $d['title'], 'post_name' => $d['slug'], 'post_content' => $d['content'], 'post_excerpt' => $d['excerpt'], 'post_date_gmt' => $d['date_gmt'], 'post_date' => get_date_from_gmt($d['date_gmt']), 'post_author' => 1], true);
if (is_wp_error($pid)) { return ['error' => $pid->get_error_message()]; }
wp_set_object_terms($pid, [$sid], 'series');
set_post_thumbnail($pid, (int) $d['cover']);
$meta = ['audio_file' => $url, 'enclosure' => $url, 'duration' => $d['duration'], 'filesize' => $d['filesize'], 'filesize_raw' => $d['filesize_raw'], 'episode_type' => 'audio', 'itunes_episode_type' => 'full', 'itunes_episode_number' => (string) $d['n'], 'date_recorded' => $d['date_recorded'], 'ssp_youtube_id' => $d['vid'], 'rank_math_title' => $d['seo'], 'rank_math_description' => $d['meta'], 'rank_math_focus_keyword' => $d['kw']];
foreach ($meta as $k => $v) { update_post_meta($pid, $k, $v); }
clean_post_cache($pid);
return ['post_id' => $pid, 'n' => $d['n'], 'status' => get_post_status($pid), 'audio_ok' => get_post_meta($pid, 'audio_file', true) === $url, 'url' => get_permalink($pid)];
""" % (__import__("base64").b64encode(json.dumps(data).encode()).decode())
    out = os.path.join(S, "payloads", f"ep{n:02d}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"code": php}, open(out, "w"))
    manifest.append(dict(n=n, vid=e["vid"], file=e["file"], fname=fname, size=size, date=date_gmt[:10], title=spec["title"], payload=out))

json.dump(manifest, open(os.path.join(S, "payloads", "manifest.json"), "w"), indent=1)
for x in manifest:
    print(f"Ep{x['n']:02d} {x['date']} {x['size'] / 1048576:5.1f}MB {x['title']}")
