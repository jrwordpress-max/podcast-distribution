"""Client side of creating one episode: skip if it exists, upload, then insert."""
import base64
import json

from podcastlib.numbering import read_saved_number
from podcastlib.publish_php import EXISTING_PHP, render_find_php, render_index_php, render_publish_php
from podcastlib.upload import UploadError, curl_upload_status, request_upload_link, upload_with_retries


def _b64(payload):
    return base64.b64encode(json.dumps(payload).encode()).decode()


def lookup_existing(php_fn, vid):
    """The post already stored for this YouTube id, or None."""
    found = php_fn(render_find_php(_b64({"vid": vid})))
    if isinstance(found, dict) and found.get("post_id"):
        return found
    return None


def episode_index(php_fn, series):
    rows = php_fn(render_index_php(_b64({"series": series or ""})))
    return rows or []


def existing_youtube_ids(php_fn):
    return php_fn(EXISTING_PHP) or []


def upload_audio(novamira_fn, rel, fname, audio, size, attempts=3, sleep=None):
    """Upload the audio file. Raises UploadError when the site gives no URL."""
    upload_with_retries(
        lambda: request_upload_link(novamira_fn, rel, size),
        lambda link: curl_upload_status(audio, fname, link),
        attempts=attempts,
        sleep=sleep,
    )


def insert_episode(php_fn, show, data):
    return php_fn(render_publish_php(show, _b64(data)))


def episode_number_for(work_dir):
    return read_saved_number(work_dir)


__all__ = [
    "UploadError",
    "episode_index",
    "episode_number_for",
    "existing_youtube_ids",
    "insert_episode",
    "lookup_existing",
    "upload_audio",
]
