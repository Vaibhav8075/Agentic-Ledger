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
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config
from agents.guardrails import compute_signature, plan_supplier_payment, sanitize_pii
from agents.invoice_parser import InvoiceParseError, parse_invoice
from ml.forecaster import Forecaster

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
            "current_unsettled_balance": 6000.00,   # today's collections not yet settled (16:00)
            "daily_loan_emi": 3000.00,              # auto-deducted from the 05:00 T+1 batch
            "advance_limit": 5000.00,               # pre-approved short advance (mock lending policy)
            # [morning, evening] sales for the last 3 days and today's sales so far (mock history)
            "sales_history": {"past_days": [[5800.0, 8900.0], [6200.0, 9400.0], [5600.0, 8600.0]], "today_morning": 6000.0},
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
        "emi_breaches_prevented_count": 0,  # bills that would have eaten into the EMI reserve
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
    merchant_id: str = config.DEMO_MERCHANT_ID
    due_amount: float = Field(gt=0)
    cutoff_time: Optional[str] = None
    vendor_id: str = "supplier"

class LiquiditySimulateResponse(BaseModel):
    merchant_id: str
    current_unsettled_balance: float
    requested_settlement: float
    daily_loan_emi: float
    advance_limit: float
    assertion_passed: bool  # strict check without any forecast: due + EMI <= balance
    decision: Literal["PAY_FROM_BALANCE", "PAY_WITH_ADVANCE", "PARTIAL_PAYMENT"]
    safe_settlement_limit: float
    recommended_micro_settlement: float
    advance_amount: float
    unpaid_amount: float
    evening_forecast_expected: float
    evening_forecast_floor: float
    projected_eod_balance: float  # unsettled balance left after settling now (still covers the EMI)
    instant_fee: float
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

@app.post("/api/v1/sandbox/reset")
async def reset_sandbox():
    """Sandbox only: restores the seeded merchant ledger and clears payments, orders and metrics."""
    reset_state()
    return {"status": "reset"}

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
@lru_cache(maxsize=1)
def get_forecaster() -> Forecaster:
    """Loads the evening-revenue model once per process."""
    return Forecaster.load()

def _notification_text(plan: Dict[str, Any], vendor: str, emi: float) -> str:
    if plan["decision"] == "PAY_FROM_BALANCE":
        return f"Tap to settle ₹{plan['settle_now_amount']:,.2f} and pay {vendor}. ₹{emi:,.2f} stays reserved for tomorrow's EMI."
    if plan["decision"] == "PAY_WITH_ADVANCE":
        return (f"Pay {vendor} now: ₹{plan['settle_now_amount']:,.2f} from your balance + a ₹{plan['advance_amount']:,.2f} advance, "
                f"repaid from tonight's sales. Your ₹{emi:,.2f} EMI stays covered. Tap to accept.")
    return (f"You can safely pay {vendor} ₹{plan['settle_now_amount']:,.2f} now. Paying more would put tomorrow's "
            f"₹{emi:,.2f} EMI at risk; ask them to collect ₹{plan['unpaid_amount']:,.2f} later.")

@app.post("/api/v1/liquidity/simulate", response_model=LiquiditySimulateResponse)
async def simulate_liquidity(req: LiquiditySimulateRequest):
    """
    Plans a supplier payment without ever touching the EMI reserve.
    The balance comes from the ledger (not the caller). The LSTM forecast of tonight's sales is
    only used through its conservative floor, to size an optional short advance.
    """
    merchant = MERCHANT_DATABASE.get(req.merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant MID not found.")
    OBSERVABILITY_METRICS["liquidity_simulations_count"] += 1

    balance = float(merchant["current_unsettled_balance"])
    emi = float(merchant["daily_loan_emi"])
    try:
        history = merchant["sales_history"]
        forecast = get_forecaster().predict(history["past_days"], history["today_morning"])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Forecaster unavailable: {exc}")

    plan = plan_supplier_payment(balance, req.due_amount, emi, forecast.floor, merchant["advance_limit"])
    strict_ok = req.due_amount + emi <= balance
    if not strict_ok:
        OBSERVABILITY_METRICS["emi_breaches_prevented_count"] += 1

    # Nominal instant settlement fee (0.10% capped at ₹5)
    instant_fee = round(min(5.0, plan["settle_now_amount"] * 0.0010), 2)

    payload_data = {
        "params": (f"amount={plan['settle_now_amount']}&advance={plan['advance_amount']}"
                   f"&vendor={req.vendor_id}&emi_reserved={emi}"),
        "path": "/micro-settlement-approval"
    }
    encoded_data = base64.b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8")
    action_deep_link = f"paytmmp://mini-app?aId=settlement_module&data={encoded_data}"

    notification_payload = {
        "notification_type": "LIQUIDITY_OPTIMIZATION_PROMPT",
        "merchant_id": merchant["mid"],
        "title": f"Supplier payment due: ₹{req.due_amount:,.2f}",
        "body": _notification_text(plan, req.vendor_id, emi),
        "action_deep_link": action_deep_link,
        "expiry_timestamp": int(time.time()) + 3600,
        "priority": "HIGH"
    }
    P4B_NOTIFICATION_STORE.append(notification_payload)

    return LiquiditySimulateResponse(
        merchant_id=merchant["mid"],
        current_unsettled_balance=balance,
        requested_settlement=req.due_amount,
        daily_loan_emi=emi,
        advance_limit=merchant["advance_limit"],
        assertion_passed=strict_ok,
        decision=plan["decision"],
        safe_settlement_limit=plan["safe_settlement_limit"],
        recommended_micro_settlement=plan["settle_now_amount"],
        advance_amount=plan["advance_amount"],
        unpaid_amount=plan["unpaid_amount"],
        evening_forecast_expected=forecast.expected,
        evening_forecast_floor=forecast.floor,
        projected_eod_balance=round(balance - plan["settle_now_amount"], 2),
        instant_fee=instant_fee,
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
    raw_message: str = Field(min_length=1, max_length=5000)
    vendor_id: str

@app.post("/api/v1/supplier-bills/parse")
async def parse_supplier_bill(req: ParseBillRequest):
    """
    Extracts a structured payment obligation from a WhatsApp/SMS supplier message.
    PII should already be masked by the agent; anything still found here counts as a leak
    and is masked before parsing.
    """
    cleaned_text, leaked = sanitize_pii(req.raw_message)
    if leaked:
        OBSERVABILITY_METRICS["pii_leakage_detected"] += 1
    try:
        bill = parse_invoice(cleaned_text, req.vendor_id)
    except InvoiceParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    bill["pii_redacted"] = leaked
    return bill

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
            "emi_breaches_prevented": OBSERVABILITY_METRICS["emi_breaches_prevented_count"],
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
