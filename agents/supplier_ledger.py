"""
Child Worker 2: Supplier Ledger & Invoice Parsing Agent
Parses unstructured WhatsApp/SMS distributor bills (e.g. Amul, Britannia)
and extracts structured debt obligations into JSON.
"""

import httpx
from typing import Any, Dict, Optional

import config
from agents.guardrails import sanitize_pii
from agents.invoice_parser import validate_extraction

class SupplierLedgerAgent:
    def __init__(self, backend_url: str = config.BACKEND_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.backend_url = backend_url
        self.transport = transport  # injectable for tests
        self.name = "SupplierLedgerWorker"

    async def parse_invoice(self, raw_message: str, vendor_id: str = "amul_distributor_vpa") -> Dict[str, Any]:
        """
        Redacts PII before the message leaves the agent, extracts the obligation, then checks
        that the extracted amount really appears in the message before anyone can pay it.
        """
        sanitized_text, had_pii = sanitize_pii(raw_message)

        url = f"{self.backend_url}/api/v1/supplier-bills/parse"
        payload = {
            "raw_message": sanitized_text,
            "vendor_id": vendor_id
        }

        async with httpx.AsyncClient(timeout=5.0, transport=self.transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        problems = validate_extraction(data, sanitized_text)
        if problems:
            raise ValueError("Rejected bill extraction: " + "; ".join(problems))
        data["pii_sanitized_at_ingress"] = had_pii
        data["sanitized_text"] = sanitized_text
        return data
