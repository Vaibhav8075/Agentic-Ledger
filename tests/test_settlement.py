import asyncio
import time

from tests.conftest import MID, balance, settlement_body, signed_headers

URL = "/api/v1/settlement/execute-micro"
START = 6000.0  # seeded unsettled balance; EMI reserve is 3000


def test_signed_request_settles_once(client):
    body = settlement_body(500.0)
    resp = client.post(URL, content=body, headers=signed_headers(body))
    assert resp.status_code == 200
    assert resp.json()["request"]["body"]["status"] == "TXN_SUCCESS"
    assert balance() == START - 500.0


def test_forged_or_missing_signature_is_rejected(client):
    body = settlement_body(500.0)
    forged = signed_headers(body, key="wrong-key")
    assert client.post(URL, content=body, headers=forged).status_code == 401
    unsigned = {"Content-Type": "application/json", "X-Idempotency-Key": "IDEMP_TEST_0001"}
    assert client.post(URL, content=body, headers=unsigned).status_code == 401
    assert balance() == START


def test_tampered_amount_and_stale_timestamp_are_rejected(client):
    signed_for_small = signed_headers(settlement_body(10.0))
    assert client.post(URL, content=settlement_body(5000.0), headers=signed_for_small).status_code == 401
    body = settlement_body(500.0)
    stale = signed_headers(body, timestamp=int(time.time()) - 3600)
    assert client.post(URL, content=body, headers=stale).status_code == 401
    assert balance() == START


def test_retry_with_same_key_does_not_double_debit(client):
    body = settlement_body(2000.0)
    first = client.post(URL, content=body, headers=signed_headers(body))
    retry = client.post(URL, content=body, headers=signed_headers(body))
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert balance() == START - 2000.0


def test_reused_key_with_different_body_conflicts(client):
    first = settlement_body(500.0)
    client.post(URL, content=first, headers=signed_headers(first))
    other = settlement_body(700.0, order_id="ORD_TEST_0002")
    assert client.post(URL, content=other, headers=signed_headers(other)).status_code == 409
    assert balance() == START - 500.0


def test_guardrail_applies_on_timeout_path_too(client):
    # Regression: the simulated-504 path used to skip the EMI check (balance went to -992,500).
    body = settlement_body(1_000_000.0, simulate_504=True)
    resp = client.post(URL, content=body, headers=signed_headers(body))
    assert resp.status_code == 400
    assert balance() == START


def test_invalid_amount_rail_and_merchant(client):
    for body in (settlement_body(-99999.0), settlement_body(500.0, rail="FOOBAR")):
        assert client.post(URL, content=body, headers=signed_headers(body)).status_code == 422
    body = settlement_body(500.0, mid="UNKNOWN_MID")
    assert client.post(URL, content=body, headers=signed_headers(body)).status_code == 404


def test_state_endpoint_hides_signing_key(client):
    state = client.get(f"/api/v1/merchant/state/{MID}").json()
    assert "secret_key" not in state


def test_supervisor_recovers_from_timeout_without_second_payout(supervisor):
    result = asyncio.run(supervisor.execute_settlement(MID, 2000.0, simulate_504=True))
    assert result["recovered_after_timeout"] is True
    assert result["request"]["body"]["udir_reconciliation_code"] == "TCC102"
    assert balance() == START - 2000.0


def test_supervisor_retry_of_same_order_is_idempotent(supervisor):
    first = asyncio.run(supervisor.execute_settlement(MID, 1000.0, order_id="ORD_REPEAT_01"))
    again = asyncio.run(supervisor.execute_settlement(MID, 1000.0, order_id="ORD_REPEAT_01"))
    assert first["request"]["body"]["transactionId"] == again["request"]["body"]["transactionId"]
    assert balance() == START - 1000.0
