# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import pathlib
from unittest import mock

_MISSING = pathlib.Path("__no_committed_rules__.json")


def without_committed_rules(cls):
    """Class decorator: the test sees no fixed_menus.json and no overrides.json,
    whatever the committed files currently contain."""
    cls = mock.patch("menus.preprocess.fixed.CATALOG_PATH", new=_MISSING)(cls)
    return mock.patch("menus.preprocess.overrides.OVERRIDES_PATH", new=_MISSING)(cls)
