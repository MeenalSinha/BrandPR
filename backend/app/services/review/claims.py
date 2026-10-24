"""Claim extraction: find spans of submitted text that need verification.

Deterministic rules run always. An AI provider, when configured, may add claims the rules miss; its output is
validated here, and any claim whose text cannot be found verbatim in the content is discarded.
"""
import re
from dataclasses import dataclass

from app.schemas.review import ClaimCategory

PRICE_RE = re.compile(
    r"([$₹€£]\s?\d|\b\d[\d,.]*\s?(?:usd|inr|eur|gbp|dollars?|rupees?)\b|\b(?:price[sd]?|costs?|starting at|starts at|only \$)\b)", re.I
)
COMPARATIVE_RE = re.compile(
    r"\b(fastest|best|better|faster|slowest|lighter|lightest|thinnest|smallest|largest|cheapest|strongest|smartest|"
    r"unbeatable|unmatched|unrivall?ed|unparalleled|number one|no\.\s?1|leading|outperforms?|outperformed|beats?|"
    r"superior|most (?:powerful|advanced|reliable|popular|efficient)|(?:more|less) \w+ than|than (?:any|all|every|other|competing|competitors?|the (?:competition|rest)))\b|#1",
    re.I,
)
PERFORMANCE_RE = re.compile(r"\b(improv\w+|boosts?|boosted|speed\w*|throughput|performance|faster|accelerat\w+|efficien\w+)\b", re.I)
TIME_RE = re.compile(r"\b(currently|right now|available now|available today|today|this (?:week|month|year|weekend)|limited[- ]time|in stock|now available|new for \d{4}|launching)\b", re.I)
SPEC_RE = re.compile(
    r"\b(battery|display|screen|weight|weighs|memory|storage|processor|charger|charging|resolution|warranty|waterproof|"
    r"all[- ]day|long[- ]lasting|lightweight|ports?|camera|speakers?|keyboard|bluetooth|wi-?fi)\b", re.I,
)
NUMBER_RE = re.compile(r"\d")


@dataclass
class Claim:
    text: str
    start: int
    end: int
    category: ClaimCategory
    extraction_method: str = "deterministic"
    hint: str | None = None

    def overlaps(self, other: "Claim") -> bool:
        return self.start < other.end and other.start < self.end


def sentences(content: str) -> list[tuple[int, int]]:
    """(start, end) offsets of trimmed sentences / lines. content[start:end] is exactly the sentence."""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"[^\n]+", content):
        line_start, line = m.start(), m.group(0)
        pos = 0
        for part in re.finditer(r".+?(?:[.!?]+(?=\s|$)|$)", line):
            raw = part.group(0)
            if not raw.strip():
                continue
            lead = len(raw) - len(raw.lstrip())
            s = line_start + pos + part.start() + lead
            e = line_start + pos + part.start() + len(raw.rstrip())
            if e > s:
                spans.append((s, e))
    return spans


def categorize(sentence: str) -> ClaimCategory | None:
    has_number = bool(NUMBER_RE.search(sentence))
    if PRICE_RE.search(sentence) and (has_number or re.search(r"\b(price|priced|costs?)\b", sentence, re.I)):
        return "pricing"
    if COMPARATIVE_RE.search(sentence):
        return "performance" if has_number and PERFORMANCE_RE.search(sentence) else "comparative"
    if has_number and PERFORMANCE_RE.search(sentence):
        return "performance"
    if has_number:
        return "quantitative"
    if TIME_RE.search(sentence) and SPEC_RE.search(sentence):
        return "time_sensitive"
    if SPEC_RE.search(sentence) and re.search(r"\b(all[- ]day|long[- ]lasting|waterproof|lightweight|unlimited|instant)\b", sentence, re.I):
        return "specification"
    return None


def extract_deterministic(content: str) -> list[Claim]:
    claims = []
    for s, e in sentences(content):
        text = content[s:e]
        category = categorize(text)
        if category:
            claims.append(Claim(text=text, start=s, end=e, category=category))
    return claims


def locate(content: str, text: str, taken: list[Claim]) -> tuple[int, int] | None:
    """Find a model-supplied claim verbatim in the content. Prefers an occurrence not already claimed."""
    needle = text.strip()
    if not needle:
        return None
    first = None
    idx = content.find(needle)
    while idx != -1:
        span = (idx, idx + len(needle))
        if first is None:
            first = span
        if not any(c.start < span[1] and span[0] < c.end for c in taken):
            return span
        idx = content.find(needle, idx + 1)
    return first


def merge_ai_claims(content: str, deterministic: list[Claim], ai: list[tuple[str, ClaimCategory, str | None]]) -> tuple[list[Claim], list[str]]:
    """Add model-found claims that are real text and not already covered. Returns (claims, notes)."""
    merged = list(deterministic)
    notes: list[str] = []
    discarded = 0
    for text, category, reason in ai:
        span = locate(content, text, merged)
        if span is None:
            discarded += 1
            continue
        candidate = Claim(text=content[span[0]:span[1]], start=span[0], end=span[1], category=category, extraction_method="ai", hint=reason)
        if any(candidate.overlaps(c) for c in merged):
            continue
        merged.append(candidate)
    if discarded:
        notes.append(f"Discarded {discarded} model-suggested claim(s) whose text was not found in the submitted content.")
    merged.sort(key=lambda c: (c.start, c.end))
    return merged, notes
