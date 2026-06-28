from __future__ import annotations

import re
from typing import Any

# Trailing digits encode the contract month (RB2505 -> RB, RB0 -> RB, I0 -> I),
# so the root symbol is the value with its trailing numeric suffix removed. This
# MUST match the write-side root extraction in
# services/data_sources/akshare_futures.py `_base_symbol`, which also uses
# `\d+$`. The previous `\d+` (strip *all* digits) diverged from the write side
# and corrupted any symbol with non-trailing digits (e.g. 6E -> E), so a query
# could normalize to a different root than the one stored.
_TRAILING_CONTRACT_MONTH = re.compile(r"\d+$")


def normalize_root_symbol(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = _TRAILING_CONTRACT_MONTH.sub("", raw).upper()
    return normalized or None
