"""Shared salary parsing from description text.

Extracts salary ranges or single values from free-text job descriptions.
Handles hourly/annual detection and conversion.
"""

from __future__ import annotations

import re

from pipeline.config import (
    SALARY_RANGE_PATTERN,
    SALARY_SINGLE_PATTERN,
    HOURLY_PATTERN,
    ANNUAL_PATTERN,
    BONUS_PATTERN,
)

# Minimum plausible hourly rate and annual salary (filters out noise like "$1", "$5")
MIN_HOURLY = 10.0
MAX_HOURLY = 250.0
MIN_ANNUAL = 20_000.0
MAX_ANNUAL = 500_000.0

# Dollar amounts near these words are not salary — skip them
_NON_SALARY_PATTERN = re.compile(
    r"(?:sign[\-\s]?on|signing|recruitment|retention|welcome|hiring)\s*bonus"
    r"|bonus\s+(?:of\s+)?\$"
    r"|relocation"
    r"|repayment|forgiveness|reimbursement|stipend|allowance"
    r"|tuition|loan|debt"
    r"|(?:up\s+to\s+)?\$[\d,]+\s*(?:k\b)?\s*(?:bonus|incentive)"
    r"|revenue|budget|(?:total\s+)?compensation\s+package"
    r"|benefits?\s+(?:up\s+to|of|worth)",
    re.IGNORECASE,
)


def _is_non_salary(text: str, match_start: int, match_end: int) -> bool:
    """Check if the dollar amount near the match is a bonus, repayment, etc."""
    window_start = max(0, match_start - 60)
    window_end = min(len(text), match_end + 60)
    context = text[window_start:window_end]
    return bool(_NON_SALARY_PATTERN.search(context))


def _is_hourly(text: str, match_start: int, match_end: int) -> bool | None:
    """Check if salary near the match is hourly.

    Returns True (hourly), False (annual), None (unknown).
    """
    # Check a window around the match
    window_start = max(0, match_start - 30)
    window_end = min(len(text), match_end + 40)
    context = text[window_start:window_end]

    if HOURLY_PATTERN.search(context):
        return True
    if ANNUAL_PATTERN.search(context):
        return False
    return None


def _classify_and_convert(value: float, is_hourly: bool | None) -> int | None:
    """Classify a raw dollar value and convert to annual cents.

    Returns annual salary in cents, or None if value seems invalid.
    """
    if value <= 0:
        return None

    # If explicitly tagged as hourly
    if is_hourly is True:
        if MIN_HOURLY <= value <= MAX_HOURLY:
            return int(value * 2080 * 100)
        return None

    # If explicitly tagged as annual
    if is_hourly is False:
        if MIN_ANNUAL <= value <= MAX_ANNUAL:
            return int(value * 100)
        return None

    # Heuristic: values under $300 are likely hourly, over $10k are annual
    if value < 300:
        if MIN_HOURLY <= value <= MAX_HOURLY:
            return int(value * 2080 * 100)
        return None
    elif value >= 10_000:
        if MIN_ANNUAL <= value <= MAX_ANNUAL:
            return int(value * 100)
        return None

    # Ambiguous range ($300-$10,000) — skip to avoid bad data
    return None


def parse_salary(text: str) -> tuple[int | None, int | None]:
    """Extract salary from text. Returns (min_cents, max_cents) as annual salary.

    Tries range pattern first ($X - $Y), then single value ($X).
    Handles hourly/annual detection and conversion.
    """
    if not text:
        return None, None

    # Try range pattern first: "$50,000 - $75,000" or "$28.00 - $42.00/hr"
    match = SALARY_RANGE_PATTERN.search(text)
    if match and not _is_non_salary(text, match.start(), match.end()):
        try:
            low = float(match.group(1).replace(",", ""))
            high = float(match.group(2).replace(",", ""))
        except (ValueError, TypeError):
            low = high = 0
        hourly = _is_hourly(text, match.start(), match.end())

        low_cents = _classify_and_convert(low, hourly)
        high_cents = _classify_and_convert(high, hourly)

        if low_cents and high_cents:
            return (min(low_cents, high_cents), max(low_cents, high_cents))

    # Try single value: "$75,000" or "$45/hr"
    for match in SALARY_SINGLE_PATTERN.finditer(text):
        if _is_non_salary(text, match.start(), match.end()):
            continue
        val1_str = match.group(1)
        if not val1_str or not val1_str.strip(","):
            continue
        try:
            val1 = float(val1_str.replace(",", ""))
        except ValueError:
            continue
        val2_str = match.group(2)

        hourly = _is_hourly(text, match.start(), match.end())

        if val2_str:
            # Has an upper bound too
            val2 = float(val2_str.replace(",", ""))
            low_cents = _classify_and_convert(val1, hourly)
            high_cents = _classify_and_convert(val2, hourly)
            if low_cents and high_cents:
                return (min(low_cents, high_cents), max(low_cents, high_cents))

        cents = _classify_and_convert(val1, hourly)
        if cents:
            # Single value — use as both min and max
            return cents, cents

    return None, None


MIN_BONUS = 500
MAX_BONUS = 100_000


def parse_bonus(text: str) -> int | None:
    """Extract sign-on bonus amount from text. Returns amount in cents, or None."""
    if not text:
        return None

    for match in BONUS_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue

        # Check for "$15k" style — look for 'k' right after the number
        span_end = match.end()
        after = text[match.start():span_end].lower()
        if "k" in after and value < 1000:
            value *= 1000

        if MIN_BONUS <= value <= MAX_BONUS:
            return int(value * 100)

    return None
