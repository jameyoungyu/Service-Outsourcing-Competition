"""Lineage-as-cache: content-addressed memoisation of pipeline stages.

The data-version design already requires every derived artifact to record its parent, the
tool that produced it, that tool's version, the parameters and a checksum. That tuple is
exactly a content-addressed key, so the lineage metadata the project keeps for auditing
doubles as a cache index — no second caching system is needed.

This matters because of how the closed loop searches. Consecutive Optuna trials usually
change only the tail of the pipeline (model orders, ridge alpha) while the head (gating
thresholds, window size, selection budget) stays put. Re-running the selection for each of
those trials is pure waste: same inputs, same parameters, same tool version, therefore the
same result by construction.

Keys are computed from a canonical JSON encoding so that ``{"a": 1, "b": 2}`` and
``{"b": 2, "a": 1}`` hash identically, and floats are rendered at fixed precision so that
values that differ only in float noise do not miss the cache.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

ResultT = TypeVar("ResultT")

# Floats are rendered at this precision before hashing. Optuna suggests values with far
# more digits than any of these parameters can act on, and two thresholds that differ in
# the twelfth decimal produce identical pipelines.
FLOAT_PRECISION = 9


def canonical_json(payload: Any) -> str:
    """Render a payload so that equal content always produces an equal string."""

    return json.dumps(
        _normalise(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalise(value: Any) -> Any:
    if isinstance(value, float):
        if value != value:  # NaN
            return "NaN"
        if value in (float("inf"), float("-inf")):
            return str(value)
        return round(value, FLOAT_PRECISION)
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def stage_key(
    *,
    parent_key: str,
    tool_name: str,
    tool_version: str,
    parameters: Mapping[str, Any],
    code_version: str = "",
) -> str:
    """Return the content-addressed key of one pipeline stage's output."""

    digest = hashlib.sha256()
    digest.update(
        canonical_json(
            {
                "parent": parent_key,
                "tool": tool_name,
                "tool_version": tool_version,
                "code_version": code_version,
                "params": parameters,
            }
        ).encode("utf-8")
    )
    return digest.hexdigest()


@dataclass
class LineageCache:
    """In-process memo table keyed by stage key, with hit/miss accounting.

    Deliberately bounded and in-process: a study is a single request's worth of work, and
    a persistent cache would have to invalidate on code changes, which the key already
    encodes but the storage lifetime would not.
    """

    max_entries: int = 512
    hits: int = 0
    misses: int = 0
    _entries: dict[str, Any] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def get_or_compute(self, key: str, compute: Callable[[], ResultT]) -> tuple[ResultT, bool]:
        """Return ``(value, was_cached)``, computing only on a miss."""

        if key in self._entries:
            self.hits += 1
            return self._entries[key], True
        self.misses += 1
        value = compute()
        self._store(key, value)
        return value, False

    def _store(self, key: str, value: Any) -> None:
        if key in self._entries:
            self._order.remove(key)
        elif len(self._order) >= self.max_entries:
            evicted = self._order.pop(0)
            self._entries.pop(evicted, None)
        self._entries[key] = value
        self._order.append(key)

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    def statistics(self) -> dict[str, float | int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "lookups": self.lookups,
            "hit_rate": self.hit_rate,
            "entries": len(self._entries),
        }

    def clear(self) -> None:
        self._entries.clear()
        self._order.clear()
        self.hits = 0
        self.misses = 0
