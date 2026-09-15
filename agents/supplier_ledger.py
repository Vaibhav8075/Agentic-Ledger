"""
Child Worker 2: Supplier Ledger & Invoice Parsing Agent
Parses unstructured WhatsApp/SMS distributor bills (e.g. Amul, Britannia)
and extracts structured debt obligations into JSON.
"""

import httpx
from typing import Any, Dict
from agents.guardrails import sanitize_pii

class SupplierLedgerAgent:
    def __init__(self, backend_url: str = "http://127.0.0.1:8000"):
        self.backend_url = backend_url
        self.name = "SupplierLedgerWorker"

    async def parse_invoice(self, raw_message: str, vendor_id: str = "amul_distributor_vpa") -> Dict[str, Any]:
        """
        Extracts structured obligation while redacting PII before processing.
        """
        sanitized_text, had_pii = sanitize_pii(raw_message)

        url = f"{self.backend_url}/api/v1/supplier-bills/parse"
        payload = {
            "raw_message": sanitized_text,
            "vendor_id": vendor_id
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        data["pii_sanitized_at_ingress"] = had_pii
        return data
