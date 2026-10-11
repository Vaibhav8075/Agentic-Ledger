import pytest

from tests.conftest import MID

URL = "/api/v1/liquidity/simulate"
SCALE_BUG = "Known bug: the LSTM was trained on dataset-wide daily totals (~Rs 2 crore) and approves almost anything"


@pytest.mark.xfail(strict=True, reason=SCALE_BUG)
def test_bill_within_safe_balance_is_settled_without_forecast_inflation(client):
    resp = client.post(URL, json={"current_unsettled_balance": 12000.0, "due_amount": 4500.0,
                                  "cutoff_time": "2026-09-10T16:00:00+05:30", "merchant_id": MID})
    data = resp.json()
    assert data["assertion_passed"] is True
    assert data["projected_eod_balance"] == 7500.0


@pytest.mark.xfail(strict=True, reason=SCALE_BUG)
def test_bill_that_breaks_the_emi_is_not_fully_approved(client):
    resp = client.post(URL, json={"current_unsettled_balance": 12000.0, "due_amount": 10000.0,
                                  "cutoff_time": "2026-09-10T16:00:00+05:30", "merchant_id": MID})
    data = resp.json()
    assert data["assertion_passed"] is False
    assert data["recommended_micro_settlement"] == 9000.0
