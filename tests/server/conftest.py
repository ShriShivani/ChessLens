import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app

TOKEN = "test-token"
AUTH = {"X-Ingest-Token": TOKEN}


@pytest.fixture
def client():
    settings = Settings(
        database_url="sqlite://", ingest_token=TOKEN, rate_limit_per_min=1000, log_level="WARNING"
    )
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def game_id(client):
    return client.post("/api/games", json={"white": "Ann", "black": "Bo"}, headers=AUTH).json()[
        "id"
    ]
