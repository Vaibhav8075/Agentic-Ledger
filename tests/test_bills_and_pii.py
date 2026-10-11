import asyncio
from datetime import date

import pytest

from agents.guardrails import sanitize_pii
from agents.invoice_parser import InvoiceParseError, parse_invoice, validate_extraction

DEMO_BILL = (
    "From: Amul Distributor Depot #4\n"
    "Delivery Note #INV-8891\n"
    "5 Crates Amul Taaza + 10 Dahi Tubs.\n"
    "Total Amount Due: Rs 4500.00. Payment required strictly by 16:00 today.\n"
    "Payee VPA: amul.dist@paytm | Bank Acc: 98127391823719 | IFSC: PYTM0123456"
)
DAY = date(2026, 9, 10)


# --- PII ----------------------------------------------------------------------

@pytest.mark.parametrize("text, label", [
    ("Acc 98127391823719", "[REDACTED_BANK_ACC]"),
    ("IFSC:SBIN0001234", "[REDACTED_IFSC]"),
    ("PAN ABCDE1234F", "[REDACTED_PAN]"),
    ("Aadhaar 2345 6789 0123", "[REDACTED_AADHAAR]"),
    ("Call +91 98765 43210", "[REDACTED_PHONE]"),
    ("Card 4111 1111 1111 1111", "[REDACTED_CARD]"),
    ("Pay ramesh.k@okhdfcbank", "[REDACTED_VPA]"),
])
def test_pii_is_masked(text, label):
    masked, found = sanitize_pii(text)
    assert found and label in masked


def test_bill_details_survive_redaction():
    masked, _ = sanitize_pii(DEMO_BILL)
    assert "4500.00" in masked and "INV-8891" in masked and "16:00" in masked
    assert "98127391823719" not in masked and "amul.dist@paytm" not in masked


# --- parser -------------------------------------------------------------------

def test_demo_bill_is_parsed_from_the_text():
    bill = parse_invoice(sanitize_pii(DEMO_BILL)[0], "amul", DAY)
    assert bill["due_amount"] == 4500.0
    assert bill["vendor_name"] == "Amul Distributor Depot #4"
    assert bill["invoice_number"] == "INV-8891"
    assert bill["cutoff_time"] == "2026-09-10T16:00:00+05:30"
    assert [(i["quantity"], i["item"]) for i in bill["line_items"]] == [(5, "Crates Amul Taaza"), (10, "Dahi Tubs")]


@pytest.mark.parametrize("text, amount, cutoff", [
    # Regression: anything that was not 4500/3200/2450 used to come back as a Rs 4,500 Amul bill.
    ("Britannia bill. Total due Rs 7,800 by 5pm", 7800.0, "2026-09-10T17:00:00+05:30"),
    # Regression: "14500" used to match the substring "4500".
    ("Pay ₹14,500 for 20 cases Pepsi", 14500.0, None),
])
def test_other_bills_are_parsed(text, amount, cutoff):
    bill = parse_invoice(text, "v", DAY)
    assert bill["due_amount"] == amount and bill["cutoff_time"] == cutoff


def test_message_without_amount_is_refused():
    with pytest.raises(InvoiceParseError):
        parse_invoice("see you tomorrow", "v", DAY)


def test_checker_rejects_an_amount_not_in_the_message():
    assert validate_extraction({"due_amount": 4550.0, "line_items": []}, DEMO_BILL)
    assert validate_extraction(parse_invoice(DEMO_BILL, "v", DAY), DEMO_BILL) == []


# --- backend and agents ----------------------------------------------------------

def test_backend_parses_and_counts_leaked_pii(client):
    resp = client.post("/api/v1/supplier-bills/parse", json={"raw_message": DEMO_BILL, "vendor_id": "amul"})
    assert resp.status_code == 200 and resp.json()["due_amount"] == 4500.0
    assert resp.json()["pii_redacted"] is True  # raw text was sent, so the backend saw PII
    metrics = client.get("/api/v1/observability/metrics").json()["metrics"]
    assert metrics["pii_leakage_events"] == 1
    assert client.post("/api/v1/supplier-bills/parse", json={"raw_message": "hi", "vendor_id": "x"}).status_code == 422


def test_supervisor_routes_a_bill_end_to_end_without_leaking_pii(client, supervisor):
    outcome = asyncio.run(supervisor.handle_event({"type": "supplier_bill", "raw_message": DEMO_BILL,
                                                   "vendor_id": "amul"}))
    assert outcome["bill"]["due_amount"] == 4500.0
    assert outcome["plan"]["decision"] == "PAY_WITH_ADVANCE"
    assert outcome["plan"]["maker_checker_verification"]["passed"] is True
    assert client.get("/api/v1/observability/metrics").json()["metrics"]["pii_leakage_events"] == 0
    assert supervisor.audit_trail[-1]["event"] == "supplier_bill"


def test_supervisor_settles_an_approved_plan(supervisor):
    result = asyncio.run(supervisor.handle_event({"type": "settlement_tap", "amount": 3000.0, "simulate_504": True}))
    assert result["recovered_after_timeout"] is True
    with pytest.raises(ValueError):
        asyncio.run(supervisor.handle_event({"type": "unknown"}))
