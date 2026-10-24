"""Severity and human-review policy. Defaults can be overridden with REVIEW_SEVERITY_OVERRIDES (JSON)."""
import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("brandpr.review.policy")

DEFAULT_SEVERITY = {
    "supported:*": "low",
    "conflicting:*": "high", "conflicting:terminology": "medium",
    "outdated:*": "high", "outdated:time_sensitive": "medium", "outdated:general": "medium",
    "unsupported:*": "medium", "unsupported:comparative": "high", "unsupported:performance": "high",
    "unsupported:quantitative": "high", "unsupported:pricing": "high", "unsupported:terminology": "low",
    "uncertain:*": "medium",
}
VALID = {"low", "medium", "high"}


def _policy() -> dict[str, str]:
    policy = dict(DEFAULT_SEVERITY)
    raw = get_settings().review_severity_overrides.strip()
    if raw:
        try:
            for k, v in json.loads(raw).items():
                if v in VALID:
                    policy[str(k)] = v
        except (ValueError, AttributeError):
            logger.warning("REVIEW_SEVERITY_OVERRIDES is not a valid JSON object; defaults are used.")
    return policy


def severity_for(status: str, category: str, term_kind: str | None = None) -> str:
    policy = _policy()
    if term_kind == "casing":
        return policy.get("conflicting:terminology_casing", "low")
    return policy.get(f"{status}:{category}") or policy.get(f"{status}:*") or "medium"


def needs_human_review(status: str, category: str, severity: str, method: str) -> bool:
    if method == "ai_assisted":
        return True
    if status == "supported":
        return False
    if category == "terminology" and severity == "low":
        return False
    return severity == "high" or status in ("conflicting", "outdated", "uncertain")
