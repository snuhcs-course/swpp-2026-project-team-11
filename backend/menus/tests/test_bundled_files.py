"""The schema, prompt and RL manifest read at import are UTF-8 whatever the machine's locale."""
import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

BACKEND = Path(__file__).resolve().parents[2]
MODULES = ("menus.features.schema", "menus.features.prompt",
           "question_engines.decision_tree.contracts", "question_engines.rl.policy")


class BundledFileTests(TestCase):
    def test_the_modules_load_outside_utf8_mode(self):
        # Korean Windows reads text as cp949 unless told otherwise; an ASCII locale fails the same way.
        env = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}
        code = "import importlib, sys; [importlib.import_module(name) for name in sys.argv[1:]]"
        run = subprocess.run([sys.executable, "-c", code, *MODULES], cwd=BACKEND, env=env,
                             capture_output=True, text=True, errors="replace")
        self.assertEqual(run.returncode, 0, run.stderr)
