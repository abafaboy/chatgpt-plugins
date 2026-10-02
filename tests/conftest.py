import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def usage_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("USAGE_LOG", str(path))
    return path


FIXTURES = Path(__file__).parent / "fixtures"
os.environ.setdefault("PUBLIC_HOST", "")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
