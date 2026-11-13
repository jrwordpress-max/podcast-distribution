"""PHP that creates one podcast episode on the site.

The post is created only after the audio file is in place. A second run for the
same YouTube id returns the existing post instead of inserting another one,
including when the first request is still in flight (a timeout used to do that).
"""

_TEMPLATE = r"""
$d = json_decode(base64_decode('__B64__'), true);
add_filter('wp_redirect', '__return_false', 9999);
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
$vid = (string) $d['vid'];
$lock = 'ssp_pub_' . preg_replace('/[^A-Za-z0-9_\-]/', '', $vid);

if (empty($d['test'])) {
  $found = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'posts_per_page' => 1, 'fields' => 'ids', 'meta_key' => 'ssp_youtube_id', 'meta_value' => $vid]);
  if (!$found && !empty($d['slug'])) {
    $by_slug = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'name' => $d['slug'], 'posts_per_page' => 1, 'fields' => 'ids']);
    if ($by_slug) {
      $other = (string) get_post_meta($by_slug[0], 'ssp_youtube_id', true);
      if ($other === '' || $other === $vid) { $found = $by_slug; }
    }
  }
  if ($found) {
    $id = $found[0];
    return ['skipped' => true, 'post_id' => $id, 'status' => get_post_status($id), 'url' => get_permalink($id), 'episode' => get_post_meta($id, 'itunes_episode_number', true)];
  }
  $now = time();
  $claim = 'pending:' . $now;
  if (!add_option($lock, $claim, '', false)) {
    $cur = (string) get_option($lock);
    if (strpos($cur, 'pending:') === 0 && ($now - (int) substr($cur, 8)) < 1800) {
      return ['error' => 'publish already in progress for this video; retry shortly', 'retry' => true];
    }
    if ($cur !== '' && ctype_digit($cur) && get_post((int) $cur)) {
      $id = (int) $cur;
      return ['skipped' => true, 'post_id' => $id, 'status' => get_post_status($id), 'url' => get_permalink($id), 'episode' => get_post_meta($id, 'itunes_episode_number', true)];
    }
    update_option($lock, $claim, false);
  }
}

$file = WP_CONTENT_DIR . '/' . $d['rel'];
if (!file_exists($file) || filesize($file) != (int) $d['filesize_raw']) {
  if (empty($d['test'])) { delete_option($lock); }
  return ['error' => 'audio file missing or wrong size', 'size' => file_exists($file) ? filesize($file) : null];
}
$url = content_url($d['rel']);
$att = attachment_url_to_postid($url);
if (!$att) {
  $att = wp_insert_attachment(['post_mime_type' => 'audio/mp4', 'post_title' => $d['title'], 'post_status' => 'inherit'], $file);
  wp_update_attachment_metadata($att, ['filesize' => (int) $d['filesize_raw'], 'mime_type' => 'audio/mp4']);
}
global $wpdb;
__SERIES__
$n = isset($d['episode_number']) ? (int) $d['episode_number'] : 0;
if ($n > 0) {
  __TAKEN__
  if ($taken) { $n = 0; }
}
if ($n < 1) {
  $n = (int) $wpdb->get_var(__MAXSQL__) + 1;
}
$pid = wp_insert_post(['post_type' => 'podcast', 'post_status' => $d['status'], 'post_title' => $d['title'], 'post_name' => $d['slug'], 'post_content' => $d['content'], 'post_excerpt' => $d['excerpt'], 'post_author' => 1, 'meta_input' => ['ssp_youtube_id' => empty($d['test']) ? $vid : '']], true);
if (is_wp_error($pid)) {
  if (empty($d['test'])) { delete_option($lock); }
  return ['error' => $pid->get_error_message()];
}
if (empty($d['test'])) { update_option($lock, (string) $pid, false); }
wp_set_object_terms($pid, [$sid], 'series');
$meta = ['audio_file' => $url, 'enclosure' => $url, 'duration' => $d['duration'], 'filesize' => $d['filesize'], 'filesize_raw' => $d['filesize_raw'], 'episode_type' => 'audio', 'itunes_episode_type' => 'full', 'itunes_episode_number' => (string) $n, 'date_recorded' => $d['date_recorded'], 'ssp_youtube_id' => empty($d['test']) ? $vid : '', 'rank_math_title' => $d['seo'], 'rank_math_description' => $d['meta'], 'rank_math_focus_keyword' => $d['kw']];
foreach ($meta as $k => $v) { update_post_meta($pid, $k, $v); }
__THUMB__
clean_post_cache($pid);
return ['post_id' => $pid, 'episode' => $n, 'status' => get_post_status($pid), 'thumbnail' => $thumb, 'url' => get_permalink($pid), 'edit' => admin_url('post.php?post=' . $pid . '&action=edit')];
"""

_SERIES_AI = r"""
$term = get_term_by('slug', $d['series'], 'series');
if (!$term) {
  if (empty($d['test'])) { delete_option($lock); }
  return ['error' => 'series ' . $d['series'] . ' does not exist'];
}
$sid = (int) $term->term_id;
"""

_SERIES_BT = r"""
$sid = (int) get_option('ss_podcasting_default_series');
"""

_MAX_AI = (
    '$wpdb->prepare("SELECT MAX(CAST(pm.meta_value AS UNSIGNED)) FROM {$wpdb->postmeta} pm '
    "JOIN {$wpdb->posts} p ON p.ID = pm.post_id "
    "JOIN {$wpdb->term_relationships} tr ON tr.object_id = p.ID "
    "JOIN {$wpdb->term_taxonomy} tt ON tt.term_taxonomy_id = tr.term_taxonomy_id "
    "WHERE pm.meta_key = 'itunes_episode_number' AND p.post_type = 'podcast' "
    "AND p.post_status IN ('publish','draft','future','pending') "
    "AND tt.taxonomy = 'series' AND tt.term_id = %d\", $sid)"
)

_MAX_BT = (
    '"SELECT MAX(CAST(pm.meta_value AS UNSIGNED)) FROM {$wpdb->postmeta} pm '
    "JOIN {$wpdb->posts} p ON p.ID = pm.post_id "
    "WHERE pm.meta_key = 'itunes_episode_number' AND p.post_type = 'podcast' "
    "AND p.post_status IN ('publish','draft','future','pending')\""
)

_TAKEN_AI = r"""
$taken = (int) $wpdb->get_var($wpdb->prepare(
  "SELECT COUNT(*) FROM {$wpdb->postmeta} pm
   INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
   INNER JOIN {$wpdb->term_relationships} tr ON tr.object_id = p.ID
   INNER JOIN {$wpdb->term_taxonomy} tt ON tt.term_taxonomy_id = tr.term_taxonomy_id
   LEFT JOIN {$wpdb->postmeta} y ON y.post_id = pm.post_id AND y.meta_key = 'ssp_youtube_id'
   WHERE pm.meta_key = 'itunes_episode_number' AND pm.meta_value = %s
     AND p.post_type = 'podcast'
     AND p.post_status IN ('publish','draft','future','pending')
     AND tt.taxonomy = 'series' AND tt.term_id = %d
     AND (y.meta_id IS NULL OR y.meta_value <> %s)",
  (string) $n, $sid, $vid));
"""

_TAKEN_BT = r"""
$taken = (int) $wpdb->get_var($wpdb->prepare(
  "SELECT COUNT(*) FROM {$wpdb->postmeta} pm
   INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
   LEFT JOIN {$wpdb->postmeta} y ON y.post_id = pm.post_id AND y.meta_key = 'ssp_youtube_id'
   WHERE pm.meta_key = 'itunes_episode_number' AND pm.meta_value = %s
     AND p.post_type = 'podcast'
     AND p.post_status IN ('publish','draft','future','pending')
     AND (y.meta_id IS NULL OR y.meta_value <> %s)",
  (string) $n, $vid));
"""

_THUMB = r"""
$thumb = 'cover';
$tmp = download_url('https://i.ytimg.com/vi/' . $vid . '/maxresdefault.jpg', 15);
if (is_wp_error($tmp)) { $tmp = download_url('https://i.ytimg.com/vi/' . $vid . '/hqdefault.jpg', 15); }
if (!is_wp_error($tmp)) {
  $img = media_handle_sideload(['name' => $d['slug'] . '-__IMAGE__' . '.jpg', 'tmp_name' => $tmp], $pid, $d['title']);
  if (!is_wp_error($img)) { update_post_meta($img, '_wp_attachment_image_alt', $d['title']); set_post_thumbnail($pid, $img); $thumb = 'youtube'; } else { @unlink($tmp); }
}
__COVER__
"""

FIND_PHP = r"""
$d = json_decode(base64_decode('__B64__'), true);
$vid = (string) $d['vid'];
$found = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'posts_per_page' => 1, 'fields' => 'ids', 'meta_key' => 'ssp_youtube_id', 'meta_value' => $vid]);
if (!$found) { return null; }
$id = $found[0];
return ['skipped' => true, 'post_id' => $id, 'status' => get_post_status($id), 'url' => get_permalink($id), 'episode' => get_post_meta($id, 'itunes_episode_number', true)];
"""

INDEX_PHP = r"""
$d = json_decode(base64_decode('__B64__'), true);
$q = ['post_type' => 'podcast', 'post_status' => ['publish', 'draft', 'future', 'pending'], 'posts_per_page' => -1, 'fields' => 'ids'];
if (!empty($d['series'])) {
  $q['tax_query'] = [['taxonomy' => 'series', 'field' => 'slug', 'terms' => $d['series']]];
}
$out = [];
foreach (get_posts($q) as $id) {
  $out[] = ['vid' => (string) get_post_meta($id, 'ssp_youtube_id', true), 'number' => (int) get_post_meta($id, 'itunes_episode_number', true), 'date' => (string) get_post_meta($id, 'date_recorded', true)];
}
return $out;
"""

EXISTING_PHP = r"""
$ids = get_posts(['post_type' => 'podcast', 'post_status' => 'any', 'posts_per_page' => -1, 'fields' => 'ids']);
$out = [];
foreach ($ids as $id) { $v = get_post_meta($id, 'ssp_youtube_id', true); if ($v) { $out[] = $v; } }
return $out;
"""


def render_publish_php(show, b64):
    if show == "ai-samachar":
        series, maxsql, taken, image = _SERIES_AI, _MAX_AI, _TAKEN_AI, "ai-samachar"
        cover = "if ($thumb === 'cover' && (int) $d['cover']) { set_post_thumbnail($pid, (int) $d['cover']); }"
    else:
        series, maxsql, taken, image = _SERIES_BT, _MAX_BT, _TAKEN_BT, "block-talks"
        cover = "if ($thumb === 'cover') { set_post_thumbnail($pid, (int) $d['cover']); }"
    thumb = _THUMB.replace("__IMAGE__", image).replace("__COVER__", cover)
    php = _TEMPLATE
    php = php.replace("__SERIES__", series.strip())
    php = php.replace("__TAKEN__", taken.strip())
    php = php.replace("__MAXSQL__", maxsql)
    php = php.replace("__THUMB__", thumb.strip())
    php = php.replace("__B64__", b64)
    return php


def render_find_php(b64):
    return FIND_PHP.replace("__B64__", b64)


def render_index_php(b64):
    return INDEX_PHP.replace("__B64__", b64)
