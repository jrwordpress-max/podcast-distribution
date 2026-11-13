<?php
/**
 * Block Talks: record which app or website each podcast play comes from.
 *
 * Seriously Simple Stats does not keep the listening app, so this logs every episode
 * download into {prefix}tbp_podcast_plays with the platform worked out from the user agent.
 * One play is counted per listener (hashed IP), episode and platform per 24 hours,
 * and bots, crawlers and HEAD checks are skipped, so app re-downloads don't inflate counts.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function tbp_podcast_plays_table() {
	global $wpdb;
	return $wpdb->prefix . 'tbp_podcast_plays';
}

add_action( 'init', function () {
	if ( get_option( 'tbp_podcast_plays_db' ) === '1' ) {
		return;
	}
	global $wpdb;
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta( 'CREATE TABLE ' . tbp_podcast_plays_table() . " (
		id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
		post_id bigint(20) unsigned NOT NULL,
		platform varchar(40) NOT NULL,
		user_agent varchar(255) NOT NULL DEFAULT '',
		ip_hash char(32) NOT NULL,
		created datetime NOT NULL,
		PRIMARY KEY  (id),
		KEY post_platform (post_id, platform),
		KEY created (created)
	) " . $wpdb->get_charset_collate() . ';' );
	update_option( 'tbp_podcast_plays_db', '1', false );
} );

function tbp_podcast_platform( $ua, $referrer ) {
	$apps = array(
		'Spotify'          => 'Spotify',
		'AppleCoreMedia'   => 'Apple Podcasts',
		'iTunes'           => 'Apple Podcasts',
		'Apple Podcasts'   => 'Apple Podcasts',
		'watchOS'          => 'Apple Podcasts',
		'Pocket Casts'     => 'Pocket Casts',
		'PocketCasts'      => 'Pocket Casts',
		'Overcast'         => 'Overcast',
		'CastBox'          => 'Castbox',
		'PodcastAddict'    => 'Podcast Addict',
		'Player FM'        => 'Player FM',
		'PlayerFM'         => 'Player FM',
		'AmazonMusic'      => 'Amazon Music',
		'Amazon Music'     => 'Amazon Music',
		'Alexa'            => 'Amazon Music',
		'Audible'          => 'Audible',
		'Deezer'           => 'Deezer',
		'TuneIn'           => 'TuneIn',
		'iHeart'           => 'iHeartRadio',
		'Anghami'          => 'Anghami',
		'Goodpods'         => 'Goodpods',
		'Podverse'         => 'Podverse',
		'Fountain'         => 'Fountain',
		'CurioCaster'      => 'CurioCaster',
		'AntennaPod'       => 'AntennaPod',
		'Castro'           => 'Castro',
		'Castamatic'       => 'Castamatic',
		'Podcast Guru'     => 'Podcast Guru',
		'Podbean'          => 'Podbean',
		'Podcast Republic' => 'Podcast Republic',
		'TrueFans'         => 'TrueFans',
		'Breez'            => 'Breez',
		'Snipd'            => 'Snipd',
		'Musixmatch'       => 'Musixmatch',
		'gPodder'          => 'gPodder',
		'Downcast'         => 'Downcast',
		'JioSaavn'         => 'JioSaavn',
		'YouTube'          => 'YouTube Music',
		'Google-Podcast'   => 'Google',
		'GoogleChirp'      => 'Google',
	);
	foreach ( $apps as $needle => $name ) {
		if ( stripos( $ua, $needle ) !== false ) {
			return $name;
		}
	}
	if ( 'player' === $referrer ) {
		return 'Website player';
	}
	if ( 'download' === $referrer || 'new_window' === $referrer ) {
		return 'Website download';
	}
	if ( preg_match( '/Mozilla|Chrome|Safari|Firefox|Edg\//i', $ua ) ) {
		return 'Web browser';
	}
	return 'Other apps';
}

add_action( 'ssp_file_download', function ( $file, $episode, $referrer ) {
	if ( ! $episode || empty( $episode->ID ) ) {
		return;
	}
	if ( isset( $_SERVER['REQUEST_METHOD'] ) && 'HEAD' === strtoupper( $_SERVER['REQUEST_METHOD'] ) ) {
		return;
	}
	$ua = isset( $_SERVER['HTTP_USER_AGENT'] ) ? substr( (string) wp_unslash( $_SERVER['HTTP_USER_AGENT'] ), 0, 255 ) : '';
	// Bots and crawlers, and Apple's "Podcasts/" pre-check that is followed by the real AppleCoreMedia download.
	if ( '' === $ua || preg_match( '/bot|crawl|spider|slurp|curl|wget|python|go-http|podcast-trend|podcastindex|feed|validator|^Podcasts\//i', $ua ) ) {
		return;
	}
	$ip = '';
	foreach ( array( 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' ) as $key ) {
		if ( ! empty( $_SERVER[ $key ] ) ) {
			$ip = trim( explode( ',', (string) $_SERVER[ $key ] )[0] );
			break;
		}
	}
	global $wpdb;
	$table    = tbp_podcast_plays_table();
	$platform = tbp_podcast_platform( $ua, (string) $referrer );
	$ip_hash  = md5( wp_salt( 'nonce' ) . $ip );
	$recent   = $wpdb->get_var( $wpdb->prepare(
		"SELECT id FROM $table WHERE post_id = %d AND platform = %s AND ip_hash = %s AND created > %s LIMIT 1",
		$episode->ID, $platform, $ip_hash, gmdate( 'Y-m-d H:i:s', time() - DAY_IN_SECONDS )
	) );
	if ( $recent ) {
		return;
	}
	$wpdb->insert( $table, array(
		'post_id'    => $episode->ID,
		'platform'   => $platform,
		'user_agent' => $ua,
		'ip_hash'    => $ip_hash,
		'created'    => gmdate( 'Y-m-d H:i:s' ),
	) );
}, 5, 3 );
