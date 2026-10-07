import json
import os
import stat
from pathlib import Path

from freeagent_ai import client


def test_save_is_mode_600_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "sub" / "credentials.json"))
    client._save({"client_id": "a", "client_secret": "b", "access_token": "c", "refresh_token": "d"})
    assert stat.S_IMODE(os.stat(client.CREDS_PATH).st_mode) == 0o600
    assert json.loads(Path(client.CREDS_PATH).read_text())["client_id"] == "a"


def test_store_token_records_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "credentials.json"))
    creds = {"client_id": "a", "client_secret": "b", "access_token": "", "refresh_token": "r"}
    client._store_token(creds, {"access_token": "new", "expires_in": 3600})
    saved = json.loads(Path(client.CREDS_PATH).read_text())
    assert saved["access_token"] == "new"
    assert saved["refresh_token"] == "r"
    assert client.token_expiry() is not None
