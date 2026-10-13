# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import pathlib
from unittest import mock

_MISSING = pathlib.Path("__no_committed_rules__.json")
_RULE_FILES = ("menus.preprocess.fixed.CATALOG_PATH", "menus.preprocess.overrides.OVERRIDES_PATH")


def without_committed_rules(cls):
    """Class decorator: from setUp on, the test sees no fixed_menus.json and no
    overrides.json, whatever the committed files currently contain.

    (A class-level mock.patch would only cover the test methods, not setUp.)
    """
    original_setup = cls.setUp

    def setUp(self):
        for target in _RULE_FILES:
            patcher = mock.patch(target, new=_MISSING)
            patcher.start()
            self.addCleanup(patcher.stop)
        original_setup(self)

    cls.setUp = setUp
    return cls
