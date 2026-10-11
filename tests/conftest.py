import time

import httpx
import pytest
from fastapi.testclient import TestClient

import config
import mock_backend.main as backend
from agents.guardrails import canonical_body, compute_signature
from agents.supervisor import MasterSupervisorAgent

MID = config.DEMO_MERCHANT_ID
IMEI = "864201938472910"


@pytest.fixture(autouse=True)
def clean_state():
    backend.reset_state()
    yield
    backend.reset_state()


@pytest.fixture
def client():
    with TestClient(backend.app) as c:
        yield c


@pytest.fixture
def supervisor():
    return MasterSupervisorAgent(backend_url="http://sandbox", transport=httpx.ASGITransport(app=backend.app))


def signed_headers(body: bytes, key: str = config.MERCHANT_SIGNING_KEY, idem: str = "IDEMP_TEST_0001",
                   timestamp: int = None) -> dict:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    return {"Content-Type": "application/json", "X-Paytm-Signature": compute_signature(body, key, ts),
            "X-Paytm-Timestamp": ts, "X-Idempotency-Key": idem}


def settlement_body(amount=500.0, order_id="ORD_TEST_0001", rail="IMPS", simulate_504=False, mid=MID) -> bytes:
    return canonical_body({"merchant_id": mid, "order_id": order_id, "required_amount": amount,
                           "routing_rail": rail, "simulate_504": simulate_504})


def balance() -> float:
    return backend.MERCHANT_DATABASE[MID]["current_unsettled_balance"]
