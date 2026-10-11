"""
Master / Supervisory Agent: Paytm Vyapar Saathi Orchestrator
Coordinates child workers, maintains merchant session state,
and executes cryptographically signed Paytm settlement actions.
"""

import asyncio
import uuid
import httpx
from typing import Any, Dict, Optional

import config
from agents.spoof_guard import SpoofGuardAgent
from agents.supplier_ledger import SupplierLedgerAgent
from agents.liquidity_engine import LiquidityEngineAgent
from agents.guardrails import canonical_body, sign_paytm_request

class MasterSupervisorAgent:
    def __init__(self, backend_url: str = config.BACKEND_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.backend_url = backend_url
        self.transport = transport
        self.name = "MasterSupervisorOrchestrator"

        # Initialize Child Workers
        self.spoof_guard = SpoofGuardAgent(backend_url, transport)
        self.supplier_ledger = SupplierLedgerAgent(backend_url, transport)
        self.liquidity_engine = LiquidityEngineAgent(backend_url, transport)

    async def handle_soundbox_event(self, txn_id: str, device_imei: str, claimed_amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Dispatches to Worker 1 (Spoof Guard) for rapid verification.
        """
        return await self.spoof_guard.verify_transaction(txn_id=txn_id, device_imei=device_imei, claimed_amount=claimed_amount)

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
        merchant_id: str = config.DEMO_MERCHANT_ID
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
        order_id: Optional[str] = None,
        simulate_504: bool = False,
        status_checks: int = 3
    ) -> Dict[str, Any]:
        """
        Executes an instant micro-settlement with a signed request.
        One order ID and one idempotency key are fixed up front and reused for every retry,
        so a timeout can never turn into a second payout.
        """
        order_id = order_id or f"ORD_{uuid.uuid4().hex[:16].upper()}"
        idempotency_key = f"IDEMP_{order_id}"
        body = canonical_body({
            "merchant_id": merchant_id,
            "order_id": order_id,
            "required_amount": round(float(required_amount), 2),
            "routing_rail": routing_rail,
            "simulate_504": simulate_504
        })

        async with httpx.AsyncClient(base_url=self.backend_url, timeout=5.0, transport=self.transport) as client:
            resp = await self._post_signed(client, body, idempotency_key)
            if resp.status_code == 504:
                # Never fire a fresh payout after a timeout: first ask the switch what happened.
                for attempt in range(status_checks):
                    status = await client.get(f"/api/v1/settlement/status/{order_id}")
                    if status.status_code == 200:
                        result = status.json()
                        result["recovered_after_timeout"] = True
                        return result
                    await asyncio.sleep(0.2 * (attempt + 1))
                # The order never reached the bank, so a retry with the same key is safe.
                resp = await self._post_signed(client, body, idempotency_key)
            resp.raise_for_status()
            return resp.json()

    async def _post_signed(self, client: httpx.AsyncClient, body: bytes, idempotency_key: str) -> httpx.Response:
        auth = sign_paytm_request(body, config.MERCHANT_SIGNING_KEY)
        headers = {
            "Content-Type": "application/json",
            "X-Paytm-Signature": auth["signature"],
            "X-Paytm-Timestamp": auth["timestamp"],
            "X-Idempotency-Key": idempotency_key
        }
        return await client.post("/api/v1/settlement/execute-micro", content=body, headers=headers)
