import json
import pathlib
from functools import lru_cache

from app.models.policy import PolicyTerms

_DEFAULT_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "data" / "policy_terms.json"


@lru_cache(maxsize=1)
def load_policy(path: str | None = None) -> PolicyTerms:
    p = pathlib.Path(path) if path else _DEFAULT_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return PolicyTerms(**data)
