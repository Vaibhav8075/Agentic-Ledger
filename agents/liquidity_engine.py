"""
Child Worker 3: Autonomous Liquidity & Settlement Optimization Agent
Asks the backend for a supplier-payment plan, then independently re-checks it (maker-checker):
the settlement never eats into the EMI reserve, any advance stays within the forecast floor and
the advance limit, and the decision matches an independent recomputation.
"""

import httpx
from typing import Any, Dict, Optional

import config
from agents.guardrails import check_payment_plan

class LiquidityEngineAgent:
    def __init__(self, backend_url: str = config.BACKEND_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.backend_url = backend_url
        self.transport = transport  # injectable for tests
        self.name = "LiquidityEngineWorker"

    async def simulate_cashflow(
        self,
        due_amount: float,
        cutoff_time: Optional[str] = None,
        merchant_id: str = config.DEMO_MERCHANT_ID,
        vendor_id: str = "supplier"
    ) -> Dict[str, Any]:
        """
        Plans the payment of a supplier bill against the merchant's ledger.
        Guarantees that the 05:00 AM loan EMI deduction is preserved.
        """
        url = f"{self.backend_url}/api/v1/liquidity/simulate"
        payload = {
            "merchant_id": merchant_id,
            "due_amount": due_amount,
            "cutoff_time": cutoff_time,
            "vendor_id": vendor_id
        }

        async with httpx.AsyncClient(timeout=15.0, transport=self.transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        plan = {
            "decision": data["decision"],
            "settle_now_amount": data["recommended_micro_settlement"],
            "advance_amount": data["advance_amount"],
            "unpaid_amount": data["unpaid_amount"]
        }
        violations = check_payment_plan(
            plan,
            balance=data["current_unsettled_balance"],
            due_amount=data["requested_settlement"],
            daily_loan_emi=data["daily_loan_emi"],
            evening_floor=data["evening_forecast_floor"],
            advance_limit=data["advance_limit"]
        )
        data["maker_checker_verification"] = {"passed": not violations, "violations": violations}
        return data
