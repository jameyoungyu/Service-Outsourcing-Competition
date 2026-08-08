"""Identifiability-driven data selection and control-relevant model validation.

This package replaces hand-weighted "data quality" heuristics with the quantity a
system-identification engineer actually cares about: how much Fisher information a
candidate data segment contributes to the ARX parameter estimate, and whether the
resulting model survives a free-run simulation instead of a flattering one-step
prediction.
"""

from algorithms.identifiability.excitation import (
    ExcitationReport,
    fisher_information,
    log_det_information,
    persistent_excitation_order,
    profile_excitation,
)
from algorithms.identifiability.regressor import (
    ArxStructure,
    RegressorMatrix,
    build_regressor,
)
from algorithms.identifiability.selection import (
    SelectedWindow,
    SelectionResult,
    WindowGrid,
    build_window_grid,
    select_informative_windows,
)
from algorithms.identifiability.validation import (
    ModelValidation,
    free_run_simulate,
    steady_state_gains,
    validate_model,
)
from algorithms.identifiability.weighted_score import (
    WindowScore,
    score_windows,
    select_by_weighted_score,
)

__all__ = [
    "ArxStructure",
    "ExcitationReport",
    "ModelValidation",
    "RegressorMatrix",
    "SelectedWindow",
    "SelectionResult",
    "WindowGrid",
    "WindowScore",
    "build_regressor",
    "build_window_grid",
    "fisher_information",
    "free_run_simulate",
    "log_det_information",
    "persistent_excitation_order",
    "profile_excitation",
    "score_windows",
    "select_by_weighted_score",
    "select_informative_windows",
    "steady_state_gains",
    "validate_model",
]
