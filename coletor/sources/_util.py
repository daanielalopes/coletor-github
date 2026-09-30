"""Helpers de parsing compartilhados entre as fontes (crawler de HTML)."""

import re
from typing import Optional


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def parse_compact_number(text: Optional[str]) -> Optional[int]:
    """
    Converte números "compactos" exibidos no HTML em inteiros.
    Exemplos: '1.2k' -> 1200, '3.4m' -> 3400000, '512' -> 512, '12,345' -> 12345.
    """
    if not text:
        return None
    t = text.strip().lower().replace(",", "").replace("\u00a0", "")
    m = re.match(r"^([\d.]+)\s*([km]?)$", t)
    if not m:
        digits = re.sub(r"[^\d]", "", t)
        return int(digits) if digits else None
    num = float(m.group(1))
    suffix = m.group(2)
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    return int(round(num))
