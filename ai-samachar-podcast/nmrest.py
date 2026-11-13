"""Novamira abilities on podcast.rankkking.com over the WordPress Abilities REST API.

Credentials come from WP_API_USERNAME and WP_API_PASSWORD in the environment,
secrets.env, or .wp.env. Nothing is read at import time, so a missing password
file does not break `python3 publish.py` until a command actually calls the site.
"""
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, os.path.join(ROOT, "shared"))

from podcastlib.config import load_config  # noqa: E402
from podcastlib.wp import failed, rest_run  # noqa: E402


def run(ability, payload, timeout=600):
    cfg = load_config(DIR)
    user, password = cfg.get("WP_API_USERNAME"), cfg.get("WP_API_PASSWORD")
    if not user or not password:
        return {"success": False, "error": "WP_API_USERNAME and WP_API_PASSWORD are not set (.wp.env or the environment)"}
    return rest_run(cfg["SITE"], user, password, ability, payload, timeout=timeout)


def php(code):
    res = run("novamira/execute-php", {"code": code})
    if failed(res) or "return_value" not in res:
        raise RuntimeError("execute-php failed: %s" % __import__("json").dumps(res)[:500])
    return res["return_value"]
