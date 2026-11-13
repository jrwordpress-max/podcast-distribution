"""WordPress / Novamira ability calls.

The Mac's Block Talks job uses the novamira CLI and its saved login. A server
or GitHub Actions run has no saved login: when WP_API_USERNAME and
WP_API_PASSWORD are set (environment, secrets.env, or .wp.env) both shows use
the same REST call AI Samachar already uses.
"""
import base64
import json
import os
import urllib.error
import urllib.request

from podcastlib.config import load_config


def credentials(show_dir, environ=None):
    cfg = load_config(show_dir, environ)
    user = cfg.get("WP_API_USERNAME")
    password = cfg.get("WP_API_PASSWORD")
    if user and password:
        return user, password
    return None, None


def ability_result(res):
    """Normalize a CLI body ({data: payload}) and a raw REST body to the payload."""
    if not isinstance(res, dict):
        return {}
    data = res.get("data")
    if isinstance(data, dict) and ("return_value" in data or "upload_url" in data):
        if "return_value" not in res and "upload_url" not in res:
            return data
    return res


def rest_run(site, user, password, ability, payload, timeout=600, opener=None):
    host = (site or "").strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    host = host.split("/")[0]
    if not host or "." not in host:
        return {"success": False, "error": "SITE %r is not a host name; cannot call the REST API" % site}
    url = "https://%s/wp-json/wp-abilities/v1/abilities/%s/run" % (host, ability)
    body = json.dumps({"input": payload}).encode()
    auth = base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Basic " + auth,
        "Content-Type": "application/json",
        "User-Agent": "PodcastPublisher/1.0",
    })
    urlopen = opener or urllib.request.urlopen
    try:
        raw = urlopen(req, timeout=timeout).read()
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return {"success": False, "error": "HTTP %s: %s" % (exc.code, detail)}


def failed(res):
    if not isinstance(res, dict):
        return True
    if res.get("success") is False and "return_value" not in res and "upload_url" not in res:
        return True
    return False
