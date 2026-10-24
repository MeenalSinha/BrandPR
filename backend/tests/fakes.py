"""Controlled stand-in for a model provider. Used ONLY in tests of the pipeline's handling of model output.
It is never a substitute for testing the real provider integration (see test_provider_adapter.py)."""
import json
import re


class FakeProvider:
    name = "fake"
    model = "fake-model-1"

    def __init__(self, extract='{"claims":[]}', interpret=None):
        self.extract_response = extract
        self.interpret_response = interpret if interpret is not None else '{"assessments":[]}'
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        response = self.extract_response if system.startswith("You identify") else self.interpret_response
        if callable(response):
            response = response(user)
        if isinstance(response, Exception):
            raise response
        return response


def claims_json(*texts: str, category: str = "general") -> str:
    return json.dumps({"claims": [{"text": t, "category": category, "reason": "test"} for t in texts]})


def assessments_for(relation: str, which: int = 0):
    """Interpret-response callable that answers about the Nth fact id the backend listed in the prompt."""

    def respond(user: str) -> str:
        ids = re.findall(r"fact_id=([0-9a-f-]{36})", user)
        return json.dumps({"assessments": [{"fact_id": ids[which], "relation": relation, "reason": "test reason"}]})

    return respond
