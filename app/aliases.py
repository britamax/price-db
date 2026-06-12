"""Alias expansion service.

Loads alias map from DB at startup, applies variant→canonical substitution
to text before embedding/indexing. Whole-word boundary matching to avoid
mid-word collisions (e.g. "kbl" shouldn't match "kabel").

Auto-reload via reload_aliases() — call after admin edits the alias table.
"""

from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional, Tuple

import psycopg

# Module-level cache. Two passes: longer phrases first, then single tokens.
# Confidence < threshold are skipped (set per-call).
_cache_lock = threading.Lock()
_aliases_cache: Optional[List[Tuple[str, str, float, re.Pattern]]] = None
_aliases_by_kind: Dict[str, Dict[str, str]] = {}


def _compile_alias(variant: str) -> re.Pattern:
    """Compile a regex that matches the variant as a whole-word phrase, case-insensitive."""
    # Escape special chars but allow flexible whitespace between tokens of the variant
    parts = [re.escape(p) for p in variant.split()]
    pattern = r"\b" + r"\s+".join(parts) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def reload_aliases(conn) -> int:
    """Reload alias cache from DB. Returns total entries loaded."""
    global _aliases_cache, _aliases_by_kind
    with conn.cursor() as cur:
        cur.execute(
            "SELECT variant, canonical, kind, confidence FROM alias ORDER BY length(variant) DESC, variant"
        )
        rows = cur.fetchall()

    compiled: List[Tuple[str, str, float, re.Pattern]] = []
    by_kind: Dict[str, Dict[str, str]] = {"material": {}, "unit": {}, "brand": {}}
    for r in rows:
        # Support both tuple-row and dict-row cursors
        if isinstance(r, dict):
            variant, canonical, kind, confidence = r["variant"], r["canonical"], r["kind"], r["confidence"]
        else:
            variant, canonical, kind, confidence = r[0], r[1], r[2], r[3]
        if not variant or not canonical:
            continue
        try:
            compiled.append((variant.lower(), canonical.lower(), float(confidence), _compile_alias(variant)))
        except re.error:
            continue
        by_kind.setdefault(kind, {})[variant.lower()] = canonical.lower()

    with _cache_lock:
        _aliases_cache = compiled
        _aliases_by_kind = by_kind
    return len(compiled)


def _ensure_loaded(conn) -> None:
    if _aliases_cache is None:
        reload_aliases(conn)


def expand_aliases(text: str, conn=None, min_confidence: float = 0.5) -> str:
    """Apply alias expansion to a text. Returns text with all alias variants replaced.

    Variants are applied longest-first to avoid partial collisions.
    Caller must pass conn on first call so the cache can warm.
    """
    if not text:
        return text
    if _aliases_cache is None:
        if conn is None:
            return text  # Can't lazy-load without a connection
        reload_aliases(conn)
    with _cache_lock:
        aliases = list(_aliases_cache or [])

    result = text
    for variant, canonical, confidence, pattern in aliases:
        if confidence < min_confidence:
            continue
        result = pattern.sub(canonical, result)
    # Collapse whitespace introduced by substitutions
    result = re.sub(r"\s+", " ", result).strip()
    return result


def get_canonical(variant: str, kind: str = "material") -> Optional[str]:
    """Direct lookup: get canonical for a known variant in a specific kind."""
    return _aliases_by_kind.get(kind, {}).get(variant.lower())


def cached_size() -> int:
    return len(_aliases_cache or [])
