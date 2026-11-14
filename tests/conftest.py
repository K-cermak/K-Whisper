from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QStandardPaths

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent

# Keep tests away from the real user data / settings locations.
QStandardPaths.setTestModeEnabled(True)
QCoreApplication.setApplicationName("K-Whisper-tests")
QCoreApplication.setOrganizationName("K-Whisper-tests")


@pytest.fixture
def jfk_json() -> Path:
    return FIXTURES / "jfk.json"
