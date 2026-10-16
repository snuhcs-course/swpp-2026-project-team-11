# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Reaching the server from another network (settings, `serve_public`, recommend/tunnel.py).

cloudflared and the server are replaced by scripted processes, so nothing here
opens a tunnel or needs the network.
"""
import io
import os
import pathlib
import signal
import subprocess
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from recommend import tunnel
from recommend.management.commands import serve_public

QUICK_URL = "https://calm-red-fox-demo.trycloudflare.com"
QUICK_LOG = [
    "2026-10-08T01:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n",
    "2026-10-08T01:00:01Z INF +----------------------------------------------+\n",
    f"2026-10-08T01:00:01Z INF |  {QUICK_URL}  |\n",
    "2026-10-08T01:00:02Z INF Registered tunnel connection connIndex=0\n",
]


class HostTests(SimpleTestCase):
    def test_health_answers_on_a_quick_tunnel_hostname(self):
        response = self.client.get("/api/health/", HTTP_HOST="calm-red-fox-demo.trycloudflare.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_local_addresses_still_work(self):
        for host in ("localhost:8000", "127.0.0.1:8000", "10.0.2.2:8000"):
            self.assertEqual(self.client.get("/api/health/", HTTP_HOST=host).status_code, 200, host)

    def test_other_hostnames_are_refused(self):
        for host in ("evil.example.com", "trycloudflare.com.evil.example.com"):
            self.assertEqual(self.client.get("/api/health/", HTTP_HOST=host).status_code, 400, host)

    def test_health_is_read_only(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)


class TunnelHelperTests(SimpleTestCase):
    def test_finds_the_address_in_cloudflared_log(self):
        self.assertEqual([tunnel.find_quick_url(line) for line in QUICK_LOG],
                         [None, None, QUICK_URL, None])

    def test_ignores_the_quick_tunnel_api_host(self):
        line = 'ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": timeout'
        self.assertIsNone(tunnel.find_quick_url(line))

    def test_normalizes_a_named_tunnel_address(self):
        for given in ("https://metchu.example.com", "https://metchu.example.com/",
                      "metchu.example.com", " https://metchu.example.com "):
            self.assertEqual(tunnel.normalize_public_url(given), "https://metchu.example.com/", given)

    def test_rejects_addresses_the_app_could_not_use(self):
        for given in ("http://metchu.example.com", "https://metchu.example.com/api/", "https://", ""):
            with self.assertRaises(ValueError, msg=given):
                tunnel.normalize_public_url(given)

    def test_quick_and_named_commands(self):
        self.assertEqual(
            tunnel.tunnel_command("cloudflared", "http://127.0.0.1:8000", named=False),
            ["cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"])
        self.assertEqual(tunnel.tunnel_command("cloudflared", "http://127.0.0.1:8000", named=True),
                         ["cloudflared", "tunnel", "--no-autoupdate", "run"])

    def test_client_config_keeps_other_properties_and_replaces_the_old_address(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "local.properties"
            path.write_text("sdk.dir=/sdk\nmetchu.baseUrl=http://192.168.0.3:8000/\n", encoding="utf-8")
            tunnel.write_client_base_url(path, QUICK_URL + "/")
            tunnel.write_client_base_url(path, QUICK_URL + "/")
            self.assertEqual(path.read_text(encoding="utf-8"),
                             f"sdk.dir=/sdk\nmetchu.baseUrl={QUICK_URL}/\n")

    def test_client_config_is_created_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "local.properties"
            tunnel.write_client_base_url(path, QUICK_URL + "/")
            self.assertEqual(path.read_text(encoding="utf-8"), f"metchu.baseUrl={QUICK_URL}/\n")


class FakeProcess:
    """A child process whose `poll()` replays `polls`, then keeps running.

    A poll result that is an exception is raised, which is how a test presses Ctrl-C.
    """

    def __init__(self, polls=(None,), lines=()):
        self.polls = list(polls)
        self.stdout = iter(lines)
        self.returncode = None
        self.terminated = self.killed = False

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        result = self.polls.pop(0) if self.polls else None
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class ServePublicTests(SimpleTestCase):
    def run_command(self, server, connector, *args, env=None, which="/usr/bin/cloudflared"):
        """Run serve_public with scripted children. Returns (stdout, Popen calls)."""
        stream = io.StringIO()
        popen = mock.Mock(side_effect=[server, connector])
        self.popen = popen
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(serve_public.subprocess, "Popen", popen), \
                mock.patch.object(serve_public.shutil, "which", return_value=which), \
                mock.patch.object(serve_public.Command, "poll_interval", 0), \
                mock.patch.object(serve_public.Command, "url_timeout", 2.0), \
                mock.patch.object(serve_public.Command, "connect_timeout", 0.2), \
                mock.patch.object(serve_public, "CLIENT_PROPERTIES",
                                  pathlib.Path(directory) / "local.properties"), \
                mock.patch.dict("os.environ", env or {}):
            for name in ("METCHU_TUNNEL_TOKEN", "METCHU_PUBLIC_URL", "METCHU_ALLOWED_HOSTS"):
                if name not in (env or {}):
                    serve_public.os.environ.pop(name, None)
            try:
                call_command("serve_public", *args, stdout=stream)
            finally:
                properties = serve_public.CLIENT_PROPERTIES
                self.client_config = (properties.read_text(encoding="utf-8")
                                      if properties.exists() else None)
        return stream.getvalue()

    def test_quick_tunnel_prints_the_address_and_stops_both_on_ctrl_c(self):
        server = FakeProcess([None, KeyboardInterrupt()])
        connector = FakeProcess(lines=QUICK_LOG)
        output = self.run_command(server, connector)

        self.assertIn(f"Public address: {QUICK_URL}/", output)
        self.assertIn(f"metchu.baseUrl={QUICK_URL}/", output)
        self.assertIn("new on every start", output)
        self.assertIn("wait before opening it", output)
        self.assertTrue(server.terminated)
        self.assertTrue(connector.terminated)
        self.assertIsNone(self.client_config)

    def test_server_stays_on_localhost_with_debug_off(self):
        self.run_command(FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=QUICK_LOG),
                         "--port", "8123")
        (server_args, server_kwargs), (tunnel_args, tunnel_kwargs) = self.popen.call_args_list

        self.assertEqual(server_args[0][2:], ["runserver", "127.0.0.1:8123", "--noreload"])
        self.assertEqual(server_kwargs["env"]["METCHU_DEBUG"], "0")
        self.assertEqual(tunnel_args[0], ["/usr/bin/cloudflared", "tunnel", "--no-autoupdate",
                                          "--url", "http://127.0.0.1:8123"])
        self.assertIsNone(tunnel_kwargs["env"])

    def test_debug_flag_keeps_debug_on(self):
        self.run_command(FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=QUICK_LOG), "--debug")
        self.assertEqual(self.popen.call_args_list[0].kwargs["env"]["METCHU_DEBUG"], "1")

    def test_the_address_waits_for_the_first_connection(self):
        output = self.run_command(FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=QUICK_LOG))
        self.assertNotIn("not reported a connection", output)
        unconnected = [line for line in QUICK_LOG if "Registered" not in line]
        output = self.run_command(FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=unconnected))
        self.assertIn("not reported a connection yet", output)
        self.assertIn(f"Public address: {QUICK_URL}/", output)

    def test_write_client_config(self):
        self.run_command(FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=QUICK_LOG),
                         "--write-client-config")
        self.assertEqual(self.client_config, f"metchu.baseUrl={QUICK_URL}/\n")

    def test_named_tunnel_uses_the_fixed_address_and_hides_the_token(self):
        output = self.run_command(
            FakeProcess([KeyboardInterrupt()]), FakeProcess(lines=["INF Registered tunnel connection\n"]),
            env={"METCHU_TUNNEL_TOKEN": "secret-token", "METCHU_PUBLIC_URL": "metchu.example.com",
                 "METCHU_ALLOWED_HOSTS": "192.168.0.3"})
        (_, server_kwargs), (tunnel_args, tunnel_kwargs) = self.popen.call_args_list

        self.assertIn("Public address: https://metchu.example.com/", output)
        self.assertNotIn("new on every start", output)
        self.assertEqual(tunnel_args[0], ["/usr/bin/cloudflared", "tunnel", "--no-autoupdate", "run"])
        self.assertEqual(tunnel_kwargs["env"]["TUNNEL_TOKEN"], "secret-token")
        self.assertEqual(server_kwargs["env"]["METCHU_ALLOWED_HOSTS"], "192.168.0.3,metchu.example.com")
        self.assertNotIn("secret-token", output)

    def test_named_tunnel_needs_both_settings(self):
        for env in ({"METCHU_TUNNEL_TOKEN": "secret-token"}, {"METCHU_PUBLIC_URL": "metchu.example.com"}):
            with self.assertRaisesMessage(CommandError, "needs both"):
                self.run_command(FakeProcess(), FakeProcess(), env=env)
            self.popen.assert_not_called()

    def test_named_tunnel_rejects_a_plain_http_address(self):
        with self.assertRaisesMessage(CommandError, "METCHU_PUBLIC_URL"):
            self.run_command(FakeProcess(), FakeProcess(), env={
                "METCHU_TUNNEL_TOKEN": "secret-token", "METCHU_PUBLIC_URL": "http://metchu.example.com"})
        self.popen.assert_not_called()

    def test_missing_cloudflared_says_how_to_install_it(self):
        with self.assertRaisesMessage(CommandError, "brew install cloudflared"):
            self.run_command(FakeProcess(), FakeProcess(), which=None)
        self.popen.assert_not_called()

    def test_cloudflared_failing_to_start_reports_its_log_and_stops_the_server(self):
        server = FakeProcess()
        connector = FakeProcess([1], lines=["ERR failed to request quick Tunnel: no network\n"])
        with self.assertRaisesMessage(CommandError, "failed to request quick Tunnel"):
            self.run_command(server, connector)
        self.assertTrue(server.terminated)

    def test_no_address_in_time_is_an_error(self):
        server = FakeProcess()
        connector = FakeProcess(lines=["INF Requesting new quick Tunnel on trycloudflare.com...\n"])
        with mock.patch.object(serve_public.time, "monotonic", side_effect=[0, 100]), \
                self.assertRaisesMessage(CommandError, "opened no tunnel"):
            self.run_command(server, connector)
        self.assertTrue(server.terminated)
        self.assertTrue(connector.terminated)

    def test_server_dying_stops_the_tunnel(self):
        server = FakeProcess([3])
        connector = FakeProcess(lines=QUICK_LOG)
        with self.assertRaisesMessage(CommandError, "The server stopped (exit code 3)"):
            self.run_command(server, connector)
        self.assertTrue(connector.terminated)
        self.assertFalse(server.terminated)

    def test_kill_and_a_closed_terminal_stop_both_like_ctrl_c(self):
        for signum in serve_public.STOP_SIGNALS:  # SIGTERM, and SIGHUP where it exists
            with self.subTest(signal=signum.name):
                class Killed(FakeProcess):
                    sent = False

                    def poll(self):
                        if not self.sent:
                            self.sent = True
                            os.kill(os.getpid(), signum)
                        return super().poll()

                before = signal.getsignal(signum)
                server, connector = Killed(), FakeProcess(lines=QUICK_LOG)
                output = self.run_command(server, connector)

                self.assertIn("Stopping.", output)
                self.assertTrue(server.terminated)
                self.assertTrue(connector.terminated)
                self.assertIs(signal.getsignal(signum), before)

    def test_a_process_that_ignores_terminate_is_killed(self):
        process = FakeProcess()
        process.terminate = lambda: None
        process.wait = mock.Mock(side_effect=[subprocess.TimeoutExpired("x", 5), -9])
        serve_public.Command._stop(process)
        self.assertTrue(process.killed)
