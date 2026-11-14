import tomllib
from pathlib import Path

import k_whisper


def test_package_version_matches_pyproject():
    pyproject = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
    assert k_whisper.__version__ == pyproject["project"]["version"]
