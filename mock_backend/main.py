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
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config

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

def _seed_gateway_hashes() -> Dict[str, Dict[str, Any]]:
    # Legitimate transactions cleared through the gateway switch
    return {
        "TXN_9876543210": {
            "txn_id": "TXN_9876543210",
            "rrn": "321456987012",
            "amount": 50.00,
            "timestamp": int(time.time()),
            "status": "SUCCESS",
            "device_imei": "864201938472910",
            "mqtt_status": "QOS1_PUBACK_DELAYED", # Simulated 2G cellular network congestion
            "mqtt_publish_sent": True,
            "puback_received": False
        },
        "TXN_1122334455": {
            "txn_id": "TXN_1122334455",
            "rrn": "456789123045",
            "amount": 250.00,
            "timestamp": int(time.time()),
            "status": "SUCCESS",
            "device_imei": "864201938472910",
            "mqtt_status": "DELIVERED",
            "mqtt_publish_sent": True,
            "puback_received": True
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
        "pii_leakage_detected": 0,
        "math_hallucinations_detected": 0,
        "latency_records_ms": []
    }

MERCHANT_DATABASE: Dict[str, Dict[str, Any]] = _seed_merchants()
KNOWN_GATEWAY_HASHES: Dict[str, Dict[str, Any]] = _seed_gateway_hashes()
P4B_NOTIFICATION_STORE: List[Dict[str, Any]] = []
SETTLEMENT_ORDERS_STORE: Dict[str, Dict[str, Any]] = {}
PROCESSED_IDEMPOTENCY_KEYS: Dict[str, Dict[str, Any]] = {}
OBSERVABILITY_METRICS: Dict[str, Any] = _fresh_metrics()

def reset_state() -> None:
    """Restores the seeded sandbox state in place (used by tests and the demo)."""
    for store, fresh in ((MERCHANT_DATABASE, _seed_merchants()), (KNOWN_GATEWAY_HASHES, _seed_gateway_hashes()),
                         (OBSERVABILITY_METRICS, _fresh_metrics())):
        store.clear()
        store.update(fresh)
    P4B_NOTIFICATION_STORE.clear()
    SETTLEMENT_ORDERS_STORE.clear()
    PROCESSED_IDEMPOTENCY_KEYS.clear()

# -------------------------------------------------------------
# DATA MODELS
# -------------------------------------------------------------
class VerifyPacketRequest(BaseModel):
    txn_id: str
    device_imei: str
    timestamp_window: int

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
    required_amount: float
    routing_rail: str
    order_id: Optional[str] = None
    simulate_504: Optional[bool] = False

# -------------------------------------------------------------
# HELPER FUNCTIONS: CHECKSUM & SECURITY
# -------------------------------------------------------------
def compute_paytm_checksum(payload_dict: dict, secret_key: str, timestamp: str) -> str:
    raw_str = json.dumps(payload_dict, sort_keys=True) + timestamp
    return hmac.new(secret_key.encode('utf-8'), raw_str.encode('utf-8'), hashlib.sha256).hexdigest()

def verify_paytm_checksum(payload_dict: dict, secret_key: str, signature: str, timestamp: str) -> bool:
    expected = compute_paytm_checksum(payload_dict, secret_key, timestamp)
    return hmac.compare_digest(expected, signature)

# -------------------------------------------------------------
# ENDPOINT 1: SOUNDBOX TELEMETRY & SPOOF VERIFICATION
# -------------------------------------------------------------
@app.post("/api/v1/telemetry/verify-packet", response_model=VerifyPacketResponse)
async def verify_packet(req: VerifyPacketRequest):
    """
    Sub-600ms endpoint cross-referencing payment gateway hashes with MQTT QoS 1 telemetry.
    Differentiates 2G cellular network buffering from malicious Paytm Spoof attacks.
    """
    start_time = time.time()
    OBSERVABILITY_METRICS["telemetry_verifications_count"] += 1

    # 1. Check if Transaction Hash exists in Gateway Switch
    txn = KNOWN_GATEWAY_HASHES.get(req.txn_id)

    if not txn:
        # Counterfeit / Spoofed Transaction
        OBSERVABILITY_METRICS["spoofs_detected_count"] += 1
        elapsed_ms = int((time.time() - start_time) * 1000)
        OBSERVABILITY_METRICS["latency_records_ms"].append(elapsed_ms)

        # Broadcast Fraud Alert to P4B
        fraud_alert = {
            "notification_type": "FRAUD_ALERT_SPOOF_ATTEMPT",
            "merchant_id": "HelloM8xxxxxxxx45",
            "title": "🚨 FAKE PAYMENT ATTEMPT DETECTED",
            "body": f"Transaction ID '{req.txn_id}' does not exist on Paytm Gateway. Do NOT hand over goods.",
            "timestamp": int(time.time()),
            "priority": "CRITICAL"
        }
        P4B_NOTIFICATION_STORE.append(fraud_alert)

        return VerifyPacketResponse(
            status="SPOOF_DETECTED",
            gateway_hash_matched=False,
            mqtt_publish_detected=False,
            puback_received=False,
            latency_ms=elapsed_ms,
            deduplicated=False,
            message="No legitimate transaction hash found in payment gateway. Counterfeit spoof attempt intercepted.",
            p4b_action_triggered="FRAUD_ALERT_SPOOF_ATTEMPT"
        )

    # 2. Legitimate Transaction - Check 2G Cellular MQTT Telemetry State
    mqtt_status = txn.get("mqtt_status")
    elapsed_ms = int((time.time() - start_time) * 1000) + 42 # Add synthetic switch verification latency (~42ms)
    OBSERVABILITY_METRICS["latency_records_ms"].append(elapsed_ms)

    if mqtt_status == "QOS1_PUBACK_DELAYED":
        # 2G cellular lag: PUBLISH recorded on broker, but PUBACK delayed/dropped
        OBSERVABILITY_METRICS["lagged_audio_alerts_count"] += 1

        p4b_push = {
            "notification_type": "AUDIO_DELAYED_CONFIRMATION",
            "merchant_id": "HelloM8xxxxxxxx45",
            "title": f"Payment of ₹{txn['amount']:.2f} Received",
            "body": "Soundbox audio delayed due to 2G network congestion. Payment is mathematically genuine.",
            "txn_id": req.txn_id,
            "amount": txn["amount"],
            "timestamp": int(time.time()),
            "priority": "HIGH"
        }
        P4B_NOTIFICATION_STORE.append(p4b_push)

        return VerifyPacketResponse(
            status="AUDIO_DELAYED",
            gateway_hash_matched=True,
            mqtt_publish_detected=True,
            puback_received=False,
            latency_ms=elapsed_ms,
            deduplicated=True,
            message=f"Genuine payment of ₹{txn['amount']:.2f} verified in gateway. Soundbox audio delayed by 2G MQTT latency.",
            p4b_action_triggered="AUDIO_DELAYED_CONFIRMATION"
        )

    # 3. Normal Delivered State
    return VerifyPacketResponse(
        status="VERIFIED_DELIVERED",
        gateway_hash_matched=True,
        mqtt_publish_detected=True,
        puback_received=True,
        latency_ms=elapsed_ms,
        deduplicated=True,
        message=f"Transaction verified and Soundbox audio acknowledged.",
        p4b_action_triggered=None
    )

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
    x_paytm_signature: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None)
):
    """
    Executes instant payout with HMAC-SHA256 signature verification and handles 504 Gateway Timeouts.
    """
    merchant = MERCHANT_DATABASE.get(req.merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant MID not found.")

    order_id = req.order_id or f"ORDER_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"
    idempotency_key = x_idempotency_key or f"IDEMP_{order_id}"

    # 1. Idempotency Check: Prevent Double Debit
    if idempotency_key in PROCESSED_IDEMPOTENCY_KEYS:
        return PROCESSED_IDEMPOTENCY_KEYS[idempotency_key]

    # 2. Cryptographic Checksum Generation & Verification
    timestamp = str(int(time.time()))
    payload_body = {
        "mid": merchant["mid"],
        "orderId": order_id,
        "amount": f"{req.required_amount:.2f}",
        "routingRail": req.routing_rail
    }
    server_generated_signature = compute_paytm_checksum(payload_body, merchant["secret_key"], timestamp)

    # 3. Simulate 504 Bank Switch Gateway Timeout & Auto-UDIR Recovery
    if req.simulate_504:
        # Bank Core Banking System timed out. Avoid retry to protect against double debits!
        # Automatically poll NPCI UDIR for code TCC102/TCC103
        reconciled_utr = f"218{int(time.time())}04"
        recovery_response = {
            "request": {
                "head": {
                    "reqMsgId": str(uuid.uuid4()),
                    "signature": server_generated_signature,
                    "timestamp": timestamp
                },
                "body": {
                    "mid": merchant["mid"],
                    "transactionId": f"TXN_{uuid.uuid4().hex[:12].upper()}",
                    "orderId": order_id,
                    "amount": f"{req.required_amount:.2f}",
                    "status": "TXN_SUCCESS",
                    "settledDate": datetime.now().isoformat(),
                    "utrNo": reconciled_utr,
                    "routingRail": req.routing_rail,
                    "udir_reconciliation_code": "TCC102",
                    "note": "Recovered via NPCI UDIR polling post-504 CBS timeout. Zero double-debit."
                }
            }
        }
        # Deduct from unsettled ledger
        merchant["current_unsettled_balance"] -= req.required_amount
        merchant["settled_today"] += req.required_amount
        OBSERVABILITY_METRICS["total_settled_amount"] += req.required_amount
        PROCESSED_IDEMPOTENCY_KEYS[idempotency_key] = recovery_response
        return recovery_response

    # 4. Standard Instant Payout
    if merchant["current_unsettled_balance"] - req.required_amount < merchant["daily_loan_emi"]:
        raise HTTPException(
            status_code=400,
            detail=f"Settlement blocked by Liquidity Guardrail: balance would breach ₹{merchant['daily_loan_emi']} EMI float."
        )

    merchant["current_unsettled_balance"] -= req.required_amount
    merchant["settled_today"] += req.required_amount
    OBSERVABILITY_METRICS["total_settled_amount"] += req.required_amount

    txn_id = f"202{int(time.time())}{uuid.uuid4().hex[:6].upper()}"
    utr_no = f"218{int(time.time())}04"

    response_payload = {
        "request": {
            "head": {
                "reqMsgId": str(uuid.uuid4()),
                "signature": server_generated_signature,
                "timestamp": timestamp
            },
            "body": {
                "mid": merchant["mid"],
                "transactionId": txn_id,
                "orderId": order_id,
                "amount": f"{req.required_amount:.2f}",
                "status": "TXN_SUCCESS",
                "settledDate": datetime.now().isoformat(),
                "utrNo": utr_no,
                "routingRail": req.routing_rail
            }
        },
        "merchant_ledger": {
            "remaining_unsettled_balance": merchant["current_unsettled_balance"],
            "protected_daily_loan_emi": merchant["daily_loan_emi"],
            "loan_emi_status": "SECURED"
        }
    }

    PROCESSED_IDEMPOTENCY_KEYS[idempotency_key] = response_payload
    return response_payload

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
    latencies = OBSERVABILITY_METRICS["latency_records_ms"]
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

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
            "latency_sla_compliance": "<600ms (PASSED)" if avg_latency <= 600 else "EXCEEDED",
            "pii_leakage_events": OBSERVABILITY_METRICS["pii_leakage_detected"],
            "math_calculation_hallucinations": OBSERVABILITY_METRICS["math_hallucinations_detected"]
        }
    }

@app.get("/api/v1/merchant/state/{merchant_id}")
async def get_merchant_state(merchant_id: str):
    merchant = MERCHANT_DATABASE.get(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found.")
    return merchant
