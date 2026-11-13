"""Parse a JSON object out of a command's mixed stdout."""
import json


def parse_json_object(out):
    """Return the first JSON object in out, or None when there is nothing to parse.

    An empty string, a non-JSON error, or a truncated body must not raise.
    Callers retry or fail with their own message.
    """
    if not out or "{" not in out:
        return None
    start = out.find("{")
    try:
        return json.loads(out[start:])
    except json.JSONDecodeError:
        return None
