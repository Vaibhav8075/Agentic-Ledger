from tests.conftest import IMEI

URL = "/api/v1/telemetry/verify-packet"


def test_unknown_transaction_is_flagged_as_spoof(client):
    resp = client.post(URL, json={"txn_id": "TXN_NON_EXISTENT_SPOOF_999", "device_imei": IMEI, "timestamp_window": 60000})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SPOOF_DETECTED"
    assert data["gateway_hash_matched"] is False


def test_genuine_payment_with_missing_puback_is_audio_delayed(client):
    resp = client.post(URL, json={"txn_id": "TXN_9876543210", "device_imei": IMEI, "timestamp_window": 60000})
    data = resp.json()
    assert data["status"] == "AUDIO_DELAYED"
    assert data["gateway_hash_matched"] is True
    assert data["puback_received"] is False
