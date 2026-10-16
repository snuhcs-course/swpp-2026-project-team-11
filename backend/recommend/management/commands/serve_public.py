# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Run the server and a Cloudflare Tunnel to it, so the app works from any network.

    python manage.py serve_public                         # quick tunnel, random address
    python manage.py serve_public --write-client-config   # ... and point the app build at it

The server stays bound to localhost; only the tunnel is public. See
`recommend/tunnel.py` for the two kinds of tunnel and `client/README.md` for the
phone side.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import signal
import subprocess
import sys
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from recommend import tunnel

INSTALL_HINT = (
    "cloudflared was not found. Install it (macOS: `brew install cloudflared`, "
    "Windows: `winget install Cloudflare.cloudflared`, others: "
    "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) "
    "or pass --cloudflared /path/to/cloudflared."
)
CLIENT_PROPERTIES = pathlib.Path(settings.BASE_DIR).parent / "client" / "local.properties"
STOP_SIGNALS = [signal.SIGTERM] + ([signal.SIGHUP] if hasattr(signal, "SIGHUP") else [])  # no SIGHUP on Windows


class Command(BaseCommand):
    help = "Run the server behind a Cloudflare Tunnel and print its public address."

    # Seconds to wait for a quick tunnel's address, for its first connection, and
    # between liveness checks.
    url_timeout = 30.0
    connect_timeout = 15.0
    poll_interval = 0.5

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--cloudflared", default=os.environ.get("METCHU_CLOUDFLARED") or "cloudflared",
                            help="cloudflared executable (default: the one on PATH).")
        parser.add_argument("--write-client-config", action="store_true",
                            help="Write the public address to client/local.properties as metchu.baseUrl.")
        parser.add_argument("--debug", action="store_true",
                            help="Keep Django's DEBUG on. Its error pages become public.")

    def handle(self, *args, **options):
        token = os.environ.get("METCHU_TUNNEL_TOKEN", "").strip()
        public_url = os.environ.get("METCHU_PUBLIC_URL", "").strip()
        if bool(token) != bool(public_url):
            raise CommandError("A named tunnel needs both METCHU_TUNNEL_TOKEN and METCHU_PUBLIC_URL.")
        if public_url:
            try:
                public_url = tunnel.normalize_public_url(public_url)
            except ValueError as error:
                raise CommandError(str(error)) from error
        cloudflared = shutil.which(options["cloudflared"])
        if cloudflared is None:
            raise CommandError(INSTALL_HINT)

        port = options["port"]
        server_env = {**os.environ, "METCHU_DEBUG": "1" if options["debug"] else "0"}
        if public_url:
            hosts = [os.environ.get("METCHU_ALLOWED_HOSTS", ""), tunnel.hostname(public_url)]
            server_env["METCHU_ALLOWED_HOSTS"] = ",".join(host for host in hosts if host)
        tunnel_env = {**os.environ, "TUNNEL_TOKEN": token} if token else None

        processes = []
        # A plain `kill` or a closed terminal (SIGHUP) must take the children down too,
        # as Ctrl-C does; otherwise the tunnel stays open after this command is gone.
        previous = {sig: signal.signal(sig, self._interrupt) for sig in STOP_SIGNALS}
        try:
            # --noreload keeps the server to one process, so stopping it stops it all.
            server = subprocess.Popen(
                [sys.executable, str(pathlib.Path(settings.BASE_DIR) / "manage.py"),
                 "runserver", f"127.0.0.1:{port}", "--noreload"], env=server_env)
            processes.append(("The server", server))
            connector = subprocess.Popen(
                tunnel.tunnel_command(cloudflared, f"http://127.0.0.1:{port}", named=bool(token)),
                env=tunnel_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            processes.append(("cloudflared", connector))

            found, connected = threading.Event(), threading.Event()
            quick_url = []
            log = []
            reader = threading.Thread(
                target=self._read_log, daemon=True,
                args=(connector.stdout, quick_url, found, connected, log, options["verbosity"] >= 2))
            reader.start()
            if not public_url:
                public_url = self._wait_for_quick_url(connector, reader, quick_url, found, log)
            # A hostname looked up before the tunnel connects can be cached as
            # nonexistent for a while, so the address is shown only once it works.
            if not connected.wait(self.connect_timeout):
                self.stdout.write(self.style.WARNING(
                    "cloudflared has not reported a connection yet; the address may not "
                    "answer for a little while."))

            self._announce(public_url, quick=not token)
            if options["write_client_config"]:
                tunnel.write_client_base_url(CLIENT_PROPERTIES, public_url)
                self.stdout.write(f"Wrote {tunnel.CLIENT_URL_KEY} to {CLIENT_PROPERTIES}. Rebuild the app.")
            self.stdout.flush()     # the address must show even when output is piped

            while True:
                for name, process in processes:
                    if process.poll() is not None:
                        raise CommandError(f"{name} stopped (exit code {process.returncode}).")
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.stdout.write("Stopping.")
        finally:
            for _, process in reversed(processes):
                self._stop(process)
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def _read_log(self, stream, quick_url, found, connected, log, echo):
        """Drain cloudflared's log for as long as it runs; a full pipe would stall it."""
        for line in stream:
            if "Registered tunnel connection" in line:
                connected.set()
            if not found.is_set():
                log.append(line.rstrip())
                url = tunnel.find_quick_url(line)
                if url:
                    quick_url.append(url + "/")
                    found.set()
            if echo:
                self.stderr.write(line.rstrip())

    def _wait_for_quick_url(self, connector, reader, quick_url, found, log):
        deadline = time.monotonic() + self.url_timeout
        while not found.wait(0.1):
            if connector.poll() is not None:
                reader.join(timeout=2)      # let it finish the lines already written
                if found.is_set():
                    break
                raise CommandError(
                    f"cloudflared stopped (exit code {connector.returncode}) before "
                    "opening a tunnel:\n" + "\n".join(log[-15:]))
            if time.monotonic() > deadline:
                raise CommandError(
                    f"cloudflared opened no tunnel within {self.url_timeout:.0f} s:\n"
                    + "\n".join(log[-15:]))
        return quick_url[0]

    def _announce(self, public_url, *, quick):
        self.stdout.write(self.style.SUCCESS(f"\nPublic address: {public_url}"))
        self.stdout.write(f"Check it:       {public_url}api/health/")
        self.stdout.write(f"App setting:    {tunnel.CLIENT_URL_KEY}={public_url}   (client/local.properties)")
        if quick:
            self.stdout.write("This address is new on every start. Anyone who has it can use the server.")
            self.stdout.write("Some networks (SNU campus DNS) find a new address only after about a minute,\n"
                              "and remember an earlier lookup as missing for 60 s: wait before opening it.")
        self.stdout.write("Ctrl-C stops the server and the tunnel.\n")

    @staticmethod
    def _interrupt(signum, frame):
        raise KeyboardInterrupt

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
