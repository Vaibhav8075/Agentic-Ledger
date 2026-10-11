import asyncio

import httpx

import mock_backend.main as backend
from mock_backend.sandbox_client import create_payment
from tests.conftest import IMEI, MID

URL = "/api/v1/telemetry/verify-packet"
OTHER_IMEI = "999999999999999"


def pay(client, amount=50.0, imei=IMEI, delivered=False):
    resp = client.post("/api/v1/sandbox/gateway/payments",
                       json={"amount": amount, "device_imei": imei, "mqtt_delivered": delivered})
    assert resp.status_code == 200
    return resp.json()["txn_id"]


def verify(client, txn_id, imei=IMEI, window=60000, claimed=None):
    resp = client.post(URL, json={"txn_id": txn_id, "device_imei": imei, "timestamp_window": window,
                                  "claimed_amount": claimed})
    assert resp.status_code == 200
    return resp.json()


def notifications(client):
    return client.get(f"/api/v1/p4b/notifications/{MID}").json()["notifications"]


def test_unknown_transaction_is_flagged_as_spoof(client):
    data = verify(client, "TXN_NON_EXISTENT_SPOOF_999")
    assert data["status"] == "SPOOF_DETECTED"
    assert data["gateway_hash_matched"] is False


def test_genuine_payment_with_missing_puback_is_audio_delayed(client):
    data = verify(client, pay(client), claimed=50.0)
    assert data["status"] == "AUDIO_DELAYED"
    assert data["gateway_hash_matched"] is True
    assert data["puback_received"] is False


def test_delivered_payment_is_verified(client):
    assert verify(client, pay(client, delivered=True))["status"] == "VERIFIED_DELIVERED"


def test_receipt_from_another_merchant_is_spoof(client):
    # Regression: any existing txn ID used to pass, whoever it was paid to.
    other_mid = "OtherM8xxxxxxxx99"
    backend.MERCHANT_DATABASE[other_mid] = {**backend.MERCHANT_DATABASE[MID], "mid": other_mid, "device_imei": OTHER_IMEI}
    foreign_txn = pay(client, imei=OTHER_IMEI)
    assert verify(client, foreign_txn)["status"] == "SPOOF_DETECTED"


def test_old_receipt_is_spoof(client):
    txn = pay(client)
    backend.KNOWN_GATEWAY_HASHES[txn]["timestamp"] -= 600  # paid ten minutes ago
    assert verify(client, txn, window=60000)["status"] == "SPOOF_DETECTED"


def test_amount_mismatch_is_spoof(client):
    data = verify(client, pay(client, amount=50.0), claimed=500.0)
    assert data["status"] == "SPOOF_DETECTED"
    assert "500.00" in data["message"]


def test_qos1_redelivery_sends_one_notification(client):
    txn = pay(client)
    first, second = verify(client, txn), verify(client, txn)
    assert first["deduplicated"] is False and second["deduplicated"] is True
    assert sum(n["notification_type"] == "AUDIO_DELAYED_CONFIRMATION" for n in notifications(client)) == 1


def test_unregistered_device_is_rejected(client):
    resp = client.post(URL, json={"txn_id": "X", "device_imei": "000", "timestamp_window": 60000})
    assert resp.status_code == 404


def test_metrics_report_measured_latency(client):
    verify(client, pay(client))
    metrics = client.get("/api/v1/observability/metrics").json()["metrics"]
    assert metrics["p95_spoof_guard_latency_ms"] < 600
    assert "math_calculation_hallucinations" not in metrics


def test_agent_reports_sla(supervisor):
    transport = httpx.ASGITransport(app=backend.app)
    payment = asyncio.run(create_payment(50.0, IMEI, backend_url="http://sandbox", transport=transport))
    result = asyncio.run(supervisor.handle_soundbox_event(payment["txn_id"], IMEI, claimed_amount=50.0))
    assert result["status"] == "AUDIO_DELAYED" and result["sla_met"] is True
