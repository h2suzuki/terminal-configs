#!/usr/bin/env python3
"""Credential handling and fixed-endpoint tests; no live API requests."""

import asyncio
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import termios
import time
import unittest
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("jev", str(ROOT / "files/jev"))
spec = importlib.util.spec_from_loader(loader.name, loader)
jev = importlib.util.module_from_spec(spec)
loader.exec_module(jev)
OS_CREDENTIAL_DIR = jev.credential_dir
KEY = "test-only-key-NOT-a-real-credential"
REQUEST = {
    "state": "hello",
    "questions": {"urgent": {"type": "noul", "instructions": "urgent?"}},
}


class JevTests(unittest.TestCase):
    def test_api_key_without_action_shows_help(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "files/jev"), "api-key"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn("Save or replace a key", result.stdout)
        self.assertIn("Delete the saved API key", result.stdout)
        self.assertNotIn("key_command", result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "typesafe"
        self.patch = patch.object(jev, "credential_dir", return_value=self.directory)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def save_key(self):
        with (
            patch.object(jev, "test_api", new_callable=AsyncMock),
            patch.object(jev.sys.stdin, "isatty", return_value=True),
            patch.object(jev.getpass, "getpass", return_value=KEY),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            jev.api_key()
        self.assertEqual(output.getvalue(), "API is set\n")

    def test_login_private_storage_and_replacement(self):
        self.save_key()
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(
            (self.directory / "credentials.json").stat().st_mode & 0o777, 0o600
        )
        self.assertEqual(jev.load_key(), KEY)
        self.save_key()
        self.assertEqual(
            list(self.directory.iterdir()), [self.directory / "credentials.json"]
        )

    def test_status_unset_cleared_or_corrupt_never_calls_api(self):
        for state in ("unset", "cleared", "corrupt"):
            with self.subTest(state=state):
                if state != "unset":
                    self.save_key()
                    if state == "cleared":
                        with contextlib.redirect_stdout(io.StringIO()):
                            jev.remove_key()
                    else:
                        (self.directory / "credentials.json").write_text("{broken")
                with (
                    patch.object(sys, "argv", ["jev", "api-key", "status"]),
                    patch.object(jev, "create_client") as factory,
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    contextlib.redirect_stderr(io.StringIO()) as error,
                ):
                    self.assertEqual(jev.main(), 1)
                factory.assert_not_called()
                self.assertEqual(output.getvalue(), "")
                expected = (
                    "Invalid credential file"
                    if state == "corrupt"
                    else "No API key saved"
                )
                self.assertIn(expected, error.getvalue())
                self.assertNotIn(KEY, error.getvalue())

    def test_login_requires_terminal(self):
        with (
            patch.object(jev.sys.stdin, "isatty", return_value=False),
            self.assertRaises(jev.JevError),
        ):
            jev.api_key()
        self.assertFalse(self.directory.exists())

    def test_set_verifies_candidate_before_writing(self):
        from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

        candidate = "new-test-key"
        for saved in (False, True):
            for outcome in (401, 403, 429, 503, "network", "bad-answer", 200):
                with self.subTest(saved=saved, outcome=outcome):
                    path = self.directory / "credentials.json"
                    if path.exists():
                        path.unlink()
                    if saved:
                        self.save_key()
                    original = path.read_bytes() if saved else None

                    def respond(request, path=path, original=original, outcome=outcome):
                        self.assertEqual(
                            request.headers["Authorization"], "Bearer " + candidate
                        )
                        self.assertEqual(
                            path.read_bytes() if path.exists() else None, original
                        )
                        if outcome == "network":
                            raise httpx2.ConnectError(candidate)
                        body = response_body()
                        if outcome == "bad-answer":
                            body["answers"] = {}
                        return httpx2.Response(
                            outcome if isinstance(outcome, int) else 200, json=body
                        )

                    def make_client(key, respond=respond):
                        self.assertEqual(key, candidate)
                        client = AsyncTypeSafeClient(
                            api_key=key,
                            transport=httpx2.MockTransport(respond),
                            retry=RetryPolicy(max_retries=0),
                        )
                        return client

                    with (
                        patch.object(sys, "argv", ["jev", "api-key", "set"]),
                        patch.object(jev.sys.stdin, "isatty", return_value=True),
                        patch.object(jev.getpass, "getpass", return_value=candidate),
                        patch.object(
                            jev, "create_client", side_effect=make_client
                        ) as factory,
                        patch.object(
                            jev,
                            "load_key",
                            side_effect=AssertionError("must test candidate"),
                        ),
                        contextlib.redirect_stdout(io.StringIO()) as output,
                        contextlib.redirect_stderr(io.StringIO()) as error,
                    ):
                        self.assertEqual(jev.main(), 0 if outcome == 200 else 1)
                    factory.assert_called_once()
                    self.assertNotIn(candidate, output.getvalue() + error.getvalue())
                    if outcome == 200:
                        self.assertEqual(jev.load_key(), candidate)
                        self.assertEqual(output.getvalue(), "API is set\n")
                        self.assertEqual(error.getvalue(), "")
                    else:
                        self.assertEqual(
                            path.read_bytes() if path.exists() else None, original
                        )
                        self.assertEqual(output.getvalue(), "")
                        self.assertTrue(error.getvalue())

    def test_rejected_input_explains_reason_and_preserves_saved_key(self):
        self.save_key()
        for value, reason in (
            (KEY + " extra", "contains whitespace"),
            (KEY + "\x1b", "unsupported characters"),
            (KEY + "あ", "unsupported characters"),
            (KEY * 200, "too long"),
        ):
            with (
                self.subTest(reason=reason),
                patch.object(jev.sys.stdin, "isatty", return_value=True),
                patch.object(jev.getpass, "getpass", return_value=value),
                self.assertRaisesRegex(jev.JevError, reason) as error,
            ):
                jev.api_key()
            self.assertNotIn(KEY, str(error.exception))
            self.assertEqual(jev.load_key(), KEY)

    def test_empty_key_input_cancels_silently(self):
        for saved in (False, True):
            if saved:
                self.save_key()
            for value in ("", "   "):
                with (
                    self.subTest(saved=saved, value=value),
                    patch.object(sys, "argv", ["jev", "api-key", "set"]),
                    patch.object(jev.sys.stdin, "isatty", return_value=True),
                    patch.object(jev.getpass, "getpass", return_value=value),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    contextlib.redirect_stderr(io.StringIO()) as error,
                ):
                    self.assertEqual(jev.main(), 0)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(error.getvalue(), "")
                if saved:
                    self.assertEqual(jev.load_key(), KEY)
                else:
                    self.assertFalse(self.directory.exists())

    def test_hidden_input_failure_does_not_fall_back(self):
        def unavailable(prompt):
            warnings.warn("Cannot control echo", getpass_warning)
            self.fail("must not fall back to visible input")

        getpass_warning = jev.getpass.GetPassWarning
        with (
            patch.object(jev.sys.stdin, "isatty", return_value=True),
            patch.object(jev.getpass, "getpass", side_effect=unavailable),
            self.assertRaisesRegex(jev.JevError, "Hidden input is unavailable"),
        ):
            jev.api_key()
        self.assertFalse(self.directory.exists())

    def test_real_terminal_disables_echo(self):
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).resolve()),
                "--key-fixture",
                str(self.directory),
            ],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
        output = b""
        try:
            deadline = time.monotonic() + 10
            while b"TypeSafe API key:" not in output:
                self.assertLess(
                    time.monotonic(), deadline, "hidden prompt did not appear"
                )
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 4096)
            self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
            os.write(master, KEY.encode() + b"\n")
            self.assertEqual(process.wait(timeout=10), 0)
            while select.select([master], [], [], 0.1)[0]:
                output += os.read(master, 4096)
            self.assertNotIn(KEY.encode(), output)
            self.assertEqual(jev.load_key(), KEY)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_public_credential_is_rejected(self):
        self.save_key()
        (self.directory / "credentials.json").chmod(0o644)
        with self.assertRaises(jev.JevError):
            jev.load_key()

    def test_symlink_credential_is_rejected(self):
        self.save_key()
        target = self.directory / "credentials.json"
        target.rename(self.directory / "original")
        target.symlink_to("original")
        with self.assertRaises(jev.JevError):
            jev.load_key()
        with self.assertRaises(jev.JevError):
            self.save_key()

    def test_symlink_directory_is_rejected(self):
        self.save_key()
        real = self.directory.with_name("real")
        self.directory.rename(real)
        self.directory.symlink_to(real)
        with self.assertRaises(jev.JevError):
            jev.load_key()

    def test_invalid_stored_key_never_appears_in_error(self):
        self.save_key()
        (self.directory / "credentials.json").write_text(
            json.dumps({"api_key": KEY + "\n"})
        )
        with self.assertRaises(jev.JevError) as result:
            jev.load_key()
        self.assertNotIn(KEY, str(result.exception))

    def test_credential_location_uses_os_user(self):
        with patch.object(jev.pwd, "getpwuid") as user:
            user.return_value.pw_dir = "/actual-user"
            self.assertEqual(OS_CREDENTIAL_DIR(), Path("/actual-user/.config/typesafe"))

    def test_clear_never_shows_key(self):
        self.save_key()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            jev.remove_key()
            jev.remove_key()
        self.assertNotIn(KEY, output.getvalue())
        self.assertFalse((self.directory / "credentials.json").exists())

    def save_profile_key(self, profile, key):
        with (
            patch.object(jev, "test_api", new_callable=AsyncMock) as tested,
            patch.object(jev.sys.stdin, "isatty", return_value=True),
            patch.object(jev.getpass, "getpass", return_value=key),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            jev.api_key(profile)
        self.assertEqual(tested.call_args.kwargs["key"], key)

    def test_profiles_share_one_private_file_like_aws_credentials(self):
        """A verification key sits beside the production key; neither replaces the other."""
        self.save_key()
        self.save_profile_key("verify", "verify-only-key")
        path = self.directory / "credentials.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            json.loads(path.read_text()),
            {"default": {"api_key": KEY}, "verify": {"api_key": "verify-only-key"}},
        )
        self.assertEqual(jev.load_key(), KEY)
        self.assertEqual(jev.load_key("verify"), "verify-only-key")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_a_single_key_file_is_the_default_profile(self):
        self.directory.mkdir(mode=0o700)
        path = self.directory / "credentials.json"
        path.write_text(json.dumps({"api_key": KEY}))
        path.chmod(0o600)
        self.assertEqual(jev.load_key(), KEY)
        with self.assertRaisesRegex(jev.JevError, "profile verify.*--profile verify"):
            jev.load_key("verify")
        self.save_profile_key("verify", "verify-only-key")
        self.assertEqual(jev.load_key(), KEY)
        self.assertEqual(jev.load_key("verify"), "verify-only-key")

    def test_clear_removes_only_the_named_profile(self):
        self.save_key()
        self.save_profile_key("verify", "verify-only-key")
        with contextlib.redirect_stdout(io.StringIO()):
            jev.remove_key("verify")
        self.assertEqual(jev.load_key(), KEY)
        with self.assertRaisesRegex(jev.JevError, "profile verify"):
            jev.load_key("verify")
        with contextlib.redirect_stdout(io.StringIO()):
            jev.remove_key()
        self.assertFalse((self.directory / "credentials.json").exists())

    def test_profile_names_are_plain_words(self):
        for name in ("", "../x", "a b", "x" * 65, "日本"):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(jev.JevError, "Profile name"),
            ):
                jev.load_key(name)

    def test_every_command_accepts_an_optional_profile(self):
        parser, _ = jev.build_parser()
        for argv in (
            ["hello"],
            ["serve"],
            ["api-key", "set"],
            ["api-key", "clear"],
            ["api-key", "status"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(parser.parse_args(argv).profile, "default")
                self.assertEqual(
                    parser.parse_args([*argv, "--profile", "verify"]).profile, "verify"
                )


def response_body(model="jev-latest", count=1):
    return {
        "model": model,
        "usage": {"input_tokens": count},
        "answers": {"test": {"type": "noul", "noul": 0.99}},
    }


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.code = 200
        self.body = response_body()
        self.transport = httpx2.MockTransport(self.respond)
        self.real_http = httpx2.AsyncClient
        self.clients = []

        def make_http(**kwargs):
            self.http_options = kwargs
            client = self.real_http(transport=self.transport, **kwargs)
            self.clients.append(client)
            return client

        self.factory_patch = patch.object(httpx2, "AsyncClient", side_effect=make_http)
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.key_patch = patch.object(jev, "load_key", return_value=KEY)
        self.key_loader = self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.session = jev.JevSession()
        self.addAsyncCleanup(self.session.close)

    def respond(self, request):
        self.requests.append(request)
        return httpx2.Response(
            self.code, json=self.body, headers={"Location": "https://evil.invalid"}
        )

    async def test_sdk_posts_and_reuses_client_ignoring_environment(self):
        with patch.dict(
            os.environ,
            {
                "TYPESAFE_BASE_URL": "https://evil.invalid",
                "HTTPS_PROXY": "http://evil.invalid",
                "TYPESAFE_API_KEY": "wrong-key",
                "TYPESAFE_DEFAULT_MODEL": "wrong-model",
            },
        ):
            await self.session.evaluate(**REQUEST)
            await self.session.evaluate(**REQUEST)
        self.factory.assert_called_once()
        self.key_loader.assert_called_once()
        self.assertFalse(self.http_options["trust_env"])
        self.assertFalse(self.http_options["follow_redirects"])
        self.assertEqual(len(self.requests), 2)
        for request in self.requests:
            self.assertEqual(str(request.url), jev.ENDPOINT)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["Authorization"], "Bearer " + KEY)
            self.assertEqual(json.loads(request.content)["model"], "jev-latest")
        await self.session.close()
        self.assertTrue(self.clients[0].is_closed)
        self.assertIsNone(self.session.key)

    async def test_diagnostics_hide_error_bodies(self):
        for code, message in [
            (401, "jev api-key set"),
            (403, "permissions"),
            (429, "quota"),
            (503, "Retry later"),
            (307, "redirect refused"),
        ]:
            with self.subTest(code=code):
                self.code, self.body = code, {"error": KEY}
                session = jev.JevSession()
                self.addAsyncCleanup(session.close)
                with self.assertRaisesRegex(jev.JevError, message) as error:
                    await session.evaluate(**REQUEST)
                self.assertNotIn(KEY, str(error.exception))
        self.assertEqual(len(self.requests), 5)  # no redirects or retries

    def error_log(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "api-errors"
        logdir = patch.object(jev, "error_log_dir", return_value=folder)
        logdir.start()
        self.addCleanup(logdir.stop)
        return folder

    async def refused(self, **request):
        session = jev.JevSession()
        self.addAsyncCleanup(session.close)
        with self.assertRaisesRegex(jev.JevError, "HTTP 403") as error:
            await session.evaluate(**(request or REQUEST))
        return str(error.exception)

    async def test_403_saves_request_and_response_without_the_key(self):
        """A key-valid 403 on one payload could not be told from a revoked key without the response body."""
        folder = self.error_log()
        self.code, self.body = 403, {"error": "blocked for " + KEY}
        message = await self.refused()
        (saved,) = folder.iterdir()
        self.assertIn(str(saved), message)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        text = saved.read_text()
        self.assertNotIn(KEY, text)
        record = json.loads(text)
        self.assertEqual(record["status"], 403)
        self.assertEqual(record["endpoint"], "POST " + jev.ENDPOINT)
        self.assertEqual(record["request"]["state"], "hello")
        self.assertEqual(record["request"]["questions"], REQUEST["questions"])
        self.assertIn("[REDACTED]", json.dumps(record["body"]))
        self.assertEqual(record["headers"]["location"], "https://evil.invalid")

    async def test_403_log_keeps_only_the_newest_records(self):
        folder = self.error_log()
        self.code = 403
        with patch.object(jev, "ERROR_LOG_KEEP", 2):
            for n in range(3):
                await self.refused(state=f"call {n}", questions=REQUEST["questions"])
        states = sorted(json.loads(p.read_text())["request"]["state"] for p in folder.iterdir())
        self.assertEqual(states, ["call 1", "call 2"])

    async def test_403_log_truncates_a_large_request_and_body(self):
        folder = self.error_log()
        self.code, self.body = 403, {"error": "x" * (jev.ERROR_LOG_PART_BYTES * 2)}
        await self.refused(state="y" * (jev.ERROR_LOG_PART_BYTES * 2), questions=REQUEST["questions"])
        (saved,) = folder.iterdir()
        self.assertLess(saved.stat().st_size, jev.ERROR_LOG_PART_BYTES * 3)
        self.assertTrue(json.loads(saved.read_text())["truncated"])

    async def test_403_log_is_skipped_when_the_disk_is_nearly_full(self):
        folder = self.error_log()
        self.code = 403
        low = jev.shutil._ntuple_diskusage(10**12, 10**12, jev.ERROR_LOG_MIN_FREE - 1)
        with patch.object(jev.shutil, "disk_usage", return_value=low):
            message = await self.refused()
        self.assertFalse(folder.exists() and any(folder.iterdir()))
        self.assertIn("permissions", message)

    async def test_unwritable_403_log_keeps_the_error_message(self):
        self.error_log()
        self.code = 403
        with patch.object(jev.Path, "write_text", side_effect=OSError("read-only")):
            message = await self.refused()
        self.assertIn("permissions", message)

    async def test_other_errors_are_not_saved(self):
        folder = self.error_log()
        for code in (401, 429, 503):
            self.code = code
            session = jev.JevSession()
            self.addAsyncCleanup(session.close)
            with self.assertRaises(jev.JevError):
                await session.evaluate(**REQUEST)
        self.assertFalse(folder.exists())

    def request_file(self, content, run="fixed", name="case__0.json"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "backtest" / jev.EVALUATE_FILE_DIR / run / name
        path.parent.mkdir(parents=True)
        path.write_text(
            content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        )
        return path

    async def test_evaluate_file_sends_the_file_exactly(self):
        """Copied by a model, Japanese state text changed glyphs (方針→方针); the file must reach Jev unchanged."""
        state = {"text": "方針・立脚・叩き台・残骸\t`x` end", "list": ["?", "\\u2028"]}
        path = self.request_file(
            {"case": "c", "request": 0, "state": state, "questions": REQUEST["questions"]}
        )
        result = await self.session.evaluate_file(str(path))
        sent = json.loads(self.requests[0].content)
        self.assertEqual((sent["state"], sent["questions"]), (state, REQUEST["questions"]))
        self.assertEqual(result["file"], str(path.resolve()))
        canonical = json.dumps(
            {"state": state, "questions": REQUEST["questions"]},
            sort_keys=True,
            ensure_ascii=False,
        )
        self.assertEqual(result["sha256"], hashlib.sha256(canonical.encode()).hexdigest())
        self.assertEqual(result["answers"], response_body()["answers"])

    async def test_evaluate_file_refuses_paths_outside_the_request_directory(self):
        inside = self.request_file({"state": "s", "questions": REQUEST["questions"]})
        outside = inside.parents[2] / "secret.json"
        outside.write_text(json.dumps({"state": "s", "questions": REQUEST["questions"]}))
        link = inside.parent / "link.json"
        link.symlink_to(outside)
        deep = inside.parent / "a" / "b" / "deep.json"
        deep.parent.mkdir(parents=True)
        deep.write_text(inside.read_text())
        for path in (outside, link, deep, inside.parent, inside.parent / "missing.json"):
            with self.subTest(path=path), self.assertRaisesRegex(
                jev.JevError, jev.EVALUATE_FILE_DIR
            ):
                await self.session.evaluate_file(str(path))
        self.assertEqual(self.requests, [])

    async def test_evaluate_file_refuses_invalid_or_oversized_content(self):
        for content in ("not json", json.dumps(["state"]), json.dumps({"state": "s"})):
            with self.subTest(content=content), self.assertRaises(jev.JevError):
                await self.session.evaluate_file(str(self.request_file(content)))
        big = self.request_file(
            {"state": "x" * jev.MAX_BYTES, "questions": REQUEST["questions"]}
        )
        with self.assertRaisesRegex(jev.JevError, "8 MiB"):
            await self.session.evaluate_file(str(big))
        self.assertEqual(self.requests, [])

    async def test_reflected_key_is_redacted(self):
        self.body = response_body(model=KEY)
        result = await self.session.evaluate(**REQUEST)
        self.assertEqual(result["model"], "[REDACTED]")

    async def test_invalid_request_precedes_credential_read(self):
        for request in [
            REQUEST | {"state": None},
            REQUEST | {"questions": {}},
            REQUEST | {"model": ""},
        ]:
            with self.assertRaises(jev.JevError):
                await self.session.evaluate(**request)
        self.key_loader.assert_not_called()
        self.factory.assert_not_called()

    async def test_missing_key_can_be_fixed_without_restarting_server(self):
        self.key_loader.side_effect = [
            jev.JevError("No API key saved. Run jev api-key set."),
            KEY,
        ]
        with self.assertRaisesRegex(jev.JevError, "jev api-key set"):
            await self.session.evaluate(**REQUEST)
        self.factory.assert_not_called()
        await self.session.evaluate(**REQUEST)

    async def test_connection_error_is_safe(self):
        with (
            patch.object(
                self.transport,
                "handle_async_request",
                side_effect=httpx2.ConnectError(KEY),
            ),
            self.assertRaisesRegex(jev.JevError, "connectivity") as error,
        ):
            await self.session.evaluate(**REQUEST)
        self.assertNotIn(KEY, str(error.exception))

    async def test_cli_test_checks_answer_and_closes_client(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            await jev.test_api(show_exchange=True)
        query, response = output.getvalue().split("\nResponse:\n")
        self.assertTrue(query.startswith("Query:\n"))
        self.assertEqual(
            json.loads(query.removeprefix("Query:\n")),
            json.loads(self.requests[0].content),
        )
        self.assertTrue(response.endswith("\n\nHello! Jev is ready.\n"))
        self.assertEqual(
            json.loads(response.removesuffix("\n\nHello! Jev is ready.\n"))["answers"],
            self.body["answers"],
        )
        self.assertNotIn(KEY, output.getvalue())
        self.assertTrue(self.clients[0].is_closed)
        self.body = response_body() | {"answers": {}}
        with self.assertRaisesRegex(jev.JevError, "missing or invalid"):
            await jev.test_api()
        self.assertTrue(self.clients[1].is_closed)

    async def test_status_valid_and_rejected_keys(self):
        for status in (200, 401, 403, 429, 503):
            with self.subTest(status=status):
                self.code = status
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    if status == 200:
                        await jev.api_key_status()
                        self.assertEqual(output.getvalue(), "API key is valid.\n")
                    else:
                        with self.assertRaisesRegex(
                            jev.JevError, f"HTTP {status}"
                        ) as error:
                            await jev.api_key_status()
                        self.assertNotIn(KEY, str(error.exception))
                        self.assertEqual(output.getvalue(), "")
                        if status == 401:
                            self.assertIn("invalid", str(error.exception))
                            self.assertNotIn("expired", str(error.exception))
                self.assertNotIn(KEY, output.getvalue())
                self.assertTrue(self.clients[-1].is_closed)
        self.assertEqual(len(self.requests), 5)

    async def test_status_network_error_does_not_label_key_invalid(self):
        with (
            patch.object(
                self.transport,
                "handle_async_request",
                side_effect=httpx2.ConnectError(KEY),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaisesRegex(jev.JevError, "connectivity") as error,
        ):
            await jev.api_key_status()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(KEY, str(error.exception))
        self.assertNotIn("invalid", str(error.exception).lower())
        self.assertTrue(self.clients[-1].is_closed)

    async def test_mcp_schema_and_safe_error(self):
        self.key_loader.side_effect = jev.JevError(
            "No API key saved. Run jev api-key set."
        )
        async with Client(jev.create_server()) as client:
            listed = await client.list_tools()
            self.assertEqual(
                [tool.name for tool in listed.tools],
                ["evaluate", "evaluate_file", "context_gate"],
            )
            properties = listed.tools[0].input_schema["properties"]
            self.assertEqual(set(properties), {"state", "questions", "model", "profile"})
            self.assertEqual(
                set(listed.tools[1].input_schema["properties"]), {"path", "profile"}
            )
            result = await client.call_tool("evaluate", REQUEST)
            self.assertTrue(result.is_error)
            self.assertIn("jev api-key set", str(result.content))

    async def test_each_profile_uses_its_own_key(self):
        """Verification queries name their profile; the production key is never used for them."""
        verify = jev.JevSession(profile="verify")
        self.addAsyncCleanup(verify.close)
        await verify.evaluate(**REQUEST)
        await self.session.evaluate(**REQUEST)
        self.assertEqual(
            [c.args for c in self.key_loader.call_args_list], [("verify",), ("default",)]
        )

    async def test_mcp_profile_argument_and_server_default(self):
        """A tool call's profile wins; otherwise the profile the server was started with."""
        for server_profile, argument, expected in (
            ("default", {}, "default"),
            ("default", {"profile": "verify"}, "verify"),
            ("verify", {}, "verify"),
        ):
            with self.subTest(server=server_profile, argument=argument):
                self.key_loader.reset_mock()
                async with Client(jev.create_server(server_profile)) as client:
                    result = await client.call_tool("evaluate", {**REQUEST, **argument})
                    self.assertFalse(result.is_error, result.content)
                self.assertEqual(self.key_loader.call_args.args, (expected,))

    async def test_mcp_rejects_a_bad_profile_name_without_reading_keys(self):
        async with Client(jev.create_server()) as client:
            result = await client.call_tool("evaluate", {**REQUEST, "profile": "../x"})
        self.assertTrue(result.is_error)
        self.assertIn("Profile name", str(result.content))
        self.key_loader.assert_not_called()


    async def test_rejected_key_is_not_retried_until_the_saved_key_changes(self):
        stamp = patch.object(jev, "credential_stamp", return_value=("inode", 1))
        stamp.start()
        self.addCleanup(stamp.stop)
        self.code = 401
        for _ in range(2):
            with self.assertRaisesRegex(jev.JevError, "HTTP 401"):
                await self.session.evaluate(**REQUEST)
        self.assertEqual(len(self.requests), 1)  # the second call fails without asking
        jev.credential_stamp.return_value = ("inode", 2)  # jev api-key set replaced the file
        self.code = 200
        await self.session.evaluate(**REQUEST)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.key_loader.call_count, 2)

    async def test_saved_key_change_is_picked_up_by_the_running_server(self):
        stamp = patch.object(jev, "credential_stamp", return_value=("inode", 1))
        stamp.start()
        self.addCleanup(stamp.stop)
        await self.session.evaluate(**REQUEST)
        jev.credential_stamp.return_value = ("inode", 2)
        await self.session.evaluate(**REQUEST)
        self.assertEqual(self.key_loader.call_count, 2)
        self.assertEqual(self.factory.call_count, 2)

    async def test_rate_limit_backs_off_before_asking_again(self):
        now = patch.object(jev.time, "monotonic", return_value=1000.0)
        now.start()
        self.addCleanup(now.stop)
        self.code = 429
        with self.assertRaisesRegex(jev.JevError, "HTTP 429"):
            await self.session.evaluate(**REQUEST)
        with self.assertRaisesRegex(jev.JevError, "HTTP 429.*after"):
            await self.session.evaluate(**REQUEST)
        self.assertEqual(len(self.requests), 1)
        jev.time.monotonic.return_value = 1000.0 + jev.BACKOFF_S + 1
        self.code = 200
        await self.session.evaluate(**REQUEST)
        self.assertEqual(len(self.requests), 2)

    async def test_real_stdio_multiple_calls_in_one_process(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-I", "-B", str(Path(__file__).resolve()), "--serve-fixture"],
        )
        async with Client(params) as client:
            for expected_count in (1, 2):
                result = await client.call_tool("evaluate", REQUEST)
                self.assertFalse(result.is_error)
                self.assertEqual(
                    result.structured_content["usage"]["input_tokens"], expected_count
                )
                self.assertNotIn(KEY, str(result.content))


class ContextGateTests(unittest.IsolatedAsyncioTestCase):
    """The hook intake: the connected server itself judges the commit; no process is started for it."""

    respond = SessionTests.respond

    async def asyncSetUp(self):
        await SessionTests.asyncSetUp(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        env = patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            },
        )  # fmt: skip
        env.start()
        self.addCleanup(env.stop)
        module = patch.object(jev, "GATE_MODULE", ROOT / "files" / "jev_context_gate.py")
        module.start()
        self.addCleanup(module.stop)
        self.gate = jev.load_gate()
        log = patch.object(self.gate, "LOG", str(self.root / "log.jsonl"))
        log.start()
        self.addCleanup(log.stop)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        (self.repo / "README.md").write_text("# Tool\n\n## Sign in\n\nSign in once.\n\n## Update\n\nPull.\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "init"], check=True)
        (self.repo / "README.md").write_text(
            "# Tool\n\n## Sign in\n\nSign in once.\n\nMAINTAINER rule.\n\n## Update\n\nPull.\n"
        )
        self.spawned = []
        real = subprocess.Popen

        def spy(*args, **kwargs):
            self.spawned.append(str((args[0] if args else kwargs["args"])[0]))
            return real(*args, **kwargs)

        popen = patch.object(subprocess, "Popen", side_effect=spy)
        popen.start()
        self.addCleanup(popen.stop)

    async def call(self, command, tool_input=None):
        arguments = {"cwd": str(self.repo), "session_id": "sess-1"}
        if tool_input is None:
            arguments["command"] = command  # the Claude Code form
        else:
            arguments["tool_input"] = tool_input  # the Codex form
        async with Client(jev.create_server()) as client:
            result = await client.call_tool("context_gate", arguments)
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(set(self.spawned) - {"git"}, set())  # judged here, not in a new process
        return json.loads(result.content[0].text)

    async def test_misfit_is_denied_by_the_connected_server(self):
        self.body = response_body() | {"answers": {"fits_0_0": {"type": "noul", "noul": 0.1}}}
        output = await self.call('git commit -m "x" -- README.md')
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("MAINTAINER rule.", decision["permissionDecisionReason"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(json.loads(self.requests[0].content)["model"], "jev-latest")

    async def test_codex_tool_input_object_and_text_are_accepted(self):
        self.body = response_body() | {"answers": {"fits_0_0": {"type": "noul", "noul": 0.9}}}
        command = {"command": 'git commit -m "x" -- README.md'}
        self.assertEqual(await self.call("", tool_input=command), {})
        self.assertEqual(await self.call("", tool_input=json.dumps(command)), {})
        self.assertEqual(len(self.requests), 2)

    async def test_other_commands_return_nothing_without_asking(self):
        self.assertEqual(await self.call("git status"), {})
        self.assertEqual(self.requests, [])

    async def test_missing_key_skips_with_a_notice(self):
        self.key_loader.side_effect = jev.JevError("No API key saved. Run jev api-key set.")
        output = await self.call('git commit -m "x" -- README.md')
        self.assertNotIn("hookSpecificOutput", output)
        self.assertIn("No API key saved", output["systemMessage"])

    async def test_slow_answer_skips_with_a_notice(self):
        async def hang(*args, **kwargs):
            await asyncio.sleep(5)

        with patch.object(self.gate, "DEADLINE", 0.3), patch.object(jev.JevSession, "evaluate", hang):
            output = await self.call('git commit -m "x" -- README.md')
        self.assertIn("時間内", output["systemMessage"])

    async def test_missing_module_skips_with_a_notice(self):
        with patch.object(jev, "GATE_MODULE", self.root / "absent.py"), patch.object(jev, "load_gate", jev.load_gate.__wrapped__):
            output = await self.call('git commit -m "x" -- README.md')
        self.assertIn("jev_context_gate", output["systemMessage"])


def serve_fixture():
    from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

    count = 0
    clients = 0

    def respond(request):
        nonlocal count
        count += 1
        assert request.method == "POST"
        return httpx2.Response(200, json=response_body(count=count))

    def make_client(key):
        nonlocal clients
        clients += 1
        assert clients == 1  # fail if the server rebuilds its SDK client
        return AsyncTypeSafeClient(
            api_key=key,
            transport=httpx2.MockTransport(respond),
            retry=RetryPolicy(max_retries=0),
        )

    with (
        patch.object(jev, "load_key", return_value=KEY),
        patch.object(jev, "create_client", side_effect=make_client),
    ):
        jev.create_server().run()


if __name__ == "__main__":
    if sys.argv[1:] == ["--serve-fixture"]:
        serve_fixture()
    elif len(sys.argv) == 3 and sys.argv[1] == "--key-fixture":
        with (
            patch.object(jev, "credential_dir", return_value=Path(sys.argv[2])),
            patch.object(jev, "test_api", new_callable=AsyncMock),
        ):
            jev.api_key()
    else:
        unittest.main()
