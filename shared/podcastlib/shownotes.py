"""Write show notes and publish one episode.

Order, so an expired Claude login never stops the episode:

1. Claude CLI, with CLAUDE_CODE_OAUTH_TOKEN and/or ANTHROPIC_API_KEY exported
   when they are set (config.env, secrets.env, .wp.env, or the environment).
2. If the CLI is missing or its login failed, and ANTHROPIC_API_KEY is set,
   ask the Anthropic API for the spec.json directly.
3. Otherwise build basic notes from the YouTube description and publish those.

A spec Claude managed to write is kept when the failure was not a login failure.
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcastlib.auth import is_auth_failure
from podcastlib.basic_spec import build_basic_spec, show_kind
from podcastlib.config import load_config


def extract_json_object(text):
    if not text:
        raise ValueError("empty model reply")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model reply had no JSON object")
    return json.loads(text[start:end + 1])


def claude_environment(base, cfg):
    env = dict(base)
    token = cfg.get("CLAUDE_CODE_OAUTH_TOKEN")
    key = cfg.get("ANTHROPIC_API_KEY")
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    if key:
        env["ANTHROPIC_API_KEY"] = key
    return env


def run_claude(prompt, env, runner=None):
    argv = [
        "claude", "-p", prompt,
        "--allowedTools", "Bash(python3 publish.py:*)", "Read", "Write", "Edit",
        "--permission-mode", "acceptEdits",
        "--strict-mcp-config", "--no-session-persistence",
    ]
    if runner is not None:
        return runner(argv, env)
    if shutil.which("claude", path=env.get("PATH")) is None and shutil.which("claude") is None:
        return "Not logged in: claude CLI is not installed"
    proc = subprocess.run(argv, capture_output=True, text=True, env=env)
    out = proc.stdout or ""
    err = proc.stderr or ""
    return out + (("\n" + err) if err else "")


def anthropic_spec(api_key, prompt, model=None, urlopen=None):
    model = model or "claude-sonnet-4-5"
    instructions = (
        prompt
        + "\n\nDo not run any tools and do not publish. "
        "Reply with only the spec.json object, no markdown fences."
    )
    body = json.dumps({
        "model": model,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": instructions}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    urlopen = urlopen or urllib.request.urlopen
    raw = json.loads(urlopen(req, timeout=180).read())
    parts = raw.get("content") or []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    return extract_json_object(text)


def _write_spec(path, spec):
    for key in ("title", "hook", "learn", "seo", "meta", "kw"):
        if not spec.get(key):
            raise ValueError("spec is missing %s" % key)
    with open(path, "w") as handle:
        json.dump(spec, handle, indent=1, ensure_ascii=False)
        handle.write("\n")


def publish_with_notes(show_dir, vid, mode, cfg=None, run_claude_fn=None, run_publish_fn=None,
                       api_fn=None, basic_fn=None):
    """Publish one already-fetched video. Returns a status dict and does not exit."""
    cfg = cfg if cfg is not None else load_config(show_dir)
    work = os.path.join(show_dir, "work", vid)
    result_path = os.path.join(work, "result.json")
    spec_path = os.path.join(work, "spec.json")
    marker = os.path.join(work, "basic_notes")
    auth_marker = os.path.join(work, "auth_needed")
    meta_path = os.path.join(work, "meta.json")
    prompt_path = os.path.join(show_dir, "prompt.md")
    kind = show_kind(show_dir)
    status = {"ok": False, "video": vid, "fallback": False, "auth_failed": False, "via": None, "error": None}

    with open(prompt_path) as handle:
        prompt = handle.read().replace("{{VIDEO_ID}}", vid).replace("{{MODE}}", mode)
    with open(meta_path) as handle:
        meta = json.load(handle)
    if basic_fn is None:
        basic_fn = lambda: build_basic_spec(kind, meta)  # noqa: E731

    output = ""
    if run_claude_fn is not None:
        output = run_claude_fn(prompt) or ""
        tail = "\n".join(output.strip().splitlines()[-5:])
        if tail:
            print(tail)
        if os.path.isfile(result_path):
            status.update(ok=True, via="claude")
            _markers(status, marker, auth_marker)
            return status
        if is_auth_failure(output):
            status["auth_failed"] = True

    if status["auth_failed"] or not os.path.isfile(spec_path):
        wrote_api = False
        if cfg.get("ANTHROPIC_API_KEY") and api_fn is not None and (status["auth_failed"] or not os.path.isfile(spec_path)):
            try:
                _write_spec(spec_path, api_fn(prompt))
                wrote_api = True
                status["via"] = "anthropic_api"
                status["fallback"] = False
            except Exception as exc:
                status["api_error"] = str(exc)[:300]
        if not wrote_api and (status["auth_failed"] or not os.path.isfile(spec_path)):
            try:
                _write_spec(spec_path, basic_fn())
                status["fallback"] = True
                status["via"] = "basic"
            except Exception as exc:
                status["error"] = str(exc)[:500]

    if not os.path.isfile(spec_path):
        status["ok"] = False
        if not status["error"]:
            status["error"] = status.get("api_error") or "could not write show notes"
        _markers(status, marker, auth_marker)
        return status

    if not os.path.isfile(result_path):
        err = _publish(run_publish_fn, spec_path, mode)
        if err and status.get("via") != "basic":
            # The written spec did not publish. Basic notes still get the episode out.
            try:
                _write_spec(spec_path, basic_fn())
                status["fallback"] = True
                status["via"] = "basic"
                err = _publish(run_publish_fn, spec_path, mode)
            except Exception as exc:
                err = str(exc)[:500]
        if err and not os.path.isfile(result_path):
            status["error"] = err
    status["ok"] = os.path.isfile(result_path)
    _markers(status, marker, auth_marker)
    if not status["ok"] and not status["error"]:
        status["error"] = (output or "publish did not create result.json")[:500]
    return status


def _publish(run_publish_fn, spec_path, mode):
    try:
        run_publish_fn(spec_path, mode)
    except Exception as exc:
        return str(exc)[:500]
    return None


def _markers(status, marker, auth_marker):
    if status.get("fallback"):
        with open(marker, "w") as handle:
            handle.write(status.get("via") or "basic")
    elif os.path.isfile(marker):
        os.remove(marker)
    if status.get("auth_failed"):
        with open(auth_marker, "w") as handle:
            handle.write("1\n")
    elif os.path.isfile(auth_marker):
        os.remove(auth_marker)


def _default_publish(show_dir, vid):
    def run(spec_path, mode):
        proc = subprocess.run(
            [sys.executable, "publish.py", "publish", vid, spec_path, "--status", mode],
            cwd=show_dir,
        )
        if proc.returncode != 0 or not os.path.isfile(os.path.join(show_dir, "work", vid, "result.json")):
            raise RuntimeError("publish.py exited %s" % proc.returncode)
    return run


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Write show notes and publish one video.")
    parser.add_argument("--show-dir", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args(argv)
    show_dir = os.path.abspath(args.show_dir)
    os.chdir(show_dir)
    cfg = load_config(show_dir)
    env = claude_environment(os.environ, cfg)

    def claude_fn(prompt):
        return run_claude(prompt, env)

    def api_fn(prompt):
        return anthropic_spec(
            cfg.get("ANTHROPIC_API_KEY"), prompt, model=cfg.get("ANTHROPIC_MODEL"),
        )

    status = publish_with_notes(
        show_dir, args.video, args.mode, cfg=cfg,
        run_claude_fn=claude_fn,
        run_publish_fn=_default_publish(show_dir, args.video),
        api_fn=api_fn if cfg.get("ANTHROPIC_API_KEY") else None,
    )
    path = os.path.join(show_dir, "work", args.video, "notes_status.json")
    with open(path, "w") as handle:
        json.dump(status, handle, indent=1)
        handle.write("\n")
    print("STATUS " + json.dumps(status))
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
