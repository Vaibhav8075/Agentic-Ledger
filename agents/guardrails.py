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
from typing import Any, Dict, Tuple

def sanitize_pii(text: str) -> Tuple[str, bool]:
    """
    Masks PAN cards, bank accounts, and IFSC codes before sending to any LLM prompt.
    Returns (sanitized_text, had_pii).
    """
    original = text
    # Mask 10-character PAN (e.g. ABCDE1234F)
    text = re.sub(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', '[REDACTED_PAN]', text)
    # Mask 9 to 18-digit bank account numbers
    text = re.sub(r'\b\d{9,18}\b', '[REDACTED_BANK_ACC]', text)
    # Mask 11-char IFSC codes
    text = re.sub(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', '[REDACTED_IFSC]', text)
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
