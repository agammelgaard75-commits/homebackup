import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from master.app import create_app
from shared.database.storage import connect


def test_campaign_and_party_schema_persists(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "data.sqlite3"
    with TestClient(create_app(db_path=database_path)):
        assert database_path.is_file()

    with connect(database_path) as connection:
        connection.execute("INSERT INTO campaigns (name) VALUES (?)", ("Example",))
        connection.execute("INSERT INTO parties (campaign_id, name) VALUES (?, ?)", (1, "Party"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO parties (campaign_id, name) VALUES (?, ?)", (999, "Invalid"))

    with TestClient(create_app(db_path=database_path)):
        pass
    with connect(database_path) as connection:
        assert connection.execute("SELECT name FROM campaigns").fetchall() == [("Example",)]
        assert connection.execute("SELECT name FROM parties").fetchall() == [("Party",)]
