import json
import os
import stat
import tempfile
import unittest

from freeagent_ai import client


class CredentialsTest(unittest.TestCase):
    def test_save_is_mode_600_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            client.CREDS_PATH = os.path.join(d, "sub", "credentials.json")
            client._save({"client_id": "a", "client_secret": "b", "access_token": "c", "refresh_token": "d"})
            mode = stat.S_IMODE(os.stat(client.CREDS_PATH).st_mode)
            self.assertEqual(mode, 0o600)
            self.assertEqual(json.load(open(client.CREDS_PATH))["client_id"], "a")

    def test_store_token_records_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            client.CREDS_PATH = os.path.join(d, "credentials.json")
            creds = {"client_id": "a", "client_secret": "b", "access_token": "", "refresh_token": "r"}
            client._store_token(creds, {"access_token": "new", "expires_in": 3600})
            saved = json.load(open(client.CREDS_PATH))
            self.assertEqual(saved["access_token"], "new")
            self.assertEqual(saved["refresh_token"], "r")
            self.assertIsNotNone(client.token_expiry())


if __name__ == "__main__":
    unittest.main()
