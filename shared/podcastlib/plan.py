"""Assign episode numbers for the current backlog and remember them on disk.

Numbers already on the site are not changed. Pending videos are numbered by
upload date. Re-running keeps a saved number when the site does not already
use it, so a newer episode cannot take the number of an older one that failed.
"""
import json
import os
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcastlib.config import load_config  # noqa: E402
from podcastlib.numbering import assign_episode_numbers, assign_without_site_index  # noqa: E402


def load_pending(path):
    with open(path) as handle:
        data = json.load(handle)
    pending = []
    for item in data:
        vid = item.get("vid") or item.get("id")
        if not vid:
            continue
        pending.append({"vid": vid, "upload_date": item.get("upload_date") or ""})
    return pending


def saved_reservations(show_dir, pending):
    reserved = {}
    for item in pending:
        path = os.path.join(show_dir, "work", item["vid"], "episode_number")
        if not os.path.isfile(path):
            continue
        text = open(path).read().strip()
        if text.isdigit() and int(text) > 0:
            reserved[item["vid"]] = int(text)
    return reserved


def site_index(show_dir, series):
    """Return (numbers, ok). ok is False when the site could not be read."""
    proc = subprocess.run(
        [sys.executable, "publish.py", "episode-index"],
        cwd=show_dir,
        capture_output=True, text=True,
        env=dict(os.environ, EPISODE_INDEX_SERIES=series or ""),
    )
    if proc.returncode != 0:
        return [], False
    text = proc.stdout or ""
    start = text.find("[")
    if start < 0:
        start = text.find("{")
    if start < 0:
        return [], False
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError:
        return [], False
    if isinstance(payload, dict):
        payload = payload.get("episodes") or []
    numbers = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        number = row.get("number")
        try:
            number = int(number)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return numbers, True


def write_numbers(show_dir, assigned):
    for vid, number in assigned.items():
        folder = os.path.join(show_dir, "work", vid)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "episode_number")
        with open(path, "w") as handle:
            handle.write("%s\n" % number)


def plan(show_dir, pending, reserved=None, existing=None, index_ok=True):
    reserved = reserved if reserved is not None else saved_reservations(show_dir, pending)
    if not index_ok:
        return assign_without_site_index(pending, reserved)
    return assign_episode_numbers(existing or [], pending, reserved)


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Write work/<id>/episode_number for the queue.")
    parser.add_argument("--show-dir", required=True)
    parser.add_argument("--pending", required=True)
    args = parser.parse_args(argv)
    show_dir = os.path.abspath(args.show_dir)
    cfg = load_config(show_dir)
    pending = load_pending(args.pending)
    reserved = saved_reservations(show_dir, pending)
    existing, ok = site_index(show_dir, cfg.get("SERIES") or "")
    if not ok:
        print("WARN: could not read episode numbers from the site; keeping saved numbers", file=sys.stderr)
    assigned = plan(show_dir, pending, reserved=reserved, existing=existing, index_ok=ok)
    write_numbers(show_dir, assigned)
    for item in sorted(pending, key=lambda row: (row.get("upload_date") or "99999999", row["vid"])):
        print("%s %s %s" % (item["vid"], item.get("upload_date") or "-", assigned[item["vid"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
