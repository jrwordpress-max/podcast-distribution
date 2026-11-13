"""Order the videos waiting to be published, and decide how many a run may do."""
import datetime


def normalize_upload_date(upload_date, timestamp=None):
    """Return YYYYMMDD, or '' when neither the date nor a unix timestamp is usable."""
    text = (upload_date or "").strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        compact = text.replace("-", "")
        if len(compact) == 8 and compact.isdigit():
            return compact
    raw = str(timestamp or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    if raw.isdigit() and int(raw) > 0:
        return datetime.datetime.fromtimestamp(int(raw), datetime.timezone.utc).strftime("%Y%m%d")
    return ""


def parse_playlist_row(line):
    """Parse one yt-dlp --print TSV line: id, upload_date, timestamp, duration, title."""
    line = (line or "").rstrip("\n")
    if not line.strip():
        return None
    parts = line.split("\t")
    if len(parts) < 4:
        return None
    vid, upload, timestamp, duration = parts[0].strip(), parts[1], parts[2], parts[3]
    title = "\t".join(parts[4:]) if len(parts) > 4 else ""
    if not vid:
        return None
    seconds = _seconds(duration)
    return {
        "id": vid,
        "upload_date": normalize_upload_date(upload, timestamp),
        "timestamp": timestamp.strip(),
        "seconds": seconds,
        "title": title,
    }


def _seconds(duration):
    text = (duration or "").strip()
    if text in ("", "NA", "None", "nan"):
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def sort_candidates(items):
    """Oldest upload date first. A video with no date waits behind dated ones."""
    return sorted(items, key=lambda item: (not item.get("upload_date"), item.get("upload_date") or "99999999", item["id"]))


def select_by_duration(rows, seen, min_seconds):
    """Drop seen ids and videos shorter than min_seconds (Shorts, premieres with no length)."""
    seen = set(seen or [])
    chosen = []
    for row in rows:
        if not row or row["id"] in seen:
            continue
        if row.get("seconds") is None or row["seconds"] < min_seconds:
            continue
        chosen.append(row)
    return sort_candidates(chosen)


def select_unseen(rows, seen):
    """Playlist ids, with no duration filter (Block Talks publishes every playlist video)."""
    seen = set(seen or [])
    return sort_candidates([row for row in rows if row and row["id"] not in seen])


def catch_up_enabled(value):
    return str(value if value is not None else "1").strip().lower() not in ("0", "false", "no", "off")


def run_limit(backlog, max_per_run, catch_up, catch_up_max):
    """How many successful publishes this run may make.

    CATCH_UP=0 keeps the old MAX_PER_RUN cap. CATCH_UP=1 drains the backlog
    up to CATCH_UP_MAX. CATCH_UP_MAX of 0 (or less) means no extra ceiling.
    """
    backlog = max(0, int(backlog))
    if not catch_up_enabled(catch_up):
        cap = int(max_per_run)
    else:
        cap = int(catch_up_max or 0)
        if cap <= 0:
            cap = backlog
    if cap < 0:
        cap = 0
    return max(0, min(backlog, cap))


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Print how many videos this run may publish.")
    parser.add_argument("--backlog", type=int, required=True)
    parser.add_argument("--max", type=int, required=True)
    parser.add_argument("--catch-up", default="1")
    parser.add_argument("--catch-up-max", type=int, default=25)
    args = parser.parse_args(argv)
    print(run_limit(args.backlog, args.max, args.catch_up, args.catch_up_max))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
