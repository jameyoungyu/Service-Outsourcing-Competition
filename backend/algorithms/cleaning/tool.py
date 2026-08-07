"""Shared contract for deterministic preprocessing algorithms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

ContextT = TypeVar("ContextT")
ParametersT = TypeVar("ParametersT")
ResultT = TypeVar("ResultT")


class AlgorithmTool(ABC, Generic[ContextT, ParametersT, ResultT]):
    """A small explicit interface for auditable, side-effect-free algorithms.

    Services own persistence and artifact writes. Tools only transform the supplied
    context, which makes the same calculation straightforward to unit-test.
    """

    name: str
    input_schema: type[object]
    output_schema: type[object]

    @abstractmethod
    def execute(self, context: ContextT, parameters: ParametersT) -> ResultT:
        """Return a deterministic result without reading or writing external state."""
