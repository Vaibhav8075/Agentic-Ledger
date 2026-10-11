"""
Deterministic extraction of a supplier bill from a WhatsApp/SMS message.

This is the offline extractor and, just as importantly, the checker for any LLM extractor
plugged in through the Phinite graph: `validate_extraction` rejects an extracted amount that
does not literally appear in the source message, so a hallucinated total can never reach the
Liquidity Engine.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))
_NUMBER = r"(\d[\d,]*(?:\.\d{1,2})?)"
_CURRENCY = r"(?:₹|rs\.?|inr)"
_TOTAL = re.compile(rf"(?:grand total|total amount due|total due|amount due|total|payable|balance due)\b[^\n\d₹]*?{_CURRENCY}?\s*{_NUMBER}", re.I)
_TAGGED = re.compile(rf"{_CURRENCY}\s*{_NUMBER}", re.I)
_CUTOFF = re.compile(r"\bby\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", re.I)
_VENDOR = re.compile(r"^\s*from\s*:\s*(.+?)\s*$", re.I | re.M)
_INVOICE_NO = re.compile(r"\b(?:invoice|delivery note|bill)\s*(?:no\.?|number)?\s*[:#]?\s*#?\s*([A-Z0-9][A-Z0-9/-]{2,})", re.I)
_ITEM = re.compile(r"(?<![\w.,:#])(\d{1,4})[ \t]+([A-Za-z][A-Za-z ]{1,40}?)(?=[ \t]*(?:\+|,|\.|\n|$))")


class InvoiceParseError(ValueError):
    pass


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _amount(text: str) -> float:
    total = _TOTAL.search(text)
    if total:
        return _to_float(total.group(1))
    tagged = [_to_float(m.group(1)) for m in _TAGGED.finditer(text)]
    if tagged:
        return max(tagged)
    raise InvoiceParseError("No payable amount found; ask the merchant to confirm the bill total.")


def _cutoff(text: str, today: date) -> Optional[str]:
    match = _CUTOFF.search(text)
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return datetime.combine(today, time(hour, minute), IST).isoformat()


def _line_items(text: str) -> List[Dict[str, Any]]:
    items = []
    for m in _ITEM.finditer(text):
        before = text[max(0, m.start() - 4):m.start()].lower()
        if re.search(_CURRENCY + r"\s*$", before, re.I):
            continue  # a price, not a quantity
        items.append({"item": m.group(2).strip(), "quantity": int(m.group(1)), "amount": None})
    return items


def parse_invoice(text: str, vendor_id: str, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or datetime.now(IST).date()
    vendor = _VENDOR.search(text)
    invoice_no = _INVOICE_NO.search(text)
    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.group(1) if vendor else vendor_id,
        "invoice_number": invoice_no.group(1) if invoice_no else None,
        "due_amount": _amount(text),
        "currency": "INR",
        "cutoff_time": _cutoff(text, today),
        "line_items": _line_items(text),
    }


def validate_extraction(extracted: Dict[str, Any], source_text: str) -> List[str]:
    """Checker for any extractor (rule-based or LLM). Returns problems; empty list = accept."""
    problems = []
    amount = extracted.get("due_amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        problems.append("due_amount missing or not positive")
    else:
        found = {_to_float(n) for n in re.findall(r"\d[\d,]*(?:\.\d{1,2})?", source_text)}
        if float(amount) not in found:
            problems.append(f"due_amount {amount} does not appear in the message")
    for item in extracted.get("line_items") or []:
        if not isinstance(item.get("quantity"), int) or item["quantity"] <= 0:
            problems.append(f"bad quantity for line item {item.get('item')!r}")
    return problems
