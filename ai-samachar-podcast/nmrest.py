"""Novamira abilities on podcast.rankkking.com over the WordPress Abilities REST API,
signed in with the application password in .wp.env (kept out of config.env)."""
import base64, json, os, urllib.error, urllib.request
DIR = os.path.dirname(os.path.abspath(__file__))
_cred = dict(l.strip().split("=", 1) for l in open(os.path.join(DIR, ".wp.env")) if "=" in l)
_auth = base64.b64encode(f"{_cred['WP_API_USERNAME']}:{_cred['WP_API_PASSWORD']}".encode()).decode()
BASE = "https://podcast.rankkking.com/wp-json/wp-abilities/v1/abilities/"


def run(ability, payload, timeout=600):
    req = urllib.request.Request(BASE + ability + "/run", data=json.dumps({"input": payload}).encode(), method="POST",
                                 headers={"Authorization": "Basic " + _auth, "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()[:300]}"}


def php(code):
    r = run("novamira/execute-php", {"code": code})
    if not r.get("success", True) or "return_value" not in r:
        raise RuntimeError(f"execute-php failed: {json.dumps(r)[:500]}")
    return r["return_value"]
