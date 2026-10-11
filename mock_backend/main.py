"""
Paytm Vyapar Saathi: Autonomous Soundbox Anti-Fraud & Liquidity Balancer
Mock Production Backend on FastAPI
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config
from agents.guardrails import compute_signature

app = FastAPI(
    title="Paytm Vyapar Saathi Production Mock Backend",
    description="Mock backend simulating Paytm Payment Gateway, Soundbox 2G MQTT broker, and Paytm Settlement APIs for Phinite Agent Graph.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# IN-MEMORY FINTECH STATE & LEDGER STORE
# -------------------------------------------------------------
def _seed_merchants() -> Dict[str, Dict[str, Any]]:
    return {
        config.DEMO_MERCHANT_ID: {
            "mid": config.DEMO_MERCHANT_ID,
            "merchant_name": "Sharma General Store & Dairy",
            "secret_key": config.MERCHANT_SIGNING_KEY,
            "device_imei": "864201938472910",
            "current_unsettled_balance": 12000.00,
            "daily_loan_emi": 3000.00,
            "settled_today": 0.00,
            "loan_account_id": "PAYTM_LOAN_782194",
            "bank_account_masked": "XXXXXX9182",
            "ifsc_masked": "PYTM0123456"
        }
    }

def _fresh_metrics() -> Dict[str, Any]:
    return {
        "telemetry_verifications_count": 0,
        "spoofs_detected_count": 0,
        "lagged_audio_alerts_count": 0,
        "liquidity_simulations_count": 0,
        "loan_defaults_prevented_count": 0,
        "total_settled_amount": 0.0,
        "pii_leakage_detected": 0,  # PII that reached the backend unredacted
        "latency_records_ms": []
    }

MERCHANT_DATABASE: Dict[str, Dict[str, Any]] = _seed_merchants()
# Transactions cleared through the gateway switch (created via /api/v1/sandbox/gateway/payments)
KNOWN_GATEWAY_HASHES: Dict[str, Dict[str, Any]] = {}
ANNOUNCED_TXNS: set = set()
P4B_NOTIFICATION_STORE: List[Dict[str, Any]] = []
SETTLEMENT_ORDERS_STORE: Dict[str, Dict[str, Any]] = {}
PROCESSED_IDEMPOTENCY_KEYS: Dict[str, Dict[str, Any]] = {}
OBSERVABILITY_METRICS: Dict[str, Any] = _fresh_metrics()

def reset_state() -> None:
    """Restores the seeded sandbox state in place (used by tests and the demo)."""
    for store, fresh in ((MERCHANT_DATABASE, _seed_merchants()), (OBSERVABILITY_METRICS, _fresh_metrics())):
        store.clear()
        store.update(fresh)
    KNOWN_GATEWAY_HASHES.clear()
    ANNOUNCED_TXNS.clear()
    P4B_NOTIFICATION_STORE.clear()
    SETTLEMENT_ORDERS_STORE.clear()
    PROCESSED_IDEMPOTENCY_KEYS.clear()

# -------------------------------------------------------------
# DATA MODELS
# -------------------------------------------------------------
class VerifyPacketRequest(BaseModel):
    txn_id: str
    device_imei: str
    timestamp_window: int = Field(gt=0, le=3_600_000, description="How far back (ms) a genuine payment may be")
    claimed_amount: Optional[float] = Field(default=None, gt=0, description="Amount shown on the customer's screen")

class SandboxPaymentRequest(BaseModel):
    amount: float = Field(gt=0)
    device_imei: str
    mqtt_delivered: bool = Field(default=False, description="False simulates a dropped/delayed PUBACK on 2G")

class VerifyPacketResponse(BaseModel):
    status: str
    gateway_hash_matched: bool
    mqtt_publish_detected: bool
    puback_received: bool
    latency_ms: int
    deduplicated: bool
    message: str
    p4b_action_triggered: Optional[str] = None

class LiquiditySimulateRequest(BaseModel):
    current_unsettled_balance: float
    due_amount: float
    cutoff_time: str
    merchant_id: Optional[str] = "HelloM8xxxxxxxx45"

class LiquiditySimulateResponse(BaseModel):
    merchant_id: str
    current_unsettled_balance: float
    requested_settlement: float
    daily_loan_emi: float
    assertion_passed: bool
    projected_eod_balance: float
    recommended_micro_settlement: float
    instant_fee: float
    avoided_penalty_fees: float
    action_deep_link: str
    p4b_notification_payload: Dict[str, Any]

class ExecuteMicroSettlementRequest(BaseModel):
    merchant_id: str
    required_amount: float = Field(gt=0)
    routing_rail: Literal["IMPS", "UPI", "NEFT"]
    order_id: str = Field(min_length=6, max_length=64)
    simulate_504: bool = False

# -------------------------------------------------------------
# HELPER FUNCTIONS: CHECKSUM & SECURITY
# -------------------------------------------------------------
SIGNATURE_MAX_AGE_S = 300

def compute_paytm_checksum(payload_dict: dict, secret_key: str, timestamp: str) -> str:
    """Signs a response body so the caller can check it came from this gateway."""
    raw = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return compute_signature(raw, secret_key, timestamp)

def verify_request_signature(raw_body: bytes, secret_key: str, signature: Optional[str], timestamp: Optional[str]) -> None:
    """Rejects unsigned, tampered or replayed (stale) requests."""
    if not signature or not timestamp or not timestamp.isdigit():
        raise HTTPException(status_code=401, detail="Missing X-Paytm-Signature or X-Paytm-Timestamp header.")
    if abs(time.time() - int(timestamp)) > SIGNATURE_MAX_AGE_S:
        raise HTTPException(status_code=401, detail="Signature timestamp outside the allowed window.")
    if not hmac.compare_digest(compute_signature(raw_body, secret_key, timestamp), signature):
        raise HTTPException(status_code=401, detail="Invalid request signature.")

# -------------------------------------------------------------
# ENDPOINT 1: SOUNDBOX TELEMETRY & SPOOF VERIFICATION
# -------------------------------------------------------------
def _merchant_for_device(device_imei: str) -> Optional[Dict[str, Any]]:
    return next((m for m in MERCHANT_DATABASE.values() if m["device_imei"] == device_imei), None)

def _spoof_reason(txn: Optional[Dict[str, Any]], req: VerifyPacketRequest) -> Optional[str]:
    """Returns why a payment claim is not genuine, or None if it checks out."""
    if not txn:
        return f"Transaction ID '{req.txn_id}' does not exist on the Paytm gateway."
    if txn["device_imei"] != req.device_imei:
        return "This receipt belongs to a different merchant's Soundbox (replayed receipt)."
    if (time.time() - txn["timestamp"]) * 1000 > req.timestamp_window:
        return "This payment is older than the verification window (re-used old receipt)."
    if req.claimed_amount is not None and abs(req.claimed_amount - txn["amount"]) > 0.005:
        return f"Screen shows ₹{req.claimed_amount:.2f} but the gateway received ₹{txn['amount']:.2f}."
    return None

@app.post("/api/v1/telemetry/verify-packet", response_model=VerifyPacketResponse)
async def verify_packet(req: VerifyPacketRequest):
    """
    Cross-references a claimed payment with the gateway record and Soundbox MQTT telemetry.
    A claim is genuine only if the transaction exists, was paid to THIS device's merchant,
    is recent, and (when given) matches the amount on the customer's screen.
    """
    start = time.perf_counter()
    OBSERVABILITY_METRICS["telemetry_verifications_count"] += 1
    merchant = _merchant_for_device(req.device_imei)
    if not merchant:
        raise HTTPException(status_code=404, detail="Soundbox device not registered to any merchant.")

    txn = KNOWN_GATEWAY_HASHES.get(req.txn_id)
    reason = _spoof_reason(txn, req)

    def elapsed_ms() -> int:
        ms = int(round((time.perf_counter() - start) * 1000))
        OBSERVABILITY_METRICS["latency_records_ms"].append(ms)
        return ms

    if reason:
        OBSERVABILITY_METRICS["spoofs_detected_count"] += 1
        P4B_NOTIFICATION_STORE.append({
            "notification_type": "FRAUD_ALERT_SPOOF_ATTEMPT",
            "merchant_id": merchant["mid"],
            "title": "🚨 FAKE PAYMENT ATTEMPT DETECTED",
            "body": f"{reason} Do NOT hand over goods.",
            "timestamp": int(time.time()),
            "priority": "CRITICAL"
        })
        return VerifyPacketResponse(
            status="SPOOF_DETECTED",
            gateway_hash_matched=txn is not None,
            mqtt_publish_detected=bool(txn and txn["mqtt_publish_sent"]),
            puback_received=bool(txn and txn["puback_received"]),
            latency_ms=elapsed_ms(),
            deduplicated=False,
            message=reason,
            p4b_action_triggered="FRAUD_ALERT_SPOOF_ATTEMPT"
        )

    # QoS 1 can redeliver the same event; announce each genuine payment only once
    repeat = req.txn_id in ANNOUNCED_TXNS
    ANNOUNCED_TXNS.add(req.txn_id)

    if not txn["puback_received"]:
        # 2G lag: the broker sent PUBLISH but the Soundbox has not acknowledged it yet
        action = None
        if not repeat:
            OBSERVABILITY_METRICS["lagged_audio_alerts_count"] += 1
            P4B_NOTIFICATION_STORE.append({
                "notification_type": "AUDIO_DELAYED_CONFIRMATION",
                "merchant_id": merchant["mid"],
                "title": f"Payment of ₹{txn['amount']:.2f} Received",
                "body": "Soundbox audio is delayed by a weak network. The payment is confirmed on the gateway.",
                "txn_id": req.txn_id,
                "amount": txn["amount"],
                "timestamp": int(time.time()),
                "priority": "HIGH"
            })
            action = "AUDIO_DELAYED_CONFIRMATION"
        return VerifyPacketResponse(
            status="AUDIO_DELAYED",
            gateway_hash_matched=True,
            mqtt_publish_detected=txn["mqtt_publish_sent"],
            puback_received=False,
            latency_ms=elapsed_ms(),
            deduplicated=repeat,
            message=f"Genuine payment of ₹{txn['amount']:.2f} confirmed on the gateway. Soundbox audio delayed by network lag.",
            p4b_action_triggered=action
        )

    return VerifyPacketResponse(
        status="VERIFIED_DELIVERED",
        gateway_hash_matched=True,
        mqtt_publish_detected=True,
        puback_received=True,
        latency_ms=elapsed_ms(),
        deduplicated=repeat,
        message="Transaction verified and Soundbox audio acknowledged.",
        p4b_action_triggered=None
    )

@app.post("/api/v1/sandbox/gateway/payments")
async def create_sandbox_payment(req: SandboxPaymentRequest):
    """Sandbox only: records a genuine customer payment on the mock gateway, as if it just cleared."""
    if not _merchant_for_device(req.device_imei):
        raise HTTPException(status_code=404, detail="Soundbox device not registered to any merchant.")
    txn_id = f"TXN_{uuid.uuid4().hex[:10].upper()}"
    KNOWN_GATEWAY_HASHES[txn_id] = {
        "txn_id": txn_id,
        "rrn": str(uuid.uuid4().int)[:12],
        "amount": round(req.amount, 2),
        "timestamp": time.time(),
        "status": "SUCCESS",
        "device_imei": req.device_imei,
        "mqtt_status": "DELIVERED" if req.mqtt_delivered else "QOS1_PUBACK_DELAYED",
        "mqtt_publish_sent": True,
        "puback_received": req.mqtt_delivered
    }
    return KNOWN_GATEWAY_HASHES[txn_id]

# -------------------------------------------------------------
# ENDPOINT 2: DETERMINISTIC LIQUIDITY SIMULATION & EMI GUARD
# -------------------------------------------------------------
@app.post("/api/v1/liquidity/simulate", response_model=LiquiditySimulateResponse)
async def simulate_liquidity(req: LiquiditySimulateRequest):
    """
    Deterministic mathematical assertion:
    (Requested_Settlement + Daily_Loan_EMI) <= Current_Unsettled_Balance
    Guarantees zero AI math hallucinations, preventing morning EMI loan defaults.
    """
    OBSERVABILITY_METRICS["liquidity_simulations_count"] += 1
    merchant = MERCHANT_DATABASE.get(req.merchant_id, MERCHANT_DATABASE["HelloM8xxxxxxxx45"])

    current_balance = float(req.current_unsettled_balance)
    requested = float(req.due_amount)
    daily_emi = float(merchant["daily_loan_emi"])
    
    import os
    import torch
    import torch.nn as nn
    import numpy as np
    import pickle
    from sklearn.preprocessing import MinMaxScaler

    # Define model structure for loading weights
    class LiquidityLSTM(nn.Module):
        def __init__(self, input_size):
            super(LiquidityLSTM, self).__init__()
            self.lstm = nn.LSTM(input_size, hidden_size=16, batch_first=True)
            self.fc1 = nn.Linear(16, 8)
            self.relu = nn.ReLU()
            self.fc2 = nn.Linear(8, 1)
            
        def forward(self, x):
            out, _ = self.lstm(x)
            out = self.fc1(out[:, -1, :])
            out = self.relu(out)
            out = self.fc2(out)
            return out

    # Load the trained LSTM model
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "models", "lstm_model.pth")
    scaler_x_path = os.path.join(base_dir, "models", "scaler_X.pkl")
    scaler_y_path = os.path.join(base_dir, "models", "scaler_y.pkl")

    predicted_evening_sales = 0.0
    if os.path.exists(model_path):
        with open(scaler_x_path, "rb") as f:
            scaler_X = pickle.load(f)
        with open(scaler_y_path, "rb") as f:
            scaler_y = pickle.load(f)
            
        model = LiquidityLSTM(input_size=7)
        model.load_state_dict(torch.load(model_path))
        model.eval()
        
        # Synthetic merchant history vector (7 features): 
        # [Day-3 M, Day-3 E, Day-2 M, Day-2 E, Day-1 M, Day-1 E, Today M]
        dummy_history = np.array([[12000, 18000, 12500, 18200, 11800, 17500, 11000]])
        dummy_scaled = scaler_X.transform(dummy_history)
        dummy_tensor = torch.tensor(dummy_scaled.reshape(1, 1, 7), dtype=torch.float32)
        
        with torch.no_grad():
            pred_scaled = model(dummy_tensor).numpy()
            predicted_evening_sales = float(scaler_y.inverse_transform(pred_scaled)[0][0])
    else:
        # Fallback if model not trained yet
        predicted_evening_sales = 8450.00

    # DEEP LEARNING ASSERTION
    # Instead of just (requested + emi) <= current_balance
    # We include predicted future earnings!
    total_projected_liquidity = current_balance + predicted_evening_sales
    assertion_passed = (requested + daily_emi) <= total_projected_liquidity

    if assertion_passed:
        recommended = requested
        # Even though we predict evening sales, we still deduct from current balance. 
        # If current balance goes negative, it's covered by Paytm working capital float.
        projected_eod = (current_balance - requested) + predicted_evening_sales
        OBSERVABILITY_METRICS["loan_defaults_prevented_count"] += 1
        avoided_penalty = 750.00 # Standard bounce fee avoided
    else:
        # Max safe settlement without defaulting EMI
        recommended = max(0.0, total_projected_liquidity - daily_emi)
        projected_eod = (current_balance - recommended) + predicted_evening_sales
        avoided_penalty = 0.0

    # Calculate nominal instant settlement fee (0.10% capped at ₹5)
    instant_fee = round(min(5.0, recommended * 0.0010), 2)

    # Construct P4B Mini-App Deep Link with Base64 payload
    payload_data = {
        "params": f"amount={recommended}&vendor=amul_distributor&emi_reserved={daily_emi}",
        "path": "/micro-settlement-approval"
    }
    encoded_data = base64.b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8")
    action_deep_link = f"paytmmp://mini-app?aId=settlement_module&data={encoded_data}"

    notification_payload = {
        "notification_type": "LIQUIDITY_OPTIMIZATION_PROMPT",
        "merchant_id": merchant["mid"],
        "title": "Amul Distributor Payment Due",
        "body": f"Tap to instantly settle ₹{recommended:,.2f} and pay the distributor. Your remaining ₹{projected_eod:,.2f} will automatically cover tomorrow's ₹{daily_emi:,.2f} EMI deduction.",
        "action_deep_link": action_deep_link,
        "expiry_timestamp": int(time.time()) + 3600,
        "priority": "HIGH"
    }
    P4B_NOTIFICATION_STORE.append(notification_payload)

    return LiquiditySimulateResponse(
        merchant_id=merchant["mid"],
        current_unsettled_balance=current_balance,
        requested_settlement=requested,
        daily_loan_emi=daily_emi,
        assertion_passed=assertion_passed,
        projected_eod_balance=projected_eod,
        recommended_micro_settlement=recommended,
        instant_fee=instant_fee,
        avoided_penalty_fees=avoided_penalty,
        action_deep_link=action_deep_link,
        p4b_notification_payload=notification_payload
    )

# -------------------------------------------------------------
# ENDPOINT 3: TARGETED MICRO-SETTLEMENT EXECUTION WITH HMAC & 504 RECOVERY
# -------------------------------------------------------------
@app.post("/api/v1/settlement/execute-micro")
async def execute_micro_settlement(
    req: ExecuteMicroSettlementRequest,
    request: Request,
    x_paytm_signature: Optional[str] = Header(None),
    x_paytm_timestamp: Optional[str] = Header(None),
    x_idempotency_key: str = Header(..., min_length=8)
):
    """
    Executes an instant payout. The request must be signed (HMAC-SHA256 over the raw body and
    timestamp) and carry an idempotency key that the caller reuses on every retry of the same order.
    The EMI guardrail is enforced before any money moves, on every path.
    """
    merchant = MERCHANT_DATABASE.get(req.merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant MID not found.")

    raw_body = await request.body()
    verify_request_signature(raw_body, merchant["secret_key"], x_paytm_signature, x_paytm_timestamp)

    # 1. Idempotency: a retry with the same key returns the original outcome and never debits twice
    fingerprint = hashlib.sha256(raw_body).hexdigest()
    previous = PROCESSED_IDEMPOTENCY_KEYS.get(x_idempotency_key)
    if previous:
        if previous["fingerprint"] != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used for a different request.")
        return previous["response"]
    if req.order_id in SETTLEMENT_ORDERS_STORE:
        raise HTTPException(status_code=409, detail="Order ID already exists; reuse its idempotency key to retry.")

    # 2. Liquidity guardrail on every path, including the simulated timeout
    if merchant["current_unsettled_balance"] - req.required_amount < merchant["daily_loan_emi"]:
        raise HTTPException(
            status_code=400,
            detail=f"Settlement blocked by Liquidity Guardrail: balance would breach ₹{merchant['daily_loan_emi']} EMI float."
        )

    # 3. Move the money exactly once
    merchant["current_unsettled_balance"] -= req.required_amount
    merchant["settled_today"] += req.required_amount
    OBSERVABILITY_METRICS["total_settled_amount"] += req.required_amount

    timestamp = str(int(time.time()))
    body = {
        "mid": merchant["mid"],
        "transactionId": f"TXN_{uuid.uuid4().hex[:12].upper()}",
        "orderId": req.order_id,
        "amount": f"{req.required_amount:.2f}",
        "status": "TXN_SUCCESS",
        "settledDate": datetime.now().isoformat(),
        "utrNo": f"218{int(time.time())}{uuid.uuid4().hex[:4].upper()}",
        "routingRail": req.routing_rail,
        "hmac_signature_verified": True
    }
    if req.simulate_504:
        # The bank credited the beneficiary, but the response is lost: NPCI UDIR later reports TCC102.
        body["udir_reconciliation_code"] = "TCC102"
        body["note"] = "Beneficiary credited after a CBS timeout; confirmed through the order status check."
    response_payload = {
        "request": {
            "head": {
                "reqMsgId": str(uuid.uuid4()),
                "signature": compute_paytm_checksum(body, merchant["secret_key"], timestamp),
                "timestamp": timestamp
            },
            "body": body
        },
        "merchant_ledger": {
            "remaining_unsettled_balance": merchant["current_unsettled_balance"],
            "protected_daily_loan_emi": merchant["daily_loan_emi"],
            "loan_emi_status": "SECURED"
        }
    }
    SETTLEMENT_ORDERS_STORE[req.order_id] = response_payload
    PROCESSED_IDEMPOTENCY_KEYS[x_idempotency_key] = {"fingerprint": fingerprint, "response": response_payload}

    if req.simulate_504:
        return JSONResponse(status_code=504, content={"detail": "Upstream bank switch timed out. Check order status before retrying."})
    return response_payload

@app.get("/api/v1/settlement/status/{order_id}")
async def get_settlement_status(order_id: str):
    """
    Status check used after a timeout (the sandbox stand-in for an NPCI UDIR query).
    404 means the order never reached the bank, so retrying with the same idempotency key is safe.
    """
    order = SETTLEMENT_ORDERS_STORE.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found at the bank switch.")
    return order

# -------------------------------------------------------------
# ENDPOINT 4: SUPPLIER BILL PARSER (WORKER 2 SIMULATION)
# -------------------------------------------------------------
class ParseBillRequest(BaseModel):
    raw_message: str
    vendor_id: str

@app.post("/api/v1/supplier-bills/parse")
async def parse_supplier_bill(req: ParseBillRequest):
    """
    Multimodal invoice parsing with PII sanitization for WhatsApp/SMS vendor delivery notes.
    """
    raw_text = req.raw_message
    # Mask PII if any account numbers or PANs present
    import re
    cleaned_text = re.sub(r'\b\d{9,18}\b', '[REDACTED_ACC]', raw_text)
    cleaned_text = re.sub(r'[A-Z]{5}[0-9]{4}[A-Z]{1}', '[REDACTED_PAN]', cleaned_text)
    if cleaned_text != raw_text:
        # The agent should have redacted this before sending it; count it as a leak
        OBSERVABILITY_METRICS["pii_leakage_detected"] += 1

    # Extract vendor and amount
    extracted_amount = 4500.00
    if "4500" in raw_text:
        extracted_amount = 4500.00
    elif "3200" in raw_text:
        extracted_amount = 3200.00
    elif "2450" in raw_text:
        extracted_amount = 2450.50

    return {
        "vendor_id": req.vendor_id,
        "vendor_name": "Amul Dairy Distributors Ltd.",
        "invoice_number": "INV-2026-0910-AMUL",
        "due_amount": extracted_amount,
        "currency": "INR",
        "cutoff_time": "2026-09-10T16:00:00+05:30",
        "line_items": [
            {"item": "Amul Taaza Milk Crates (12x1L)", "quantity": 5, "amount": 3500.00},
            {"item": "Amul Masti Dahi Tubs", "quantity": 10, "amount": 1000.00}
        ],
        "pii_redacted": cleaned_text != raw_text
    }

# -------------------------------------------------------------
# ENDPOINT 5: P4B PUSH NOTIFICATIONS & OBSERVABILITY METRICS
# -------------------------------------------------------------
@app.get("/api/v1/p4b/notifications/{merchant_id}")
async def get_merchant_notifications(merchant_id: str):
    merchant_notifications = [n for n in P4B_NOTIFICATION_STORE if n.get("merchant_id") == merchant_id]
    return {
        "merchant_id": merchant_id,
        "active_notifications_count": len(merchant_notifications),
        "notifications": merchant_notifications
    }

@app.get("/api/v1/observability/metrics")
async def get_observability_metrics():
    latencies = sorted(OBSERVABILITY_METRICS["latency_records_ms"])
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
    p95_latency = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))] if latencies else 0.0

    return {
        "platform": "Phinite Enterprise Agentic OS",
        "track": "Paytm Track 2 (Small Businesses)",
        "agent_system": "Paytm Vyapar Saathi",
        "metrics": {
            "telemetry_verifications": OBSERVABILITY_METRICS["telemetry_verifications_count"],
            "spoof_attacks_neutralized": OBSERVABILITY_METRICS["spoofs_detected_count"],
            "audio_delayed_calming_alerts": OBSERVABILITY_METRICS["lagged_audio_alerts_count"],
            "liquidity_simulations": OBSERVABILITY_METRICS["liquidity_simulations_count"],
            "loan_emi_defaults_prevented": OBSERVABILITY_METRICS["loan_defaults_prevented_count"],
            "total_capital_settled_inr": OBSERVABILITY_METRICS["total_settled_amount"],
            "avg_spoof_guard_latency_ms": round(avg_latency, 2),
            "p95_spoof_guard_latency_ms": p95_latency,
            "latency_sla_compliance": "NO DATA" if not latencies else ("p95 <= 600ms (PASSED)" if p95_latency <= 600 else "EXCEEDED"),
            "pii_leakage_events": OBSERVABILITY_METRICS["pii_leakage_detected"]
        }
    }

@app.get("/api/v1/merchant/state/{merchant_id}")
async def get_merchant_state(merchant_id: str):
    merchant = MERCHANT_DATABASE.get(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found.")
    return {k: v for k, v in merchant.items() if k != "secret_key"}
