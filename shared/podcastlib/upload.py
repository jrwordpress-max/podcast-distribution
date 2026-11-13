"""Upload episode audio. A missing upload URL is a failure, not a skipped step."""
import json
import subprocess
import time


class UploadError(RuntimeError):
    pass


def public_link(link):
    """Describe an upload-link response without its token."""
    if not isinstance(link, dict):
        return repr(link)[:300]
    redacted = {}
    for key, value in link.items():
        if any(word in key.lower() for word in ("token", "secret", "password", "authorization")):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return json.dumps(redacted)[:400]


def request_upload_link(novamira_fn, rel, size):
    res = novamira_fn("novamira/create-upload-link", {
        "path": "wp-content/" + rel,
        "expires_in": 1800,
        "max_bytes": size + 1024,
        "overwrite": True,
    })
    data = res.get("data") if isinstance(res, dict) else None
    if not isinstance(data, dict):
        data = {}
    nested = data.get("data")
    if "upload_url" not in data and isinstance(nested, dict):
        data = nested
    return data


def curl_upload_status(audio, fname, link):
    header = link.get("token_header") or "X-Novamira-Upload-Token"
    proc = subprocess.run(
        ["curl", "-s", "-m", "1500",
         "-H", f"{header}: {link['upload_token']}",
         "-F", f"file=@{audio};filename={fname};type=audio/mp4",
         link["upload_url"], "-w", "\n%{http_code}"],
        capture_output=True, text=True,
    )
    text = (proc.stdout or "").strip()
    code = text.rsplit("\n", 1)[-1] if text else ""
    if not code:
        raise UploadError(
            f"curl produced no HTTP status (exit {proc.returncode}): {(proc.stderr or '')[-200:]}"
        )
    return code


def upload_with_retries(request_link, send_file, attempts=3, sleep=None):
    """Upload audio, retrying when the site returns no URL or the POST is not HTTP 200.

    request_link() -> dict with upload_url and upload_token.
    send_file(link) -> HTTP status string.
    Raises UploadError after the last attempt. Never returns on a missing URL.
    """
    sleep = time.sleep if sleep is None else sleep
    attempts = max(1, int(attempts))
    last = "no attempt"
    for attempt in range(1, attempts + 1):
        try:
            link = request_link() or {}
        except Exception as exc:
            last = f"create-upload-link failed: {exc}"
            if attempt < attempts:
                sleep(min(2 * attempt, 10))
            continue
        if not isinstance(link, dict):
            link = {}
        if not link.get("upload_url") or not link.get("upload_token"):
            last = f"no upload URL from the site (attempt {attempt}/{attempts}): {public_link(link)}"
            if attempt < attempts:
                sleep(min(2 * attempt, 10))
            continue
        try:
            code = str(send_file(link)).strip()
        except Exception as exc:
            last = f"audio upload request failed (attempt {attempt}/{attempts}): {exc}"
            if attempt < attempts:
                sleep(min(2 * attempt, 10))
            continue
        if code == "200":
            return
        last = f"audio upload failed (HTTP {code}) on attempt {attempt}/{attempts}"
        if attempt < attempts:
            sleep(min(2 * attempt, 10))
    raise UploadError(last)
