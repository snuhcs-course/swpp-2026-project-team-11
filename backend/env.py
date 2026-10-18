"""Load secrets from the repo-root .env, once, at the edge of the program.

Only the server needs the keys: GOOGLE_API_KEY for feature extraction and
OPENROUTER_API_KEY for the LLM question engine. Both are read from the environment
when the clients are constructed, so this just has to put them there first.
An existing environment variable always wins over the file.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


def load_env() -> bool:
    """Return True if a .env file was found and loaded."""
    try:
        from dotenv import load_dotenv
    except ImportError:          # pip install -r requirements.txt
        return False
    return load_dotenv(ENV_FILE, override=False)
