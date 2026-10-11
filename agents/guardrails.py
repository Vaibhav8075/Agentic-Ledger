"""
Deterministic Guardrails for Phinite Agent Graph
- PII Sanitization (PAN, Bank Accounts, IFSC)
- Maker-Checker Mathematical Assertion
- Cryptographic HMAC-SHA256 Signer
"""

import hashlib
import hmac
import json
import re
import time
from typing import Any, Dict, List, Tuple

# Order matters: longer / more specific patterns first, so each number gets the right label.
PII_PATTERNS = [
    ("[REDACTED_CARD]", re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b")),
    ("[REDACTED_AADHAAR]", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("[REDACTED_PHONE]", re.compile(r"(?:\+91[ -]?)?\b[6-9]\d{4}[ -]?\d{5}\b")),
    ("[REDACTED_BANK_ACC]", re.compile(r"\b\d{9,18}\b")),
    ("[REDACTED_PAN]", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("[REDACTED_IFSC]", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("[REDACTED_VPA]", re.compile(r"\b[\w.-]+@[\w-]+(?:\.[\w-]+)*\b")),
]

def sanitize_pii(text: str) -> Tuple[str, bool]:
    """
    Masks card, Aadhaar, phone, bank account, PAN, IFSC and VPA/e-mail before any text reaches an LLM.
    Returns (sanitized_text, had_pii). The backend uses the same function to detect leaks.
    """
    original = text
    for label, pattern in PII_PATTERNS:
        text = pattern.sub(label, text)
    return text, text != original

def assert_liquidity_guardrail(
    current_unsettled_balance: float,
    requested_settlement: float,
    daily_loan_emi: float = 3000.00
) -> Dict[str, Any]:
    """
    Strict Maker-Checker Boolean Assertion:
    (Requested_Settlement + Daily_Loan_EMI) <= Current_Unsettled_Balance
    Guarantees that no generative LLM hallucination can trigger an automated loan default.
    """
    current_unsettled_balance = float(current_unsettled_balance)
    requested_settlement = float(requested_settlement)
    daily_loan_emi = float(daily_loan_emi)

    passed = (requested_settlement + daily_loan_emi) <= current_unsettled_balance

    if not passed:
        max_safe = max(0.0, current_unsettled_balance - daily_loan_emi)
        return {
            "assertion_status": "FAILED",
            "passed": False,
            "reason": f"Requested ₹{requested_settlement:,.2f} + Daily EMI ₹{daily_loan_emi:,.2f} = ₹{requested_settlement + daily_loan_emi:,.2f} exceeds unsettled ledger ₹{current_unsettled_balance:,.2f}.",
            "max_safe_micro_settlement": max_safe,
            "risk_mitigation": "Aborting instant settlement to prevent morning loan EMI bounce."
        }

    residual = current_unsettled_balance - requested_settlement
    return {
        "assertion_status": "PASSED",
        "passed": True,
        "requested_settlement": requested_settlement,
        "daily_loan_emi_protected": daily_loan_emi,
        "residual_unsettled_balance": residual,
        "action": "PROCEED_WITH_TARGETED_MICRO_SETTLEMENT"
    }

def plan_supplier_payment(
    balance: float,
    due_amount: float,
    daily_loan_emi: float,
    evening_floor: float,
    advance_limit: float
) -> Dict[str, Any]:
    """
    Deterministic payment plan for a supplier bill. Never touches the EMI reserve.
    1. Pay from the unsettled balance if the bill fits above the EMI reserve.
    2. Otherwise settle what is safe and offer a short advance for the gap, but only if the gap
       is within both the pre-approved advance limit and the conservative forecast of tonight's
       sales (which repay it in the T+1 batch, alongside the EMI).
    3. Otherwise settle what is safe and leave the rest unpaid, with an advisory.
    """
    safe_now = round(max(0.0, balance - daily_loan_emi), 2)
    if due_amount <= safe_now:
        decision, settle_now, advance = "PAY_FROM_BALANCE", due_amount, 0.0
    else:
        shortfall = round(due_amount - safe_now, 2)
        if shortfall <= min(evening_floor, advance_limit):
            decision, settle_now, advance = "PAY_WITH_ADVANCE", safe_now, shortfall
        else:
            decision, settle_now, advance = "PARTIAL_PAYMENT", safe_now, 0.0
    return {
        "decision": decision,
        "safe_settlement_limit": safe_now,
        "settle_now_amount": round(settle_now, 2),
        "advance_amount": round(advance, 2),
        "unpaid_amount": round(due_amount - settle_now - advance, 2)
    }

def check_payment_plan(
    plan: Dict[str, Any],
    balance: float,
    due_amount: float,
    daily_loan_emi: float,
    evening_floor: float,
    advance_limit: float
) -> List[str]:
    """Checker side of maker-checker: returns every rule the plan breaks (empty list = safe)."""
    eps = 0.01
    settle, advance, unpaid = plan["settle_now_amount"], plan["advance_amount"], plan["unpaid_amount"]
    violations = []
    if min(settle, advance, unpaid) < -eps:
        violations.append("negative amount in plan")
    if settle > max(0.0, balance - daily_loan_emi) + eps:
        violations.append("settlement eats into the EMI reserve")
    if advance > min(evening_floor, advance_limit) + eps:
        violations.append("advance exceeds the forecast floor or the advance limit")
    if abs(settle + advance + unpaid - due_amount) > eps:
        violations.append("plan does not add up to the bill")
    expected = plan_supplier_payment(balance, due_amount, daily_loan_emi, evening_floor, advance_limit)
    if plan["decision"] != expected["decision"]:
        violations.append(f"decision {plan['decision']} differs from independent recomputation {expected['decision']}")
    return violations

def canonical_body(payload: dict) -> bytes:
    """Serialises a request body the same way on both sides so signatures are reproducible."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

def compute_signature(body: bytes, secret_key: str, timestamp: str) -> str:
    """HMAC-SHA256 over the exact request bytes followed by the timestamp."""
    return hmac.new(secret_key.encode("utf-8"), body + timestamp.encode("utf-8"), hashlib.sha256).hexdigest()

def sign_paytm_request(body: bytes, secret_key: str) -> Dict[str, str]:
    """
    Signs the exact bytes that will be sent. The receiver recomputes the signature from the raw
    body and the X-Paytm-Timestamp header, so any change to the amount or merchant breaks it.
    """
    timestamp = str(int(time.time()))
    return {"signature": compute_signature(body, secret_key, timestamp), "timestamp": timestamp}
