"""One-line success and failure summaries for the check and sheet jobs."""


def run_summary(published, failed, fallbacks):
    published = [item for item in published if item]
    failed = [item for item in failed if item]
    fallbacks = [item for item in fallbacks if item]
    lines = []
    if failed:
        lines.append("ERROR: %d video(s) not published: %s" % (len(failed), ", ".join(failed)))
    if fallbacks:
        lines.append(
            "WARN: %d episode(s) published with basic show notes (Claude unavailable): %s"
            % (len(fallbacks), ", ".join(fallbacks))
        )
    if not failed:
        lines.append("OK: published %d" % len(published))
    return "\n".join(lines)


def sheet_summary(failed_steps):
    failed_steps = [item for item in failed_steps if item]
    if failed_steps:
        return "ERROR: sheet update incomplete: %s" % ", ".join(failed_steps)
    return "OK: sheet update finished"


def exit_code_for_failures(failed):
    return 1 if any(failed) else 0


def _split(value):
    if not value:
        return []
    return [part for part in value.split(",") if part]


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Print the check-run summary and exit 0 or 1.")
    parser.add_argument("--published", default="")
    parser.add_argument("--failed", default="")
    parser.add_argument("--fallback", default="")
    args = parser.parse_args(argv)
    failed = _split(args.failed)
    print(run_summary(_split(args.published), failed, _split(args.fallback)))
    return exit_code_for_failures(failed)


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
