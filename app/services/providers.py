import random
import uuid

class MockProvider:
    def __init__(self, name, flaky=False, seed=42):
        self.name, self.flaky = name, flaky
        self.rng = random.Random(seed)

    def initiate_call(self, answer_rate):
        if self.flaky and self.rng.random() < 0.12:
            return {"timeout": True}
        return {"timeout": False, "provider_call_id": f"{self.name}-{uuid.uuid4().hex[:12]}",
                "outcome": "ANSWERED" if self.rng.random() < answer_rate else self.rng.choice(["NO_ANSWER", "BUSY", "FAILED"]),
                "duplicate_event": self.flaky and self.rng.random() < 0.2,
                "out_of_order": self.flaky and self.rng.random() < 0.15}

def provider_for(name):
    if name == "A": return MockProvider("A", False)
    if name == "B": return MockProvider("B", True)
    raise ValueError("provider must be A or B")
