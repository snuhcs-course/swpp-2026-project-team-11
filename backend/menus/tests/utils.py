# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import pathlib
from unittest import mock

# Use as a class decorator: the test sees an empty fixed-menu catalog, whatever
# menus/preprocess/fixed_menus.json currently contains.
without_fixed_catalog = mock.patch("menus.preprocess.fixed.CATALOG_PATH",
                                   new=pathlib.Path("__no_fixed_catalog__.json"))
