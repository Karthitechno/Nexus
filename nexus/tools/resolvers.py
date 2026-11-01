"""Deterministic entity resolvers for dates, amounts, currencies, and emails."""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any


def resolve_date_window(text: str, now: Optional[datetime] = None) -> Optional[Tuple[str, str]]:
    """Deterministically resolve temporal phrases into ISO 8601 UTC date windows."""
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

    lower = text.lower()

    # 1. "last month"
    if "last month" in lower:
        first_of_curr = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_of_last = first_of_curr - timedelta(seconds=1)
        start_of_last = end_of_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            start_of_last.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_of_last.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # 2. "last 7 days"
    if "last 7 days" in lower or "past 7 days" in lower:
        start_dt = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        return (
            start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # 3. "last 30 days"
    if "last 30 days" in lower or "past 30 days" in lower:
        start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        return (
            start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # 4. Explicit dates: "YYYY-MM-DD to YYYY-MM-DD" or "between YYYY-MM-DD and YYYY-MM-DD"
    explicit_match = re.search(
        r"(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}Z)?\s+(?:to|and|-)\s+(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}Z)?",
        text,
        re.IGNORECASE,
    )
    if explicit_match:
        d1, d2 = explicit_match.group(1), explicit_match.group(2)
        return f"{d1}T00:00:00Z", f"{d2}T23:59:59Z"

    return None


def resolve_amount(text: str) -> Optional[float]:
    """Deterministically extract currency amounts."""
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", text)
    if match:
        return float(match.group(1))

    match_suffix = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:usd|dollars|bucks)", text, re.IGNORECASE)
    if match_suffix:
        return float(match_suffix.group(1))

    match_for = re.search(r"(?:for|amount of|total of)\s+([0-9]+(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
    if match_for:
        return float(match_for.group(1))

    return None


def resolve_email(text: str) -> Optional[str]:
    """Deterministically extract recipient email address."""
    match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if match:
        return match.group(1).lower()
    return None


def resolve_currency(text: str) -> str:
    """Deterministically extract currency code, defaulting to USD."""
    upper = text.upper()
    for curr in ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]:
        if re.search(rf"\b{curr}\b", upper):
            return curr
    return "USD"


def resolve_entity_id(text: str, entity_prefix: str) -> Optional[str]:
    """Extract IDs like INV2-1234, ORD-9988, AUTH-5544, DISP-1010."""
    patterns = [
        rf"\b({entity_prefix}[0-9A-Za-z]*-[A-Za-z0-9_-]+)\b",
        r"\b([A-Z0-9]{3,}-[A-Z0-9-]{3,})\b",
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            val = match.group(1).upper()
            if "-" in val:
                return val
    return None
