"""Bind every number in a report to the run that produced it.

The failure mode this exists to prevent is specific and, in an industrial setting,
disqualifying: a language model asked to summarise results will round, restate and
occasionally invent figures. One altered number in a commissioning report costs more trust
than the whole report earns.

So the contract is inverted. The model is forbidden to write digits at all. It writes
placeholders — ``{{run:<run_id>.metrics.val_free_run_fit}}`` — and a renderer substitutes
the value read from the persisted run record. Two mechanisms enforce it:

* :func:`validate_draft` rejects a draft containing any bare numeral, so a model that
  ignores the instruction produces a *rejected draft*, not a wrong report.
* :func:`render_template` resolves each placeholder against real run data and records the
  binding, so every figure in the output is traceable to a run id and a field path.

The guarantee is structural rather than behavioural: it does not depend on the model
choosing to comply.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# {{run:<run_id>.<dotted.path>}} or {{chart:<artifact_id>}}
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*(run|chart)\s*:\s*([A-Za-z0-9_\-]+)(?:\.([^}\s]+))?\s*\}\}"
)

_DIGIT_RUN = re.compile(r"\d+(?:\.\d+)?")
# Ordered-list markers and heading numbers are structure, not data, so they are allowed.
# The space after the marker is optional because Chinese enumeration ("3、第三条") does not
# use one, while the Western forms ("3. ", "3) ") normally do.
_LIST_MARKER = re.compile(r"^\s{0,6}(?:#{1,6}\s*)?\d+(?:\.\d+)*[.、)]\s?")
_TABLE_ALIGNMENT = re.compile(r"^[\s|:\-]+$")


@dataclass(frozen=True)
class Binding:
    """One resolved placeholder: where the number came from and what it was."""

    placeholder: str
    kind: str
    run_id: str
    path: str
    value: str
    resolved: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "kind": self.kind,
            "run_id": self.run_id,
            "path": self.path,
            "value": self.value,
            "resolved": self.resolved,
        }


@dataclass(frozen=True)
class NumeralViolation:
    """A bare number the model wrote that is not bound to any run."""

    line: int
    column: int
    text: str
    context: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "text": self.text,
            "context": self.context,
        }


@dataclass(frozen=True)
class RenderResult:
    """Rendered report plus the provenance record behind it."""

    text: str
    bindings: tuple[Binding, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def fully_resolved(self) -> bool:
        return not self.unresolved

    def to_payload(self) -> dict[str, Any]:
        return {
            "bindings": [binding.to_payload() for binding in self.bindings],
            "unresolved": list(self.unresolved),
            "fully_resolved": self.fully_resolved,
        }


def validate_draft(draft: str) -> list[NumeralViolation]:
    """Return every numeral in the draft that is not inside a placeholder.

    A non-empty result means the draft must be regenerated. This is what makes the "the
    model cannot state a number" rule enforceable rather than aspirational.
    """

    violations: list[NumeralViolation] = []
    for line_number, line in enumerate(draft.splitlines(), start=1):
        if _TABLE_ALIGNMENT.match(line):
            continue
        spans = [match.span() for match in PLACEHOLDER_PATTERN.finditer(line)]
        marker = _LIST_MARKER.match(line)
        marker_end = marker.end() if marker else 0
        for match in _DIGIT_RUN.finditer(line):
            start, end = match.span()
            if start < marker_end:
                continue
            if any(span_start <= start and end <= span_end for span_start, span_end in spans):
                continue
            violations.append(
                NumeralViolation(
                    line=line_number,
                    column=start + 1,
                    text=match.group(0),
                    context=line.strip()[:120],
                )
            )
    return violations


def resolve_path(source: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path out of a run record, supporting list indices."""

    current: Any = source
    for part in path.split("."):
        if part == "":
            return None
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(part)
            except ValueError:
                return None
            if not -len(current) <= index < len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def render_template(
    template: str,
    *,
    runs: Mapping[str, Mapping[str, Any]],
    charts: Mapping[str, str] | None = None,
    precision: int = 4,
) -> RenderResult:
    """Substitute every placeholder with the value from its run record.

    An unresolvable placeholder is left visibly marked rather than silently blanked: a
    report that quietly drops a figure is more dangerous than one that shows it is missing.
    """

    bindings: list[Binding] = []
    unresolved: list[str] = []
    chart_map = charts or {}

    def substitute(match: re.Match[str]) -> str:
        kind, identifier, path = match.group(1), match.group(2), match.group(3) or ""
        placeholder = match.group(0)

        if kind == "chart":
            uri = chart_map.get(identifier)
            resolved = uri is not None
            rendered = uri if uri is not None else f"[未解析图表:{identifier}]"
            if not resolved:
                unresolved.append(placeholder)
            bindings.append(
                Binding(
                    placeholder=placeholder,
                    kind=kind,
                    run_id=identifier,
                    path="",
                    value=rendered,
                    resolved=resolved,
                )
            )
            return rendered

        record = runs.get(identifier)
        value = resolve_path(record, path) if record is not None else None
        resolved = value is not None
        rendered = _format(value, precision) if resolved else f"[未解析数值:{identifier}.{path}]"
        if not resolved:
            unresolved.append(placeholder)
        bindings.append(
            Binding(
                placeholder=placeholder,
                kind=kind,
                run_id=identifier,
                path=path,
                value=rendered,
                resolved=resolved,
            )
        )
        return rendered

    text = PLACEHOLDER_PATTERN.sub(substitute, template)
    return RenderResult(text=text, bindings=tuple(bindings), unresolved=tuple(unresolved))


def _format(value: Any, precision: int) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "不可用"
        if value in (float("inf"), float("-inf")):
            return "∞" if value > 0 else "-∞"
        if abs(value) >= 1e5 or (value != 0 and abs(value) < 1e-4):
            return f"{value:.{precision}e}"
        return f"{value:.{precision}f}".rstrip("0").rstrip(".") or "0"
    if isinstance(value, (list, tuple)):
        return ", ".join(_format(item, precision) for item in value)
    return str(value)


@dataclass
class ReportDraft:
    """A draft plus its validation outcome, so a caller can retry deterministically."""

    template: str
    violations: list[NumeralViolation] = field(default_factory=list)

    @property
    def acceptable(self) -> bool:
        return not self.violations
