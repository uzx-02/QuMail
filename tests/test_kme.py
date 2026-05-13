"""tests/test_kme.py — Unit tests for virtual KME node and client model."""

import unittest


class TestVirtualKME(unittest.TestCase):
    """Covers health, registration, lookup, key issue/retrieve, and throttling."""

    def setUp(self) -> None:
        try:
            from kme.virtual_node import app
        except Exception:
            self.skipTest("Flask dependency is not available in this environment")
        self.client = app.test_client()

    def test_register_lookup_and_issue_key(self) -> None:
        reg = self.client.post("/api/v1/sae/register", json={"email": "user@gmail.com"})
        self.assertIn(reg.status_code, (200, 201))
        sae_id = reg.get_json()["sae_id"]

        lookup = self.client.get("/api/v1/sae/lookup", query_string={"email": "user@gmail.com"})
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.get_json()["registered"])

        issue = self.client.post("/api/v1/keys", json={"sae_id": sae_id, "key_size": 256})
        self.assertEqual(issue.status_code, 200)
        key_id = issue.get_json()["key_id"]

        fetch = self.client.get(f"/api/v1/keys/{key_id}")
        self.assertEqual(fetch.status_code, 200)
        self.assertEqual(fetch.get_json()["key_id"], key_id)

    def test_rate_limit_responds_with_429(self) -> None:
        # Burst enough requests to trip limiter.
        got_429 = False
        for _ in range(130):
            resp = self.client.get("/api/v1/status")
            if resp.status_code == 429:
                got_429 = True
                break
        self.assertTrue(got_429)


if __name__ == "__main__":
    unittest.main()
