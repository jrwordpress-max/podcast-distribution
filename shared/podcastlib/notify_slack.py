"""Optional Slack (or compatible) webhook. No-op when SLACK_WEBHOOK_URL is unset."""
import json
import os
import sys
import urllib.request


def slack_payload(title, body):
    text = "%s: %s" % (title, body)
    return {"text": text}


def post_slack(title, body, url, opener=None):
    if not url:
        return False
    data = json.dumps(slack_payload(title, body)).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    urlopen = opener or urllib.request.urlopen
    urlopen(req, timeout=20).read()
    return True


def main(argv):
    title = argv[0] if argv else os.environ.get("TITLE", "")
    body = argv[1] if len(argv) > 1 else os.environ.get("BODY", "")
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return 0
    try:
        post_slack(title, body, url)
    except Exception as exc:
        print("WARN: Slack notification failed: %s" % exc, file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
