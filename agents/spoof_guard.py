"""
Child Worker 1: Soundbox Telemetry & Spoof Guard Agent
SLA: Strictly under 600ms latency.
Validates gateway hashes against MQTT QoS 1 telemetry.
"""

import time
import httpx
from typing import Any, Dict, Optional

import config

class SpoofGuardAgent:
    def __init__(self, backend_url: str = config.BACKEND_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.backend_url = backend_url
        self.transport = transport  # injectable for tests
        self.name = "SpoofGuardWorker"
        self.latency_budget_ms = 600

    async def verify_transaction(
        self,
        txn_id: str,
        device_imei: str,
        timestamp_window: int = 60000,
        claimed_amount: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes sub-600ms verification to eliminate Paytm Spoof app attacks
        while distinguishing 2G cellular MQTT latency.
        """
        start = time.perf_counter()
        url = f"{self.backend_url}/api/v1/telemetry/verify-packet"
        payload = {
            "txn_id": txn_id,
            "device_imei": device_imei,
            "timestamp_window": timestamp_window,
            "claimed_amount": claimed_amount
        }

        async with httpx.AsyncClient(timeout=2.0, transport=self.transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        elapsed_ms = int(round((time.perf_counter() - start) * 1000))
        data["agent_elapsed_ms"] = elapsed_ms
        data["sla_met"] = elapsed_ms <= self.latency_budget_ms

        return data
