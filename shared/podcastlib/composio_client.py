"""Composio CLI calls with retries.

An empty stdout (a dropped connection) used to crash json.loads. That is now
retried, and a still-empty response raises ComposioError with the stderr text.
"""
import json
import os
import subprocess
import time

from podcastlib.jsonutil import parse_json_object


class ComposioError(RuntimeError):
    pass


_TRANSIENT = (
    "timeout", "timed out", "connection", "network", "temporarily",
    "econnreset", "enotfound", "eof", "reset by peer", "503", "502", "429",
    "unavailable",
)


def default_runner(slug, path):
    proc = subprocess.run(
        ["composio", "execute", slug, "-d", "@" + path],
        capture_output=True, text=True, timeout=120,
    )
    return proc.stdout or "", proc.stderr or "", proc.returncode


def _backoff(attempt, quota):
    if quota:
        return 30 + 15 * attempt
    return min(2 ** attempt, 32)


def _payload(parsed):
    if parsed.get("storedInFile"):
        path = parsed.get("outputFilePath")
        if not path or not os.path.isfile(path):
            raise ComposioError("Composio stored the result in a file that is missing")
        with open(path) as handle:
            loaded = json.load(handle)
        return loaded.get("data", {})
    if "data" not in parsed:
        raise ComposioError("Composio returned no data: %s" % json.dumps(parsed)[:400])
    return parsed["data"]


def composio(slug, args, runner=None, sleep=None, attempts=5, work_dir=None):
    """Run one Composio tool. Retries empty output, timeouts, quota, and network errors."""
    sleep = time.sleep if sleep is None else sleep
    runner = runner or default_runner
    attempts = max(1, int(attempts))
    work_dir = work_dir or os.getcwd()
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, ".cmp_%s.json" % os.getpid())
    with open(path, "w") as handle:
        json.dump(args, handle)
    last = "no attempt"
    try:
        for attempt in range(attempts):
            try:
                out, err, code = runner(slug, path)
            except subprocess.TimeoutExpired as exc:
                last = "timed out: %s" % exc
                if attempt + 1 < attempts:
                    sleep(_backoff(attempt, quota=False))
                continue
            parsed = parse_json_object(out)
            if parsed is None:
                last = "empty or non-JSON output (exit %s): %s %s" % (
                    code, (out or "")[:200], (err or "")[:200],
                )
                if attempt + 1 < attempts:
                    sleep(_backoff(attempt, quota=False))
                continue
            if parsed.get("successful"):
                return _payload(parsed)
            blob = json.dumps(parsed)
            if "Quota exceeded" in blob:
                last = "quota exceeded"
                if attempt + 1 < attempts:
                    sleep(_backoff(attempt, quota=True))
                continue
            if any(marker in (blob + (err or "")).lower() for marker in _TRANSIENT):
                last = blob[:400]
                if attempt + 1 < attempts:
                    sleep(_backoff(attempt, quota=False))
                continue
            raise ComposioError("%s failed: %s" % (slug, blob[:400]))
        raise ComposioError("%s failed after %d tries: %s" % (slug, attempts, last[:400]))
    finally:
        if os.path.isfile(path):
            os.remove(path)
