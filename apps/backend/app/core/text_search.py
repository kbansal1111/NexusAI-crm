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


def word_prefix_regex(term: str, options: str = "i") -> Dict[str, Any]:
    """Industry-standard typeahead matching, escaped like ``safe_regex``.

    The term must appear at the START of the value or of a word inside it:
    "ja" matches "Jaipur" and "New Jalpaiguri" but not "Andijan". Substring
    (contains) matching surfaces noise users don't expect and matches far
    more rows, so anchoring is both the expected UX and the faster query.
    """
    t = re.escape((term or "").strip())
    return {"$regex": f"(^|[^a-zA-Z0-9]){t}", "$options": options}
