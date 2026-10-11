"""
Automated Test Suite for Paytm Vyapar Saathi Backend & Multi-Agent Logic
Runs natively using Python's standard library unittest.
"""

import unittest
import httpx

import config

BACKEND_URL = config.BACKEND_URL

class TestPaytmVyaparSaathi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = httpx.Client(base_url=BACKEND_URL, timeout=5.0)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_01_telemetry_spoof_detection(self):
        payload = {
            "txn_id": "TXN_NON_EXISTENT_SPOOF_999",
            "device_imei": "864201938472910",
            "timestamp_window": 60000
        }
        resp = self.client.post("/api/v1/telemetry/verify-packet", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "SPOOF_DETECTED")
        self.assertFalse(data["gateway_hash_matched"])
        self.assertLess(data["latency_ms"], 600)

    def test_02_telemetry_2g_cellular_delay(self):
        payload = {
            "txn_id": "TXN_9876543210",
            "device_imei": "864201938472910",
            "timestamp_window": 60000
        }
        resp = self.client.post("/api/v1/telemetry/verify-packet", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "AUDIO_DELAYED")
        self.assertTrue(data["gateway_hash_matched"])
        self.assertFalse(data["puback_received"])
        self.assertLess(data["latency_ms"], 600)

    def test_03_deterministic_liquidity_simulation(self):
        payload = {
            "current_unsettled_balance": 12000.00,
            "due_amount": 4500.00,
            "cutoff_time": "2026-09-10T16:00:00+05:30",
            "merchant_id": "HelloM8xxxxxxxx45"
        }
        resp = self.client.post("/api/v1/liquidity/simulate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["assertion_passed"])
        self.assertEqual(data["recommended_micro_settlement"], 4500.00)
        self.assertEqual(data["projected_eod_balance"], 7500.00)
        self.assertIn("paytmmp://", data["action_deep_link"])

    def test_04_liquidity_blocking_on_loan_default_risk(self):
        # 10,000 + 3,000 EMI = 13,000 > 12,000 -> must fail assertion!
        payload = {
            "current_unsettled_balance": 12000.00,
            "due_amount": 10000.00,
            "cutoff_time": "2026-09-10T16:00:00+05:30",
            "merchant_id": "HelloM8xxxxxxxx45"
        }
        resp = self.client.post("/api/v1/liquidity/simulate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["assertion_passed"])
        self.assertEqual(data["recommended_micro_settlement"], 9000.00)

    def test_05_settlement_execution_with_udir_504(self):
        payload = {
            "merchant_id": "HelloM8xxxxxxxx45",
            "required_amount": 500.00,
            "routing_rail": "IMPS",
            "simulate_504": True
        }
        resp = self.client.post("/api/v1/settlement/execute-micro", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["request"]["body"]["status"], "TXN_SUCCESS")
        self.assertEqual(data["request"]["body"]["udir_reconciliation_code"], "TCC102")

if __name__ == "__main__":
    unittest.main()
