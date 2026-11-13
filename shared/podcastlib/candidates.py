"""Turn a yt-dlp playlist listing into the videos this run should publish, oldest first."""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcastlib.queue import (  # noqa: E402
    normalize_upload_date,
    parse_playlist_row,
    select_by_duration,
    select_unseen,
    sort_candidates,
)


def read_ids(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path) as handle:
        return [line.strip() for line in handle if line.strip()]


def fill_missing_dates(rows, lookup):
    for row in rows:
        if row.get("upload_date") or lookup is None:
            continue
        try:
            row["upload_date"] = normalize_upload_date(lookup(row["id"]) or "", None)
        except Exception:
            row["upload_date"] = ""
    return sort_candidates(rows)


def ytdlp_upload_date(vid):
    import subprocess
    proc = subprocess.run(
        ["yt-dlp", "--skip-download", "--no-warnings", "--print", "%(upload_date)s",
         "https://www.youtube.com/watch?v=%s" % vid],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""


def rows_from_tsv(text):
    rows = []
    for line in (text or "").splitlines():
        row = parse_playlist_row(line)
        if row:
            rows.append(row)
    return rows


def union_rows(primary, extra):
    """Merge playlist rows with extra rows (channel uploads). One row per id.

    A later row fills in an upload date or title the earlier row does not have.
    """
    by_id = {}
    for row in list(primary) + list(extra):
        current = by_id.get(row["id"])
        if current is None:
            by_id[row["id"]] = dict(row)
            continue
        if not current.get("upload_date") and row.get("upload_date"):
            current["upload_date"] = row["upload_date"]
        if not current.get("title") and row.get("title"):
            current["title"] = row["title"]
        if current.get("seconds") is None and row.get("seconds") is not None:
            current["seconds"] = row["seconds"]
    return sort_candidates(by_id.values())


def human_line(row):
    minutes = "?" if row.get("seconds") is None else str(row["seconds"] // 60)
    date = row.get("upload_date") or "no date"
    title = row.get("title") or ""
    return "%s | %s | %s min | %s" % (row["id"], date, minutes, title)


def main(argv):
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Filter and order playlist rows from stdin.")
    parser.add_argument("--seen", default="")
    parser.add_argument("--min-seconds", type=int, default=0)
    parser.add_argument("--duration-filter", choices=("yes", "no"), default="yes")
    parser.add_argument("--fill-dates", action="store_true")
    parser.add_argument("--format", choices=("ids", "human"), default="ids")
    parser.add_argument("--pending", default="")
    parser.add_argument("--extra", default="", help="TSV of rows already chosen (channel uploads)")
    args = parser.parse_args(argv)
    rows = rows_from_tsv(sys.stdin.read())
    seen = read_ids(args.seen)
    if args.duration_filter == "yes":
        chosen = select_by_duration(rows, seen, args.min_seconds)
    else:
        chosen = select_unseen(rows, seen)
    if args.extra and os.path.isfile(args.extra):
        extra = select_unseen(rows_from_tsv(open(args.extra).read()), seen)
        chosen = union_rows(chosen, extra)
    if args.fill_dates:
        chosen = fill_missing_dates(chosen, ytdlp_upload_date)
    else:
        chosen = sort_candidates(chosen)
    if args.pending:
        os.makedirs(os.path.dirname(os.path.abspath(args.pending)), exist_ok=True)
        with open(args.pending, "w") as handle:
            json.dump(
                [{"vid": row["id"], "upload_date": row.get("upload_date") or "", "title": row.get("title") or ""}
                 for row in chosen],
                handle,
            )
            handle.write("\n")
    for row in chosen:
        print(human_line(row) if args.format == "human" else row["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
