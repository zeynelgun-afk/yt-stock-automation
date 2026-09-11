"""Conservative checks for figures displayed prominently in published videos."""
import math
import re
from decimal import Decimal, InvalidOperation

_FIGURE = re.compile(r"^([+$-]*)(\d[\d,]*(?:\.\d+)?)([KMBkmb]?)(%?)$")
_SCALE = {"": Decimal(1), "K": Decimal(1000), "M": Decimal(1000000), "B": Decimal(1000000000)}


def validate_hero_number(hero: str, story: dict, script: str, change_pct: str) -> str:
    """Match the complete figure and unit to structured source facts.

    The generated script/headline are deliberately NOT evidence. Rounding is
    allowed only to the displayed precision, never by matching leading digits.
    This checks the number, not every narrative claim or its actor attribution.
    """
    match = _FIGURE.fullmatch(hero.strip())
    if not match:
        return ""
    prefix, digits, suffix, percent = match.groups()
    if ("$" in prefix and percent) or (percent and suffix):
        return ""
    scale = _SCALE[suffix.upper()]
    number = Decimal(digits.replace(",", "")) * scale
    if "-" in prefix:
        number = -number
    decimals = len(digits.partition(".")[2])
    tolerance = scale * Decimal(10) ** -decimals / 2
    unit = "percent" if percent else ("money" if "$" in prefix else "number")

    def values(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from values(v, k.lower())
        elif isinstance(node, list):
            for v in node:
                yield from values(v, key)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if not math.isfinite(node):
                return
            kind = ("percent" if any(s in key for s in ("pct", "percent", "surprise")) else
                    "money" if any(s in key for s in ("usd", "price", "revenue", "amount", "value", "eps")) else "number")
            yield Decimal(str(node)), kind
        elif isinstance(node, str) and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", node):
            # Numeric API fields may be strings; do not mine dates or news prose.
            yield from values(float(node), key)

    candidates = list(values(story.get("facts", {})))
    try:
        candidates.append((Decimal(change_pct), "percent"))
    except InvalidOperation:
        pass
    for value, kind in candidates:
        # An explicit plus/minus must preserve direction; unsigned figures may
        # name the magnitude of a drop, with direction in the label.
        compared = value if "+" in prefix or "-" in prefix else abs(value)
        if kind == unit and compared.is_finite() and abs(compared - number) <= tolerance:
            return hero.strip()
    return ""
