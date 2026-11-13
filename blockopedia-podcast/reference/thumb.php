require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
update_post_meta(54997, 'ssp_youtube_id', '2wlAF_x1Dx8');
$cover = 54994;
$ids = get_posts(['post_type' => 'podcast', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids', 'orderby' => 'date', 'order' => 'ASC']);
$done = []; $start = microtime(true);
foreach ($ids as $pid) {
  if ((int) get_post_thumbnail_id($pid) !== $cover) { continue; }
  if (microtime(true) - $start > 20) { break; }
  $vid = get_post_meta($pid, 'ssp_youtube_id', true);
  if (!$vid) { $done[] = [$pid, 'no youtube id']; continue; }
  $tmp = download_url("https://i.ytimg.com/vi/$vid/maxresdefault.jpg", 15);
  if (is_wp_error($tmp)) { $tmp = download_url("https://i.ytimg.com/vi/$vid/hqdefault.jpg", 15); }
  if (is_wp_error($tmp)) { $done[] = [$pid, 'download failed']; continue; }
  $title = get_the_title($pid);
  $name = sanitize_title(explode(' | ', $title)[0]) . '-block-talks.jpg';
  $att = media_handle_sideload(['name' => $name, 'tmp_name' => $tmp], $pid, $title);
  if (is_wp_error($att)) { @unlink($tmp); $done[] = [$pid, 'sideload: ' . $att->get_error_message()]; continue; }
  update_post_meta($att, '_wp_attachment_image_alt', $title);
  set_post_thumbnail($pid, $att);
  $m = wp_get_attachment_metadata($att);
  $done[] = [$pid, $m['width'] . 'x' . $m['height']];
}
$left = 0; foreach ($ids as $pid) { if ((int) get_post_thumbnail_id($pid) === $cover) { $left++; } }
return ['done' => $done, 'still_on_cover' => $left, 'total' => count($ids)];
