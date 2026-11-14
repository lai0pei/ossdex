import pytest
from ossdex_server.db import ReadDb


@pytest.fixture
def db(db_path):
    d = ReadDb(db_path)
    yield d
    d.close()
