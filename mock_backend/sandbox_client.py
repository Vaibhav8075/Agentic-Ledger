"""
Helpers for driving the sandbox gateway from demos, the UI and tests.
These stand in for real customers paying the merchant; they are not part of the agent system.
"""

from typing import Any, Dict, Optional

import httpx

import config


async def create_payment(amount: float, device_imei: str, mqtt_delivered: bool = False,
                         backend_url: str = config.BACKEND_URL,
                         transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    """Records a genuine payment on the mock gateway and returns its gateway record."""
    async with httpx.AsyncClient(base_url=backend_url, timeout=5.0, transport=transport) as client:
        resp = await client.post("/api/v1/sandbox/gateway/payments",
                                 json={"amount": amount, "device_imei": device_imei, "mqtt_delivered": mqtt_delivered})
        resp.raise_for_status()
        return resp.json()
