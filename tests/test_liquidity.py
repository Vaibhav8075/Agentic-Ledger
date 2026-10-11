import asyncio
import random

import numpy as np
import pytest

import mock_backend.main as backend
from agents.guardrails import check_payment_plan, plan_supplier_payment
from ml.forecaster import Forecaster
from tests.conftest import MID

URL = "/api/v1/liquidity/simulate"
HISTORY = [[5800.0, 8900.0], [6200.0, 9400.0], [5600.0, 8600.0]]


@pytest.fixture(scope="module")
def forecaster():
    return Forecaster.load()


def simulate(client, due, mid=MID):
    return client.post(URL, json={"merchant_id": mid, "due_amount": due, "vendor_id": "amul"})


# --- deterministic plan -------------------------------------------------------

def test_plan_decisions():
    assert plan_supplier_payment(6000, 2000, 3000, 6900, 5000)["decision"] == "PAY_FROM_BALANCE"
    with_advance = plan_supplier_payment(6000, 4500, 3000, 6900, 5000)
    assert with_advance["decision"] == "PAY_WITH_ADVANCE"
    assert (with_advance["settle_now_amount"], with_advance["advance_amount"]) == (3000, 1500)
    partial = plan_supplier_payment(6000, 50000, 3000, 6900, 5000)
    assert partial["decision"] == "PARTIAL_PAYMENT" and partial["unpaid_amount"] == 47000


def test_huge_bill_on_empty_balance_is_never_approved():
    # Regression: Rs 0 balance + Rs 50 lakh bill used to be approved because of a Rs 2 crore "forecast".
    plan = plan_supplier_payment(0, 5_000_000, 3000, evening_floor=20_000_000, advance_limit=5000)
    assert plan["decision"] == "PARTIAL_PAYMENT"
    assert plan["settle_now_amount"] == 0 and plan["advance_amount"] == 0


def test_plans_never_break_the_rules():
    rng = random.Random(0)
    for _ in range(2000):
        args = [round(rng.uniform(0, 20000), 2) for _ in range(5)]
        plan = plan_supplier_payment(*args)
        assert check_payment_plan(plan, *args) == []


def test_checker_catches_a_plan_that_eats_the_emi():
    plan = {"decision": "PAY_FROM_BALANCE", "settle_now_amount": 4500, "advance_amount": 0, "unpaid_amount": 0}
    assert check_payment_plan(plan, 6000, 4500, 3000, 6900, 5000)


# --- forecaster ---------------------------------------------------------------

def test_forecast_scales_with_the_merchant(forecaster):
    # Regression: the old model gave ~Rs 2.09 crore for any Rs 12k-scale input.
    small = forecaster.predict(HISTORY, 6000)
    big = forecaster.predict([[m * 10, e * 10] for m, e in HISTORY], 60000)
    assert big.expected == pytest.approx(small.expected * 10, rel=1e-3)
    assert 0 < small.floor < small.expected < 3 * sum(map(sum, HISTORY)) / 3


def test_forecast_responds_to_todays_sales(forecaster):
    assert forecaster.predict(HISTORY, 9000).expected != pytest.approx(forecaster.predict(HISTORY, 3000).expected)


def test_forecaster_rejects_bad_history(forecaster):
    with pytest.raises(ValueError):
        forecaster.predict([[0, 0]] * 3, 100)
    with pytest.raises(ValueError):
        forecaster.predict(HISTORY[:2], 100)


# --- endpoint and agent ---------------------------------------------------------

@pytest.mark.parametrize("due, decision", [(2000.0, "PAY_FROM_BALANCE"), (4500.0, None), (50000.0, "PARTIAL_PAYMENT")])
def test_endpoint_uses_ledger_and_protects_emi(client, forecaster, due, decision):
    data = simulate(client, due).json()
    merchant = backend.MERCHANT_DATABASE[MID]
    floor = forecaster.predict(HISTORY, 6000.0).floor
    expected = plan_supplier_payment(6000.0, due, 3000.0, floor, merchant["advance_limit"])["decision"]
    assert data["decision"] == (decision or expected)
    assert data["projected_eod_balance"] >= data["daily_loan_emi"]
    assert data["evening_forecast_floor"] == floor


def test_demo_bill_gets_an_advance_not_a_sweep(client):
    data = simulate(client, 4500.0).json()
    assert data["decision"] == "PAY_WITH_ADVANCE"
    assert data["recommended_micro_settlement"] == 3000.0 and data["advance_amount"] == 1500.0


def test_endpoint_validation(client):
    assert simulate(client, -5).status_code == 422
    assert simulate(client, 100, mid="UNKNOWN").status_code == 404


def test_agent_maker_checker_passes(supervisor):
    result = asyncio.run(supervisor.optimize_cashflow(due_amount=4500.0, vendor_id="amul"))
    assert result["maker_checker_verification"] == {"passed": True, "violations": []}
