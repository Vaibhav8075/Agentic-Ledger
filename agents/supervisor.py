"""
Master / Supervisory Agent: Paytm Vyapar Saathi Orchestrator
Coordinates child workers, maintains merchant session state,
and executes cryptographically signed Paytm settlement actions.
"""

import httpx
from typing import Any, Dict, Optional
from agents.spoof_guard import SpoofGuardAgent
from agents.supplier_ledger import SupplierLedgerAgent
from agents.liquidity_engine import LiquidityEngineAgent
from agents.guardrails import sign_paytm_request

class MasterSupervisorAgent:
    def __init__(self, backend_url: str = "http://127.0.0.1:8000"):
        self.backend_url = backend_url
        self.name = "MasterSupervisorOrchestrator"

        # Initialize Child Workers
        self.spoof_guard = SpoofGuardAgent(backend_url)
        self.supplier_ledger = SupplierLedgerAgent(backend_url)
        self.liquidity_engine = LiquidityEngineAgent(backend_url)

    async def handle_soundbox_event(self, txn_id: str, device_imei: str) -> Dict[str, Any]:
        """
        Dispatches to Worker 1 (Spoof Guard) for rapid verification.
        """
        return await self.spoof_guard.verify_transaction(txn_id=txn_id, device_imei=device_imei)

    async def handle_incoming_bill(self, raw_message: str, vendor_id: str) -> Dict[str, Any]:
        """
        Dispatches to Worker 2 (Supplier Ledger) for bill parsing.
        """
        return await self.supplier_ledger.parse_invoice(raw_message=raw_message, vendor_id=vendor_id)

    async def optimize_cashflow(
        self,
        current_unsettled_balance: float,
        due_amount: float,
        cutoff_time: str,
        merchant_id: str = "HelloM8xxxxxxxx45"
    ) -> Dict[str, Any]:
        """
        Dispatches to Worker 3 (Liquidity Engine) for EMI assertion.
        """
        return await self.liquidity_engine.simulate_cashflow(
            current_unsettled_balance=current_unsettled_balance,
            due_amount=due_amount,
            cutoff_time=cutoff_time,
            merchant_id=merchant_id
        )

    async def execute_settlement(
        self,
        merchant_id: str,
        required_amount: float,
        routing_rail: str = "IMPS",
        simulate_504: bool = False
    ) -> Dict[str, Any]:
        """
        Executes instant micro-settlement against the mock Paytm Settlement API
        using HMAC-SHA256 signature and handling 504 timeout recovery.
        """
        url = f"{self.backend_url}/api/v1/settlement/execute-micro"
        payload = {
            "merchant_id": merchant_id,
            "required_amount": required_amount,
            "routing_rail": routing_rail,
            "simulate_504": simulate_504
        }

        # Generate HMAC-SHA256 signature
        secret_key = "secret_merchant_key_prod_09a7b"
        auth_head = sign_paytm_request(payload, secret_key)
        headers = {
            "X-Paytm-Signature": auth_head["signature"],
            "X-Idempotency-Key": f"IDEMP_MICRO_{int(auth_head['timestamp'])}"
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
