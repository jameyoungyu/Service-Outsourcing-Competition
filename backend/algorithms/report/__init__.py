"""Provenance-bound report rendering: the model writes prose, the database writes numbers."""

from algorithms.report.provenance import (
    PLACEHOLDER_PATTERN,
    Binding,
    NumeralViolation,
    RenderResult,
    render_template,
    resolve_path,
    validate_draft,
)

__all__ = [
    "PLACEHOLDER_PATTERN",
    "Binding",
    "NumeralViolation",
    "RenderResult",
    "render_template",
    "resolve_path",
    "validate_draft",
]
