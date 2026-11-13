"""Episode numbers for videos that are not on the site yet.

Already published numbers are left alone. New numbers follow YouTube upload
date, oldest first. A number saved on a previous run is kept when it has not
been taken, so a newer episode published after an older one failed does not
steal the older one's number.
"""


def _as_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _ordered(pending):
    return sorted(pending, key=lambda item: (item.get("upload_date") or "99999999", item["vid"]))


def assign_episode_numbers(existing_numbers, pending, reserved=None):
    """Return {vid: number} for pending videos.

    existing_numbers: numbers already stored on episodes. Not returned and not changed.
    pending: list of {vid, upload_date}.
    reserved: {vid: number} saved the last time this queue was planned.
    """
    reserved = {vid: _as_int(number) for vid, number in (reserved or {}).items()}
    reserved = {vid: number for vid, number in reserved.items() if number}
    used = {_as_int(number) for number in existing_numbers}
    used.discard(0)
    kept = {}
    for item in _ordered(pending):
        number = reserved.get(item["vid"])
        if number and number not in used and number not in kept.values():
            kept[item["vid"]] = number
            used.add(number)
    nxt = max(used, default=0) + 1
    out = dict(kept)
    for item in _ordered(pending):
        if item["vid"] in out:
            continue
        while nxt in used:
            nxt += 1
        out[item["vid"]] = nxt
        used.add(nxt)
        nxt += 1
    return out


def assign_without_site_index(pending, reserved=None):
    """Plan numbers when the site could not be read.

    Saved numbers are kept. Videos without one continue after the highest
    saved number. Nothing is renumbered down to 1.
    """
    reserved = {vid: _as_int(number) for vid, number in (reserved or {}).items()}
    reserved = {vid: number for vid, number in reserved.items() if number}
    out = {}
    used = set()
    for item in _ordered(pending):
        number = reserved.get(item["vid"])
        if number and number not in used:
            out[item["vid"]] = number
            used.add(number)
    start = max(used, default=0)
    for item in _ordered(pending):
        if item["vid"] in out:
            continue
        start += 1
        while start in used:
            start += 1
        out[item["vid"]] = start
        used.add(start)
    return out


def read_saved_number(work_dir, environ=None):
    """The episode number chosen for this video, or 0 when publish.py should use max+1."""
    environ = os_environ() if environ is None else environ
    override = (environ.get("EPISODE_NUMBER") or "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    path = os_path_join(work_dir, "episode_number")
    if os_path_isfile(path):
        text = open(path).read().strip()
        if text.isdigit() and int(text) > 0:
            return int(text)
    return 0


def os_environ():
    import os
    return os.environ


def os_path_join(*parts):
    import os
    return os.path.join(*parts)


def os_path_isfile(path):
    import os
    return os.path.isfile(path)
