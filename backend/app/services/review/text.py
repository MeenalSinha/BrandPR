"""Small, dependency-free text helpers shared by extraction, retrieval and matching.

Everything here is deterministic. Quantities are parsed with their unit and qualifier so that two numbers are
only compared when their units are comparable ("18 hours" is never compared with "18 percent").
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

STOPWORDS = frozenset(
    """a an and are as at be been being but by can for from has have in into is it its of on or our so than that the their
    them then there these this those to up us was we were what when which who will with you your more most also just very
    not no all any each per via under over about""".split()
)
# Words that appear in many fact names and say nothing about the subject.
GENERIC_NAME_WORDS = frozenset({"claim", "claims", "fact", "facts", "product", "name", "spec", "specification", "general", "approved", "statement"})


def norm_ws(s: str) -> str:
    return " ".join(s.split()).casefold()


# Words that mean the same subject but do not share a stem.
SYNONYMS = {"weigh": "weight", "weighs": "weight", "weighing": "weight", "cost": "price", "costs": "price", "costing": "price", "priced": "price"}


def stem(word: str) -> str:
    w = word.casefold()
    if w in SYNONYMS:
        w = SYNONYMS[w]
    for suffix in ("ements", "ement", "ments", "ment", "ings", "ing", "ed", "es", "s", "ly"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[: -len(suffix)]
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def tokens(text: str, *, drop_generic: bool = False) -> set[str]:
    out = set()
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text):
        w = raw.casefold().strip("'-")
        if len(w) < 3 and not w.isdigit():
            continue
        if w in STOPWORDS:
            continue
        s = stem(w)
        if drop_generic and s in GENERIC_NAME_WORDS:
            continue
        out.add(s)
    return out


# ------------------------------------------------------------------ units and quantities
UNIT_ALIASES = {
    "%": "percent", "percent": "percent", "per cent": "percent",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour", "h": "hour",
    "minute": "minute", "minutes": "minute", "min": "minute", "mins": "minute",
    "day": "day", "days": "day", "year": "year", "years": "year", "yr": "year", "yrs": "year", "month": "month", "months": "month",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "g": "g", "lb": "lb", "lbs": "lb",
    "gb": "GB", "tb": "TB", "mb": "MB", "inch": "inch", "inches": "inch", '"': "inch", "w": "W", "watt": "W", "watts": "W",
    "usd": "USD", "$": "USD", "dollar": "USD", "dollars": "USD", "inr": "INR", "₹": "INR", "rupee": "INR", "rupees": "INR",
    "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP", "x": "x", "fps": "fps", "hz": "Hz", "ghz": "GHz", "mm": "mm", "cm": "cm",
    "nits": "nits",
}
# unit -> (dimension, factor to the dimension's base unit)
DIMENSIONS = {
    "hour": ("time", Decimal(60)), "minute": ("time", Decimal(1)),
    "year": ("long_time", Decimal(12)), "month": ("long_time", Decimal(1)),
    "kg": ("mass", Decimal(1000)), "g": ("mass", Decimal(1)),
}

QUALIFIER_WORDS = {
    "up to": "up_to", "as much as": "up_to", "at most": "up_to", "maximum of": "up_to", "max": "up_to",
    "at least": "at_least", "minimum of": "at_least", "over": "at_least", "more than": "at_least", "exceeding": "at_least",
    "under": "at_most", "less than": "at_most", "below": "at_most", "fewer than": "at_most",
    "around": "approx", "about": "approx", "approximately": "approx", "roughly": "approx", "nearly": "approx", "almost": "approx",
    "from": "from", "starting at": "from", "starts at": "from", "starting from": "from",
}
ABSOLUTE_WORDS = re.compile(r"\b(always|guaranteed|guarantees?|every time|constant(?:ly)?|all\s+\d|consistently|never (?:less|below))\b", re.I)

_QUAL = "|".join(sorted((re.escape(k) for k in QUALIFIER_WORDS), key=len, reverse=True))
_UNITS = "|".join(sorted((re.escape(k) for k in UNIT_ALIASES if k not in ("$", "₹", "€", "£", "%", '"')), key=len, reverse=True))
QUANTITY_RE = re.compile(
    rf"(?P<qual>\b(?:{_QUAL})\s+)?(?P<cur>[$₹€£])?\s?(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    rf"(?P<unit>\s?%|\s?\"|[\s-]*(?:{_UNITS})\b)?",
    re.I,
)


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str | None  # canonical unit, e.g. "hour", "percent", "USD"
    qualifier: str  # exact | up_to | at_least | at_most | approx | from | absolute
    start: int
    end: int
    raw: str


def canonical_unit(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip(" -").casefold()
    return UNIT_ALIASES.get(key, raw.strip() or None)


def parse_quantities(text: str) -> list[Quantity]:
    found: list[Quantity] = []
    for m in QUANTITY_RE.finditer(text):
        try:
            value = Decimal(m.group("num").replace(",", ""))
        except InvalidOperation:
            continue
        unit = canonical_unit(m.group("unit")) if m.group("unit") else None
        if unit is None and m.group("cur"):
            unit = canonical_unit(m.group("cur"))
        qual_raw = (m.group("qual") or "").strip().casefold()
        qualifier = QUALIFIER_WORDS.get(qual_raw, "exact")
        # A bare year or a list marker is not a quantity.
        if unit is None and value == value.to_integral_value() and 1900 <= value <= 2100 and not m.group("cur"):
            continue
        before = text[max(0, m.start() - 24): m.start()]
        if qualifier == "exact" and ABSOLUTE_WORDS.search(before + " " + m.group(0)):
            qualifier = "absolute"
        found.append(Quantity(value, unit, qualifier, m.start(), m.end(), m.group(0).strip()))
    return found


def to_base(q: Quantity) -> tuple[str | None, Decimal]:
    """(dimension-or-unit, value in the dimension's base unit) so comparable quantities can be compared."""
    if q.unit in DIMENSIONS:
        dim, factor = DIMENSIONS[q.unit]
        return dim, q.value * factor
    return q.unit, q.value


def comparable(a: Quantity, b: Quantity) -> bool:
    return to_base(a)[0] == to_base(b)[0]


def fact_quantity(value: str, unit: str | None) -> Quantity | None:
    """The numeric value an approved fact states, or None when the fact is not numeric."""
    stripped = value.strip()
    if unit and re.fullmatch(r"\d[\d,]*(?:\.\d+)?", stripped):
        return Quantity(Decimal(stripped.replace(",", "")), canonical_unit(unit), "exact", 0, len(stripped), stripped)
    qs = parse_quantities(stripped)
    if not qs:
        return None
    q = qs[0]
    if q.unit is None and unit:
        q = Quantity(q.value, canonical_unit(unit), q.qualifier, q.start, q.end, q.raw)
    return q
