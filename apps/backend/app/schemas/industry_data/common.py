"""
Shared coercion helpers for industry_data schemas.

Frontend forms render multi-value fields (diagnosis codes, submitted
documents, certifications, ...) as plain text inputs, so the API receives a
comma-separated string where the schema declares List[str]. Rejecting that
with a 422 breaks every non-travel create/edit form — coerce instead.
"""
from typing import Any, List


def coerce_str_list(value: Any) -> List[str]:
    """Coerce a comma-separated string (or scalar) into a list of strings.

    Used as a `mode="before"` field validator on List[str] fields so both
    `["a", "b"]` and `"a, b"` validate to `["a", "b"]`. Empty entries are
    dropped; None becomes [].
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]
