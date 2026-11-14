"""Fixtures shared by every package's tests (the rootdir conftest applies below it)."""

import pytest
from ossdex_core.config import Settings

from testsupport.helpers import build_fixture_db


@pytest.fixture
def db_path(tmp_path):
    return build_fixture_db(tmp_path / "ossdex.db")


@pytest.fixture
def settings(db_path):
    return Settings(db_path=db_path)
