"""
Temporary call data store.

Acts as a fast runtime cache separated from the primary database layer.
Data is keyed by call_id and phone number, and cleaned up automatically.
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional

_CALL_CACHE: Dict[int, Dict[str, Any]] = {}
_PHONE_CACHE: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in str(phone) if ch not in " ()-")


def hydrate_call_cache(call_id: int, customer_profile: Dict[str, Any], memory_lines: List[str]) -> Dict[str, Any]:
    """Create or refresh temp cache for a call from primary DB snapshot."""
    phone_key = _normalize_phone(customer_profile.get("phone"))

    row = {
        "call_id": call_id,
        "customer_profile": dict(customer_profile),
        "memory_lines": list(memory_lines[:8]),
        "transcript": [],
        "created_at": _now(),
        "last_accessed": _now(),
        "phone_key": phone_key,
    }

    with _LOCK:
        _CALL_CACHE[call_id] = row
        if phone_key:
            _PHONE_CACHE[phone_key] = {
                "customer_profile": dict(customer_profile),
                "memory_lines": list(memory_lines[:8]),
                "updated_at": _now(),
            }

    return row


def get_call_cache(call_id: int) -> Optional[Dict[str, Any]]:
    with _LOCK:
        row = _CALL_CACHE.get(call_id)
        if row:
            row["last_accessed"] = _now()
        return row


def get_phone_cache(phone: Optional[str]) -> Optional[Dict[str, Any]]:
    phone_key = _normalize_phone(phone)
    if not phone_key:
        return None

    with _LOCK:
        row = _PHONE_CACHE.get(phone_key)
        if row:
            row["updated_at"] = _now()
        return row


def append_turn(
    call_id: int,
    role: str,
    content: str,
    intent: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> None:
    with _LOCK:
        row = _CALL_CACHE.get(call_id)
        if not row:
            return

        row["transcript"].append(
            {
                "role": role,
                "content": content,
                "intent": intent,
                "sentiment": sentiment,
                "timestamp": _now().isoformat(),
            }
        )
        row["last_accessed"] = _now()


def refresh_phone_cache_from_call(call_id: int, new_issue_line: Optional[str] = None) -> None:
    """Persist latest runtime view for same-phone future calls."""
    with _LOCK:
        row = _CALL_CACHE.get(call_id)
        if not row:
            return

        phone_key = row.get("phone_key")
        if not phone_key:
            return

        memory_lines = list(row.get("memory_lines") or [])
        if new_issue_line:
            memory_lines = [new_issue_line] + memory_lines

        _PHONE_CACHE[phone_key] = {
            "customer_profile": dict(row.get("customer_profile") or {}),
            "memory_lines": memory_lines[:8],
            "updated_at": _now(),
        }


def end_call_cache(call_id: int) -> None:
    with _LOCK:
        if call_id in _CALL_CACHE:
            del _CALL_CACHE[call_id]


def cleanup_temp_cache(max_age_minutes: int = 180) -> None:
    threshold = _now() - timedelta(minutes=max_age_minutes)

    with _LOCK:
        stale_calls = [cid for cid, row in _CALL_CACHE.items() if row.get("last_accessed", threshold) < threshold]
        for cid in stale_calls:
            del _CALL_CACHE[cid]

        stale_phones = [p for p, row in _PHONE_CACHE.items() if row.get("updated_at", threshold) < threshold]
        for p in stale_phones:
            del _PHONE_CACHE[p]
