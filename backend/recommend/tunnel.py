# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Pieces of `manage.py serve_public`: a Cloudflare Tunnel in front of the server.

`cloudflared` dials out to Cloudflare, which then forwards https requests for a
public hostname back down that connection. The server machine therefore needs no
port forwarding, public IP or certificate, and the server itself can stay bound
to localhost.

Two kinds of tunnel:

- quick (default): no Cloudflare account. The hostname is a random
  `*.trycloudflare.com` that changes on every start and is read from
  cloudflared's log.
- named: METCHU_TUNNEL_TOKEN holds the token of a tunnel made in the Cloudflare
  dashboard, and METCHU_PUBLIC_URL the fixed hostname routed to it there.
"""

from __future__ import annotations

import pathlib
import re
from urllib.parse import urlsplit

QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CLIENT_URL_KEY = "metchu.baseUrl"


def find_quick_url(line: str) -> str | None:
    """The quick tunnel's address, if this cloudflared log line announces it."""
    # api.trycloudflare.com is the service cloudflared asks for a tunnel, and it
    # shows up in error lines.
    for url in QUICK_URL.findall(line):
        if url != "https://api.trycloudflare.com":
            return url
    return None


def normalize_public_url(url: str) -> str:
    """`https://host/` for a named tunnel's address; a bare hostname is accepted."""
    url = url.strip()
    parts = urlsplit(url if "://" in url else f"https://{url}")
    if parts.scheme != "https" or not parts.hostname or parts.path.strip("/") or parts.query:
        raise ValueError(f"METCHU_PUBLIC_URL must look like https://metchu.example.com: {url!r}")
    return f"https://{parts.netloc}/"


def hostname(url: str) -> str:
    return urlsplit(url).hostname


def tunnel_command(cloudflared: str, local_url: str, *, named: bool) -> list[str]:
    """The cloudflared invocation. A named tunnel's token travels in TUNNEL_TOKEN,
    not here, so it does not show up in the process list."""
    if named:
        return [cloudflared, "tunnel", "--no-autoupdate", "run"]
    return [cloudflared, "tunnel", "--no-autoupdate", "--url", local_url]


def write_client_base_url(path: pathlib.Path, url: str) -> None:
    """Point the Android build at `url`, keeping the file's other properties."""
    entry = f"{CLIENT_URL_KEY}={url}"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0].strip() != CLIENT_URL_KEY]
    path.write_text("\n".join([*kept, entry]) + "\n", encoding="utf-8")
