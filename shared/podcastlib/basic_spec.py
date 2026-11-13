"""Show notes built from the YouTube title and description, with no Claude call.

Used when the Claude CLI is not logged in, the setup-token has expired, and the
Anthropic API is not available or also failed. The episode still publishes.
"""
import re
import urllib.parse


def show_kind(show_dir):
    name = os_path_basename(show_dir)
    if "samachar" in name:
        return "ai-samachar"
    return "block-talks"


def os_path_basename(path):
    import os
    return os.path.basename(os.path.abspath(path))


def build_basic_spec(kind, meta):
    if kind == "ai-samachar":
        return _ai_samachar(meta)
    return _block_talks(meta)


def _words(text, limit):
    parts = (text or "").split()
    return " ".join(parts[:limit])


def _ai_samachar(meta):
    desc = meta.get("description") or ""
    paras = [p.strip() for p in desc.split("\n\n") if p.strip()]
    hook = next((p for p in paras if not p.startswith("#")), "") or meta.get("title") or "AI Samachar"
    title = meta.get("title") or ""
    match = re.search(r"AI Samachar (\d{1,2} \w{3})", title)
    day = match.group(1) if match else ""
    stories = [s.strip() for s in title.split("|") if s.strip() and not re.search(r"AI News$|AI Samachar", s.strip())]
    sections = [c for c in meta.get("chapters") or [] if ":" in c.get("title", "")]
    learn = [c["title"].split(":", 1)[1].split(",")[0].strip() for c in sections][:6] or stories
    if not learn:
        learn = [_words(title, 12) or "Today's AI news"]
    sources, section = [], ""
    source_text = desc.split("SOURCES", 1)[-1].splitlines() if "SOURCES" in desc else []
    for line in source_text:
        line = line.strip()
        found = re.match(r"\d+\.\s+(https?://\S+)", line)
        if found:
            host = urllib.parse.urlparse(found.group(1)).netloc.removeprefix("www.")
            sources.append([f"{section}: {host}" if section else host, found.group(1)])
        elif line:
            section = line
    disclosure = re.search(r"^Disclosure:\s*(.+)$", desc, re.M)
    built = f"AI Samachar {day}: " + ", ".join(stories) if day else ", ".join(stories)
    if not built.strip(" :"):
        built = title or "AI Samachar"
    spec = {
        "title": built[:100],
        "hook": hook,
        "learn": learn,
        "links": [],
        "sources": sources,
        "seo": ((stories[0] if stories else "AI news")[:45] + " | AI Samachar")[:60],
        "meta": f"AI Samachar {day}: {', '.join(stories)} and more AI news in Hinglish.".strip()[:160],
        "kw": "ai news hindi",
        "chapters": [[c["start"], c["title"].split(":", 1)[0].strip()] for c in meta.get("chapters") or []],
    }
    if not spec["meta"].strip():
        spec["meta"] = (title or "AI Samachar daily AI news in Hinglish.")[:160]
    if disclosure:
        spec["disclosure"] = disclosure.group(1).strip()
    return spec


_BLOCK_HOSTS = ("youtube.com", "youtu.be", "theblockopedia.com")


def _block_talks(meta):
    title = (meta.get("title") or "Block Talks").strip()
    title = re.sub(r"^\s*TBP Podcast\s*[:|\-]\s*", "", title, flags=re.I).strip() or title
    desc = meta.get("description") or ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", desc) if p.strip()]
    hook = _words(paras[0], 45) if paras else _words(title, 30)
    if not hook:
        hook = title
    chapters = meta.get("chapters") or []
    learn = [c["title"].strip() for c in chapters if c.get("title")][:6]
    if not learn:
        for line in desc.splitlines():
            line = line.strip(" -\t")
            if line and not line.startswith("http") and len(line) < 140:
                learn.append(line)
            if len(learn) >= 6:
                break
    if not learn:
        learn = [_words(title, 12)]
    links = []
    seen = set()
    for raw in re.findall(r"https?://\S+", desc):
        url = raw.rstrip(").,]>\"'")
        host = urllib.parse.urlparse(url).netloc.removeprefix("www.").lower()
        if any(host == skip or host.endswith("." + skip) for skip in _BLOCK_HOSTS):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append([host or "Link", url])
    body = title.split("|")[0].strip()
    suffix = " | Block Talks"
    seo = (body[:60 - len(suffix)].rstrip(" -|") + suffix)[:60]
    meta_line = _words(paras[0] if paras else title, 28)[:160]
    if len(meta_line) < 40:
        meta_line = (meta_line + " A Block Talks interview.")[:160]
    words = re.findall(r"[A-Za-z0-9]+", body.lower())
    kw = " ".join(words[:3]) or "block talks"
    spec = {
        "title": title[:90],
        "hook": hook,
        "learn": learn[:6],
        "links": links,
        "seo": seo,
        "meta": meta_line[:160],
        "kw": kw[:40],
    }
    if chapters:
        spec["chapters"] = [[c["start"], c["title"].strip()] for c in chapters]
    return spec
