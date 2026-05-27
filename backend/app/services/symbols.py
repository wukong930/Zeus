from __future__ import annotations

import re
from typing import Any


def normalize_root_symbol(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = re.sub(r"\d+", "", raw).upper()
    return normalized or None
