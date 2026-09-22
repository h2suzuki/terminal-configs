#!/usr/bin/env python3
"""Credential handling and fixed-endpoint tests; no live API requests."""

import contextlib
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
from unittest.mock import patch

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
            patch.object(jev.sys.stdin, "isatty", return_value=True),
            patch.object(jev.getpass, "getpass", return_value=KEY),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            jev.api_key()
        self.assertNotIn(KEY, output.getvalue())

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

    def test_login_requires_terminal(self):
        with (
            patch.object(jev.sys.stdin, "isatty", return_value=False),
            self.assertRaises(jev.JevError),
        ):
            jev.api_key()
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
                with self.assertRaisesRegex(jev.JevError, message) as error:
                    await self.session.evaluate(**REQUEST)
                self.assertNotIn(KEY, str(error.exception))
        self.assertEqual(len(self.requests), 5)  # no redirects or retries

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
            await jev.test_api()
        self.assertIn("OK:", output.getvalue())
        self.assertNotIn(KEY, output.getvalue())
        self.assertTrue(self.clients[0].is_closed)
        self.body = response_body() | {"answers": {}}
        with self.assertRaisesRegex(jev.JevError, "missing or invalid"):
            await jev.test_api()
        self.assertTrue(self.clients[1].is_closed)

    async def test_mcp_schema_and_safe_error(self):
        self.key_loader.side_effect = jev.JevError(
            "No API key saved. Run jev api-key set."
        )
        async with Client(jev.create_server()) as client:
            listed = await client.list_tools()
            self.assertEqual([tool.name for tool in listed.tools], ["evaluate"])
            properties = listed.tools[0].input_schema["properties"]
            self.assertEqual(set(properties), {"state", "questions", "model"})
            result = await client.call_tool("evaluate", REQUEST)
            self.assertTrue(result.is_error)
            self.assertIn("jev api-key set", str(result.content))

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
        with patch.object(jev, "credential_dir", return_value=Path(sys.argv[2])):
            jev.api_key()
    else:
        unittest.main()
