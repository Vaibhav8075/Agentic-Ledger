import py_compile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "tests" not in p.parts)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_script_compiles(path):
    # The demo and UI scripts are not imported by other tests, so catch syntax errors here.
    py_compile.compile(str(path), doraise=True, cfile=None)
