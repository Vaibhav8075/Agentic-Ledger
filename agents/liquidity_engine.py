"""
Child Worker 3: Autonomous Liquidity & Settlement Optimization Agent
Enforces deterministic balance calculation and Maker-Checker guardrail:
(Requested_Settlement + Daily_Loan_EMI) <= Current_Unsettled_Balance
"""

import httpx
from typing import Any, Dict, Optional

import config
from agents.guardrails import assert_liquidity_guardrail

class LiquidityEngineAgent:
    def __init__(self, backend_url: str = config.BACKEND_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.backend_url = backend_url
        self.transport = transport  # injectable for tests
        self.name = "LiquidityEngineWorker"

    async def simulate_cashflow(
        self,
        current_unsettled_balance: float,
        due_amount: float,
        cutoff_time: str,
        merchant_id: str = config.DEMO_MERCHANT_ID
    ) -> Dict[str, Any]:
        """
        Executes deterministic liquidity projection via the mock backend.
        Guarantees that 05:00 AM loan EMI deduction is preserved.
        """
        url = f"{self.backend_url}/api/v1/liquidity/simulate"
        payload = {
            "current_unsettled_balance": current_unsettled_balance,
            "due_amount": due_amount,
            "cutoff_time": cutoff_time,
            "merchant_id": merchant_id
        }

        async with httpx.AsyncClient(timeout=15.0, transport=self.transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Run independent Python Maker-Checker verification
        guardrail_result = assert_liquidity_guardrail(
            current_unsettled_balance=current_unsettled_balance,
            requested_settlement=due_amount,
            daily_loan_emi=data.get("daily_loan_emi", 3000.00)
        )
        data["maker_checker_verification"] = guardrail_result

        return data
