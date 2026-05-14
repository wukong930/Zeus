from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.schemas.common import IndustryDataCreate

MAX_TEXT_VALUES_PER_METRIC = 3
VALUE_WINDOW_CHARS = 96
RUBBER_TEXT_SOURCE_PREFIX = "rubber_text"
_CNY_VALUE_PATTERN = re.compile(
    r"(?<![\d.])(\d{2,6}(?:\.\d+)?)\s*(?:cny/t|rmb/t|yuan/t|yuan\s+per\s+tonne|"
    r"yuan\s+per\s+ton|yuan|cny|rmb|元\s*/\s*吨|元/吨|元每吨|元)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RubberTextMetricSpec:
    key: str
    data_type: str
    unit: str
    symbols: tuple[str, ...]
    keywords: tuple[str, ...]
    confidence: float
    blocked_keywords: tuple[str, ...] = ()


RUBBER_TEXT_METRICS: tuple[RubberTextMetricSpec, ...] = (
    RubberTextMetricSpec(
        key="qingdao_bonded_spot",
        data_type="rubber_qingdao_spot_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=(
            "qingdao bonded spot price",
            "qingdao bonded rubber spot",
            "qingdao natural rubber spot",
            "青岛保税区现货",
            "青岛天然橡胶现货",
            "青岛现货报价",
            "保税区现货报价",
        ),
        blocked_keywords=("premium", "basis", "升水", "基差"),
        confidence=0.72,
    ),
    RubberTextMetricSpec(
        key="qingdao_bonded_premium",
        data_type="rubber_qingdao_premium_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=(
            "qingdao bonded premium",
            "qingdao spot premium",
            "bonded spot premium",
            "青岛保税区升水",
            "青岛升水",
            "青岛保税区基差",
            "保税区升水",
            "保税区基差",
        ),
        confidence=0.74,
    ),
    RubberTextMetricSpec(
        key="hainan_latex",
        data_type="rubber_hainan_latex_cny_t",
        unit="CNY/t",
        symbols=("RU",),
        keywords=("hainan field latex", "hainan latex", "海南胶水", "海南天胶", "海南天然橡胶"),
        confidence=0.7,
    ),
    RubberTextMetricSpec(
        key="hainan_collection",
        data_type="rubber_hainan_collect_cny_t",
        unit="CNY/t",
        symbols=("RU",),
        keywords=("hainan collection", "hainan collecting", "海南收胶", "海南收购", "海南收胶成本"),
        confidence=0.72,
    ),
    RubberTextMetricSpec(
        key="yunnan_latex",
        data_type="rubber_yunnan_latex_cny_t",
        unit="CNY/t",
        symbols=("RU",),
        keywords=("yunnan field latex", "yunnan latex", "云南胶水", "云南天胶", "云南天然橡胶"),
        confidence=0.7,
    ),
    RubberTextMetricSpec(
        key="yunnan_collection",
        data_type="rubber_yunnan_collect_cny_t",
        unit="CNY/t",
        symbols=("RU",),
        keywords=("yunnan collection", "yunnan collecting", "云南收胶", "云南收购", "云南收胶成本"),
        confidence=0.72,
    ),
    RubberTextMetricSpec(
        key="thailand_export",
        data_type="rubber_thai_export_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=("thailand export", "thai export", "thailand latex", "thai latex", "泰国出口", "泰国胶水", "泰国天胶"),
        confidence=0.68,
    ),
    RubberTextMetricSpec(
        key="indonesia_export",
        data_type="rubber_indo_export_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=("indonesia export", "indonesian export", "indonesia rubber", "印尼出口", "印尼天胶", "印尼橡胶"),
        confidence=0.66,
    ),
    RubberTextMetricSpec(
        key="malaysia_export",
        data_type="rubber_mys_export_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=("malaysia export", "malaysian export", "malaysia rubber", "马来西亚出口", "马来西亚天胶", "马来橡胶"),
        confidence=0.66,
    ),
    RubberTextMetricSpec(
        key="sea_freight",
        data_type="rubber_sea_freight_cny_t",
        unit="CNY/t",
        symbols=("NR", "RU"),
        keywords=("sea freight", "ocean freight", "import freight", "rubber freight", "海运费", "进口运费", "橡胶运费"),
        confidence=0.62,
    ),
)


def extract_rubber_text_industry_rows(
    *,
    title: str,
    content: str | None,
    source: str,
    published_at: datetime | None = None,
    min_confidence: float = 0.0,
) -> list[IndustryDataCreate]:
    timestamp = _ensure_timestamp(published_at)
    text = "\n".join(part for part in (title, content or "") if part)
    if not text.strip():
        return []

    rows: list[IndustryDataCreate] = []
    seen: set[tuple[str, str, float]] = set()
    source_id = _source_id(source)
    document_id = _document_id(source=source, title=title, published_at=timestamp)

    for spec in RUBBER_TEXT_METRICS:
        if spec.confidence < min_confidence:
            continue
        for value in _values_for_metric(text, spec):
            for symbol in spec.symbols:
                key = (symbol, spec.data_type, value)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    IndustryDataCreate(
                        source_key=(
                            f"{RUBBER_TEXT_SOURCE_PREFIX}:{document_id}:"
                            f"{symbol}:{spec.data_type}:{_value_token(value)}"
                        ),
                        symbol=symbol,
                        data_type=spec.data_type,
                        value=value,
                        unit=spec.unit,
                        source=source_id,
                        timestamp=timestamp,
                    )
                )

    return rows


def _values_for_metric(text: str, spec: RubberTextMetricSpec) -> list[float]:
    lowered = text.lower()
    values: list[float] = []
    for keyword in spec.keywords:
        keyword_lower = keyword.lower()
        start = 0
        while True:
            index = lowered.find(keyword_lower, start)
            if index < 0:
                break
            sentence_start, sentence_end = _sentence_bounds(text, index)
            window_start = max(sentence_start, index - VALUE_WINDOW_CHARS)
            window_end = min(sentence_end, index + len(keyword) + VALUE_WINDOW_CHARS)
            window = text[window_start:window_end]
            if _blocked(window, spec.blocked_keywords):
                start = index + len(keyword)
                continue
            value = _closest_value(window, keyword_position=index - window_start)
            if value is not None and value not in values:
                values.append(value)
            if len(values) >= MAX_TEXT_VALUES_PER_METRIC:
                return values
            start = index + len(keyword)
    return values


def _sentence_bounds(text: str, index: int) -> tuple[int, int]:
    separators = "\n。；;.!?"
    start = max(text.rfind(separator, 0, index) for separator in separators) + 1
    ends = [text.find(separator, index) for separator in separators]
    positive_ends = [end for end in ends if end >= 0]
    end = min(positive_ends) if positive_ends else len(text)
    return start, end


def _closest_value(window: str, *, keyword_position: int) -> float | None:
    following = []
    candidates = []
    for match in _CNY_VALUE_PATTERN.finditer(window):
        value = float(match.group(1))
        if value <= 0:
            continue
        if match.start() >= keyword_position:
            following.append((match.start() - keyword_position, value))
        distance = min(abs(match.start() - keyword_position), abs(match.end() - keyword_position))
        candidates.append((distance, value))
    if following:
        return sorted(following, key=lambda item: item[0])[0][1]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _blocked(window: str, blocked_keywords: Iterable[str]) -> bool:
    lowered = window.lower()
    return any(keyword.lower() in lowered for keyword in blocked_keywords)


def _ensure_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _source_id(source: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", source.strip())[:36] or "unknown"
    return f"{RUBBER_TEXT_SOURCE_PREFIX}:{safe}"[:50]


def _document_id(*, source: str, title: str, published_at: datetime) -> str:
    payload = f"{source}|{published_at.isoformat()}|{title}".encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def _value_token(value: float) -> str:
    return str(value).replace(".", "_")[:16]
