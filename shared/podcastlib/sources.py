"""Run two data sources so one failure does not discard the other."""


def collect_pair(primary, secondary):
    """Call primary and secondary. Exceptions are returned, not raised.

    primary is the source the sheet cannot do without (site stats).
    secondary is optional (OP3). Both are always attempted.
    """
    result = {"primary": None, "secondary": None, "primary_error": None, "secondary_error": None}
    try:
        result["primary"] = primary()
    except Exception as exc:
        result["primary_error"] = exc
    try:
        result["secondary"] = secondary()
    except Exception as exc:
        result["secondary_error"] = exc
    return result


def call_with_retries(fn, attempts=3, sleep=None):
    """Retry a flaky read. The last exception is raised."""
    import time
    sleep = time.sleep if sleep is None else sleep
    attempts = max(1, int(attempts))
    last = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                sleep(min(2 ** attempt, 8))
    raise last
