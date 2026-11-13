"""Offline tests for the publish and sheet-job fixes. No network, no site, no Claude."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from podcastlib.auth import is_auth_failure  # noqa: E402
from podcastlib.basic_spec import build_basic_spec  # noqa: E402
from podcastlib.composio_client import ComposioError, composio  # noqa: E402
from podcastlib.config import load_config  # noqa: E402
from podcastlib.jsonutil import parse_json_object  # noqa: E402
from podcastlib.notify_slack import slack_payload  # noqa: E402
from podcastlib.numbering import assign_episode_numbers, assign_without_site_index  # noqa: E402
from podcastlib.publish_php import render_publish_php  # noqa: E402
from podcastlib.queue import (  # noqa: E402
    normalize_upload_date,
    parse_playlist_row,
    run_limit,
    select_by_duration,
    select_unseen,
)
from podcastlib.report import exit_code_for_failures, run_summary, sheet_summary  # noqa: E402
from podcastlib.shownotes import extract_json_object, publish_with_notes  # noqa: E402
from podcastlib.sources import collect_pair  # noqa: E402
from podcastlib.episode import upload_audio  # noqa: E402
from podcastlib.upload import UploadError, public_link, request_upload_link as link_from_novamira, upload_with_retries  # noqa: E402


class NumberingTests(unittest.TestCase):
    def test_new_episodes_follow_upload_date_and_keep_existing_numbers(self):
        existing = [21, 22, 23]
        pending = [
            {"vid": "newer", "upload_date": "20261110"},
            {"vid": "older", "upload_date": "20261108"},
            {"vid": "newest", "upload_date": "20261112"},
        ]
        assigned = assign_episode_numbers(existing, pending)
        self.assertEqual(assigned, {"older": 24, "newer": 25, "newest": 26})
        self.assertEqual(existing, [21, 22, 23])

    def test_saved_number_is_kept_when_a_newer_episode_was_already_published(self):
        # older failed last run after it had been given 25; newest was published as 26.
        assigned = assign_episode_numbers(
            [24, 26],
            [{"vid": "older", "upload_date": "20261108"}, {"vid": "middle", "upload_date": "20261109"}],
            reserved={"older": 25},
        )
        self.assertEqual(assigned["older"], 25)
        self.assertEqual(assigned["middle"], 27)
        self.assertNotIn(26, assigned.values())

    def test_taken_reservation_does_not_collide(self):
        assigned = assign_episode_numbers(
            [25],
            [{"vid": "a", "upload_date": "20261101"}],
            reserved={"a": 25},
        )
        self.assertEqual(assigned["a"], 26)

    def test_missing_site_index_does_not_restart_at_one(self):
        assigned = assign_without_site_index(
            [{"vid": "keep", "upload_date": "20261102"}, {"vid": "new", "upload_date": "20261101"}],
            reserved={"keep": 30},
        )
        self.assertEqual(assigned["keep"], 30)
        self.assertEqual(assigned["new"], 31)


class QueueTests(unittest.TestCase):
    def test_upload_date_from_timestamp(self):
        self.assertEqual(normalize_upload_date("NA", "1731283200"), "20241111")
        self.assertEqual(normalize_upload_date("20261103", None), "20261103")
        self.assertEqual(normalize_upload_date("2026-11-03", None), "20261103")
        self.assertEqual(normalize_upload_date("", None), "")

    def test_playlist_row_and_duration_filter_orders_by_date(self):
        rows = [
            parse_playlist_row("ccc\t20261112\t\t600\tNew"),
            parse_playlist_row("aaa\t20261101\t\t600\tOld"),
            parse_playlist_row("short\t20261001\t\t30\tShort"),
            parse_playlist_row("seen\t20261002\t\t600\tSeen"),
            parse_playlist_row("premiere\tNA\t\tNA\tSoon"),
        ]
        chosen = select_by_duration(rows, seen=["seen"], min_seconds=180)
        self.assertEqual([row["id"] for row in chosen], ["aaa", "ccc"])

    def test_playlist_without_duration_filter_keeps_shorts(self):
        rows = [parse_playlist_row("short\t20261102\t\t20\tClip"), parse_playlist_row("long\t20261101\t\t600\tShow")]
        chosen = select_unseen(rows, seen=[])
        self.assertEqual([row["id"] for row in chosen], ["long", "short"])

    def test_catch_up_drains_backlog_and_can_be_turned_off(self):
        self.assertEqual(run_limit(15, max_per_run=2, catch_up="0", catch_up_max=25), 2)
        self.assertEqual(run_limit(15, max_per_run=2, catch_up="1", catch_up_max=25), 15)
        self.assertEqual(run_limit(40, max_per_run=2, catch_up="1", catch_up_max=25), 25)
        self.assertEqual(run_limit(40, max_per_run=2, catch_up="1", catch_up_max=0), 40)


class UploadTests(unittest.TestCase):
    def test_missing_upload_url_is_retried_then_raised(self):
        calls = {"n": 0}

        def request_link():
            calls["n"] += 1
            return {"success": True}

        with self.assertRaises(UploadError) as caught:
            upload_with_retries(request_link, lambda link: "200", attempts=3, sleep=lambda _s: None)
        self.assertIn("no upload URL", str(caught.exception))
        self.assertEqual(calls["n"], 3)

    def test_upload_retries_until_http_200(self):
        codes = iter(["503", "200"])

        def send(_link):
            return next(codes)

        upload_with_retries(lambda: {"upload_url": "https://example/up", "upload_token": "secret"},
                            send, attempts=3, sleep=lambda _s: None)

    def test_token_is_not_in_the_error_text(self):
        text = public_link({"upload_url": "", "upload_token": "super-secret", "error": "no"})
        self.assertNotIn("super-secret", text)
        self.assertIn("***", text)

    def test_nested_link_and_upload_audio_fails_closed(self):
        def novamira(_ability, _payload, confirm=False):
            return {"data": {"data": {}}}

        self.assertEqual(link_from_novamira(novamira, "uploads/a.m4a", 10), {})
        with self.assertRaises(UploadError):
            upload_audio(novamira, "uploads/a.m4a", "a.m4a", "audio.m4a", 10, attempts=1, sleep=lambda _s: None)


class PublishPhpTests(unittest.TestCase):
    def test_php_is_idempotent_and_numbers_explicitly(self):
        for show in ("ai-samachar", "block-talks"):
            php = render_publish_php(show, "QUJD")
            self.assertIn("ssp_youtube_id", php)
            self.assertIn("add_option", php)
            self.assertIn("episode_number", php)
            self.assertIn("audio file missing or wrong size", php)
            self.assertIn("meta_input", php)
            self.assertNotIn("__B64__", php)
            self.assertNotIn("__SERIES__", php)
            self.assertNotIn("__MAXSQL__", php)
        ai = render_publish_php("ai-samachar", "QUJD")
        bt = render_publish_php("block-talks", "QUJD")
        self.assertIn("ai-samachar", ai)
        self.assertIn("get_term_by", ai)
        self.assertIn("ss_podcasting_default_series", bt)
        self.assertIn("block-talks", bt)


class ComposioTests(unittest.TestCase):
    def test_empty_output_is_retried_and_does_not_crash_the_parser(self):
        self.assertIsNone(parse_json_object(""))
        self.assertIsNone(parse_json_object("no json here"))
        self.assertEqual(parse_json_object('noise\n{"ok": true}'), {"ok": True})
        calls = {"n": 0}

        def runner(_slug, _path):
            calls["n"] += 1
            if calls["n"] < 3:
                return "", "connection reset by peer", 1
            return json.dumps({"successful": True, "data": {"values": [["2026-11-13"]]}}), "", 0

        data = composio("GOOGLESHEETS_VALUES_GET", {"spreadsheet_id": "x"},
                        runner=runner, sleep=lambda _s: None, attempts=5, work_dir=tempfile.mkdtemp())
        self.assertEqual(data["values"], [["2026-11-13"]])
        self.assertEqual(calls["n"], 3)

    def test_empty_output_after_retries_raises_a_clear_error(self):
        def runner(_slug, _path):
            return "", "network is unreachable", 1

        with self.assertRaises(ComposioError) as caught:
            composio("GOOGLESHEETS_VALUES_GET", {}, runner=runner, sleep=lambda _s: None,
                     attempts=2, work_dir=tempfile.mkdtemp())
        self.assertIn("empty or non-JSON", str(caught.exception))
        self.assertNotIsInstance(caught.exception, json.JSONDecodeError)

    def test_quota_is_retried_and_other_errors_are_not(self):
        calls = {"n": 0}

        def runner(_slug, _path):
            calls["n"] += 1
            if calls["n"] == 1:
                return json.dumps({"successful": False, "error": "Quota exceeded"}), "", 0
            return json.dumps({"successful": True, "data": {"ok": 1}}), "", 0

        data = composio("X", {}, runner=runner, sleep=lambda _s: None, attempts=3, work_dir=tempfile.mkdtemp())
        self.assertEqual(data, {"ok": 1})

        def bad(_slug, _path):
            return json.dumps({"successful": False, "error": "sheet is missing"}), "", 0

        with self.assertRaises(ComposioError):
            composio("X", {}, runner=bad, sleep=lambda _s: None, attempts=5, work_dir=tempfile.mkdtemp())


class SourceTests(unittest.TestCase):
    def test_optional_source_failure_keeps_the_primary(self):
        def op3():
            raise OSError("op3 down")

        result = collect_pair(lambda: {"total": 3}, op3)
        self.assertEqual(result["primary"], {"total": 3})
        self.assertIsNone(result["secondary"])
        self.assertIsInstance(result["secondary_error"], OSError)

    def test_primary_failure_still_attempts_the_secondary(self):
        def site():
            raise RuntimeError("site")

        result = collect_pair(site, lambda: 9)
        self.assertIsNone(result["primary"])
        self.assertEqual(result["secondary"], 9)


class NotesTests(unittest.TestCase):
    def test_auth_markers(self):
        self.assertTrue(is_auth_failure("Failed to authenticate: OAuth session expired"))
        self.assertTrue(is_auth_failure("Please run /login"))
        self.assertTrue(is_auth_failure("Not logged in: claude CLI is not installed"))
        self.assertFalse(is_auth_failure("Published episode 24"))

    def test_extract_json(self):
        self.assertEqual(extract_json_object('sure\n```json\n{"title": "Hi"}\n```'), {"title": "Hi"})

    def test_basic_specs_have_the_fields_publish_requires(self):
        ai = build_basic_spec("ai-samachar", {
            "title": "AI Samachar 10 Nov: Anthropic Buys Gas | 31 AI News",
            "description": "Anthropic ne turbines kharide.\n\nSOURCES\nTools\n1. https://techcrunch.com/story\nDisclosure: AI voice.",
            "chapters": [{"start": 0, "title": "Tools: Muse Ember, Apple packs"}],
        })
        bt = build_basic_spec("block-talks", {
            "title": "TBP Podcast | How Sweatcoin Works",
            "description": "Oleg explains retention.\nhttps://sweatcoin.com\nhttps://www.youtube.com/watch?v=abc",
            "chapters": [{"start": 0, "title": "Introduction"}],
        })
        for spec in (ai, bt):
            for key in ("title", "hook", "learn", "seo", "meta", "kw"):
                self.assertTrue(spec.get(key), key)
        self.assertTrue(ai.get("sources"))
        self.assertEqual(bt["links"], [["sweatcoin.com", "https://sweatcoin.com"]])
        self.assertNotIn("youtube.com", json.dumps(bt["links"]))

    def test_expired_login_still_publishes_with_basic_notes(self):
        folder = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(folder, "work", "vid123"))
            with open(os.path.join(folder, "prompt.md"), "w") as handle:
                handle.write("Video {{VIDEO_ID}} mode {{MODE}}")
            meta = {"title": "How Sweatcoin Works", "description": "A founder interview about retention and growth.", "chapters": []}
            with open(os.path.join(folder, "work", "vid123", "meta.json"), "w") as handle:
                json.dump(meta, handle)

            def claude(_prompt):
                return "Failed to authenticate: OAuth session expired"

            def publish(spec_path, mode):
                with open(spec_path) as handle:
                    spec = json.load(handle)
                self.assertEqual(mode, "publish")
                self.assertTrue(spec["title"])
                with open(os.path.join(folder, "work", "vid123", "result.json"), "w") as handle:
                    json.dump({"ok": True, "episode": 24}, handle)

            status = publish_with_notes(
                folder, "vid123", "publish", cfg={},
                run_claude_fn=claude, run_publish_fn=publish, api_fn=None,
                basic_fn=lambda: build_basic_spec("block-talks", meta),
            )
            self.assertTrue(status["ok"])
            self.assertTrue(status["fallback"])
            self.assertTrue(status["auth_failed"])
            self.assertTrue(os.path.isfile(os.path.join(folder, "work", "vid123", "basic_notes")))
        finally:
            shutil.rmtree(folder)

    def test_claude_success_does_not_use_the_fallback(self):
        folder = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(folder, "work", "vid123"))
            with open(os.path.join(folder, "prompt.md"), "w") as handle:
                handle.write("go")
            with open(os.path.join(folder, "work", "vid123", "meta.json"), "w") as handle:
                json.dump({"title": "T", "description": "D"}, handle)

            def claude(_prompt):
                with open(os.path.join(folder, "work", "vid123", "result.json"), "w") as handle:
                    json.dump({"ok": True}, handle)
                return "Published episode 8"

            called = {"n": 0}

            def publish(_spec, _mode):
                called["n"] += 1

            status = publish_with_notes(
                folder, "vid123", "publish", cfg={},
                run_claude_fn=claude, run_publish_fn=publish, api_fn=None,
            )
            self.assertTrue(status["ok"])
            self.assertFalse(status["fallback"])
            self.assertEqual(called["n"], 0)
            self.assertEqual(status["via"], "claude")
        finally:
            shutil.rmtree(folder)


class ConfigTests(unittest.TestCase):
    def test_environment_and_secret_file_override_the_placeholder(self):
        folder = tempfile.mkdtemp()
        try:
            with open(os.path.join(folder, "config.env"), "w") as handle:
                handle.write('MODE=draft\nSHEET_ID=YOUR_GOOGLE_SHEET_ID\nSITE=example.com\nCHANNEL_MATCH="TBP Podcast"\n')
            with open(os.path.join(folder, "secrets.env"), "w") as handle:
                handle.write("CLAUDE_CODE_OAUTH_TOKEN=from-file\nWP_API_PASSWORD=pw\n")
            env = {"SHEET_ID": "from-env", "CLAUDE_CODE_OAUTH_TOKEN": "from-env"}
            cfg = load_config(folder, env)
            self.assertEqual(cfg["SHEET_ID"], "from-env")
            self.assertEqual(cfg["CLAUDE_CODE_OAUTH_TOKEN"], "from-env")
            self.assertEqual(cfg["WP_API_PASSWORD"], "pw")
            self.assertEqual(cfg["MODE"], "draft")
            self.assertEqual(cfg["CHANNEL_MATCH"], "TBP Podcast")
            self.assertEqual(env["WP_API_PASSWORD"], "pw")
        finally:
            shutil.rmtree(folder)


class ReportTests(unittest.TestCase):
    def test_summary_and_exit_code(self):
        text = run_summary(["a"], ["b", "c"], ["a"])
        self.assertIn("ERROR: 2 video(s) not published: b, c", text)
        self.assertIn("basic show notes", text)
        self.assertNotIn("OK:", text)
        self.assertEqual(exit_code_for_failures(["b"]), 1)
        self.assertEqual(exit_code_for_failures([]), 0)
        self.assertEqual(sheet_summary([]), "OK: sheet update finished")
        self.assertIn("Daily numbers", sheet_summary(["Daily numbers"]))
        self.assertEqual(slack_payload("Block Talks", "Ep 4")["text"], "Block Talks: Ep 4")


class ShellTests(unittest.TestCase):
    def test_environment_wins_when_the_job_starts(self):
        env = dict(os.environ)
        env.update(MODE="draft", SHEET_ID="from-env")
        script = textwrap.dedent("""
            DIR=%s
            source %s
            podcast_load_env
            print -r -- "MODE=$MODE"
            print -r -- "SHEET=$SHEET_ID"
            print -r -- "MATCH=[$CHANNEL_MATCH]"
        """ % (os.path.join(ROOT, "blockopedia-podcast"), os.path.join(ROOT, "shared", "joblib.zsh")))
        proc = subprocess.run(["zsh", "-c", script], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("MODE=draft", proc.stdout)
        self.assertIn("SHEET=from-env", proc.stdout)
        self.assertIn("MATCH=[TBP Podcast]", proc.stdout)

    def test_candidates_cli_orders_oldest_first(self):
        text = "b\t20261102\t\t400\tNew\na\t20261101\t\t400\tOld\nshort\t20261101\t\t20\tSkip\n"
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "shared", "podcastlib", "candidates.py"),
             "--min-seconds", "180", "--duration-filter", "yes", "--format", "ids"],
            input=text, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.split(), ["a", "b"])

    def test_report_cli_exits_non_zero(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "shared", "podcastlib", "report.py"),
             "--published", "a", "--failed", "b", "--fallback", "a"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ERROR:", proc.stdout)


class ImportTests(unittest.TestCase):
    def test_show_modules_import_without_a_password_file(self):
        for folder, name in (("ai-samachar-podcast", "ai_publish"), ("blockopedia-podcast", "bt_publish")):
            show = os.path.join(ROOT, folder)
            sys.path.insert(0, show)
            spec = importlib.util.spec_from_file_location(name, os.path.join(show, "publish.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertIn(module.CFG["MODE"], ("publish", "draft"))
            sys.path.remove(show)
        self.assertEqual(
            importlib.util.spec_from_file_location(
                "bt_publish_check", os.path.join(ROOT, "blockopedia-podcast", "publish.py")
            ).name,
            "bt_publish_check",
        )
        # Block Talks stays in publish mode unless config says otherwise.
        show = os.path.join(ROOT, "blockopedia-podcast")
        sys.path.insert(0, show)
        spec = importlib.util.spec_from_file_location("bt_mode", os.path.join(show, "publish.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.CFG["MODE"], "publish")
        sys.path.remove(show)


if __name__ == "__main__":
    unittest.main()
