"""Helpers for building safe MongoDB text-search clauses from user input."""
import re
from typing import Any, Dict


def safe_regex(term: str, options: str = "i") -> Dict[str, Any]:
    """Build a Mongo ``$regex`` clause from UNTRUSTED user input.

    Escapes regex metacharacters so a search like ``C++``, ``Congo (Brazzaville``
    or ``[a`` can't (a) crash the query — an invalid regex makes MongoDB raise and
    the endpoint return 500 — or (b) trigger catastrophic backtracking (ReDoS).
    The user's text is matched literally, case-insensitively by default.
    """
    return {"$regex": re.escape((term or "").strip()), "$options": options}
