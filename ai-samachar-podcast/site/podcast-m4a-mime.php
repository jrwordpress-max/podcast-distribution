<?php
/**
 * Plugin Name: Podcast audio type for .m4a
 * Description: WordPress labels .m4a files as audio/mpeg (MP3). Podcast feeds need audio/x-m4a for AAC audio, so this corrects the type used in the AI Samachar feed.
 */
add_filter('mime_types', function ($types) {
    foreach ($types as $ext => $type) {
        if ($type === 'audio/mpeg' && preg_match('/(^|\|)m4a(\||$)/', $ext)) {
            unset($types[$ext]);
            $rest = trim(preg_replace('/(^|\|)(m4a|m4b)(?=\||$)/', '', $ext), '|');
            if ($rest !== '') {
                $types[$rest] = 'audio/mpeg';
            }
        }
    }
    $types['m4a|m4b'] = 'audio/x-m4a';
    return $types;
});
