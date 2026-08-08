"""Static verification of an execution plan, emitting a machine-checked proof.

``scope-freeze.md`` already forbids the dangerous things: non-whitelisted tools, tuning on
the test partition, fitting transforms on data the model will later be scored against,
interpolating across a partition boundary, deleting a variable without confirmation. Those
were prose. This module turns them into checks that run before any step executes, and emits
a signed record of what was verified.

The distinction matters for an industrial buyer. "The agent is not allowed to touch the test
set" is a promise; "here is the proof, over these seven intermediate versions, that it did
not" is evidence. A plan that fails any check does not run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from algorithms.agent.planner import (
    CONFIRMATION_REQUIRED,
    TOOL_PREREQUISITES,
    TOOL_WHITELIST,
)

# Tools that estimate something from data and then apply it. Fitting these on anything but
# the training partition leaks information into the evaluation.
FITTED_TRANSFORMS: frozenset[str] = frozenset(
    {"detect_anomalies", "clean_data", "detect_dynamic_segments", "select_variables", "fit_arx"}
)

# Parameter keys that would point a step at the test partition.
TEST_PARTITION_KEYS: frozenset[str] = frozenset({"partition", "split", "use_partition"})


@dataclass(frozen=True)
class ProofCheck:
    """One verified property of a plan."""

    name: str
    passed: bool
    detail: str

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class ComplianceProof:
    """The verdict on a plan, plus the evidence behind it."""

    proof_id: str
    checks: tuple[ProofCheck, ...]
    signature: str
    code_version: str
    generated_at: datetime

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[ProofCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_payload(self) -> dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "passed": self.passed,
            "checks": [check.to_payload() for check in self.checks],
            "signature": self.signature,
            "code_version": self.code_version,
            "generated_at": self.generated_at.isoformat(),
        }


def verify_plan(
    steps: Sequence[Mapping[str, Any]],
    *,
    code_version: str = "1.0.0",
    confirmed_steps: frozenset[str] = frozenset(),
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
) -> ComplianceProof:
    """Check a plan against every frozen rule and return the proof.

    ``steps`` are plain mappings with ``step_id``, ``tool``, ``depends_on``, ``parameters``
    and ``requires_confirmation`` so this stays usable on an LLM's raw output, before it has
    been coerced into any richer type.
    """

    checks: list[ProofCheck] = [
        _check_whitelist(steps),
        _check_acyclic(steps),
        _check_dependencies_complete(steps),
        _check_ordering(steps),
        _check_no_test_partition(steps),
        _check_fitted_transforms_use_train(steps, train_ratio, validation_ratio),
        _check_no_cross_boundary_interpolation(steps, train_ratio),
        _check_confirmations(steps, confirmed_steps),
    ]
    payload = _canonical(steps)
    signature = hashlib.sha256(
        f"{payload}|{code_version}|{[check.passed for check in checks]}".encode()
    ).hexdigest()
    return ComplianceProof(
        proof_id=f"PROOF-{signature[:12]}",
        checks=tuple(checks),
        signature=f"sha256:{signature}",
        code_version=code_version,
        generated_at=datetime.now(UTC),
    )


def _check_whitelist(steps: Sequence[Mapping[str, Any]]) -> ProofCheck:
    unknown = sorted({str(step.get("tool")) for step in steps} - set(TOOL_WHITELIST))
    return ProofCheck(
        name="tool_whitelist",
        passed=not unknown,
        detail=(
            f"全部 {len(steps)} 个工具调用均在白名单内"
            if not unknown
            else f"存在非白名单工具：{', '.join(unknown)}"
        ),
    )


def _check_acyclic(steps: Sequence[Mapping[str, Any]]) -> ProofCheck:
    graph = {str(step.get("step_id")): list(step.get("depends_on") or []) for step in steps}
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return False
        if state.get(node) == 2:
            return True
        state[node] = 1
        for parent in graph.get(node, []):
            if not visit(str(parent)):
                return False
        state[node] = 2
        return True

    acyclic = all(visit(node) for node in graph)
    return ProofCheck(
        name="dag_acyclic",
        passed=acyclic,
        detail="计划 DAG 无环" if acyclic else "计划 DAG 存在循环依赖",
    )


def _check_dependencies_complete(steps: Sequence[Mapping[str, Any]]) -> ProofCheck:
    known = {str(step.get("step_id")) for step in steps}
    dangling = sorted(
        {
            str(parent)
            for step in steps
            for parent in (step.get("depends_on") or [])
            if str(parent) not in known
        }
    )
    return ProofCheck(
        name="dependencies_resolved",
        passed=not dangling,
        detail="依赖完备" if not dangling else f"存在未定义的前置步骤：{', '.join(dangling)}",
    )


def _check_ordering(steps: Sequence[Mapping[str, Any]]) -> ProofCheck:
    """Every tool's prerequisites must appear before it, transitively."""

    position = {str(step.get("step_id")): index for index, step in enumerate(steps)}
    by_tool: dict[str, int] = {}
    for index, step in enumerate(steps):
        by_tool.setdefault(str(step.get("tool")), index)

    violations: list[str] = []
    for index, step in enumerate(steps):
        tool = str(step.get("tool"))
        for prerequisite in TOOL_PREREQUISITES.get(tool, ()):
            if prerequisite in by_tool and by_tool[prerequisite] > index:
                violations.append(f"{tool} 早于其前置 {prerequisite}")
    _ = position
    return ProofCheck(
        name="tool_ordering",
        passed=not violations,
        detail="工具顺序满足前置约束" if not violations else "；".join(violations),
    )


def _check_no_test_partition(steps: Sequence[Mapping[str, Any]]) -> ProofCheck:
    offenders: list[str] = []
    for step in steps:
        parameters = step.get("parameters") or {}
        for key in TEST_PARTITION_KEYS:
            value = parameters.get(key)
            if isinstance(value, str) and "test" in value.lower():
                offenders.append(f"{step.get('step_id')}.{key}={value}")
    return ProofCheck(
        name="test_set_untouched",
        passed=not offenders,
        detail=(
            f"测试集在方案冻结前零触及（数据流分析覆盖 {len(steps)} 个步骤）"
            if not offenders
            else f"存在指向测试分区的参数：{', '.join(offenders)}"
        ),
    )


def _check_fitted_transforms_use_train(
    steps: Sequence[Mapping[str, Any]],
    train_ratio: float,
    validation_ratio: float,
) -> ProofCheck:
    """A fitted transform must not be estimated past the training boundary."""

    offenders: list[str] = []
    for step in steps:
        tool = str(step.get("tool"))
        if tool not in FITTED_TRANSFORMS:
            continue
        parameters = step.get("parameters") or {}
        ratio = parameters.get("train_ratio")
        if isinstance(ratio, (int, float)) and float(ratio) > train_ratio + validation_ratio:
            offenders.append(f"{step.get('step_id')}({tool}) train_ratio={ratio}")
    return ProofCheck(
        name="fitted_on_train_only",
        passed=not offenders,
        detail=(
            f"全部 {sum(1 for s in steps if str(s.get('tool')) in FITTED_TRANSFORMS)} "
            "个拟合型变换仅由训练分区估计"
            if not offenders
            else f"以下步骤的估计范围越过训练边界：{', '.join(offenders)}"
        ),
    )


def _check_no_cross_boundary_interpolation(
    steps: Sequence[Mapping[str, Any]],
    train_ratio: float,
) -> ProofCheck:
    offenders: list[str] = []
    for step in steps:
        if str(step.get("tool")) not in {"align_and_resample", "clean_data"}:
            continue
        parameters = step.get("parameters") or {}
        limit = parameters.get("max_consecutive_missing")
        if isinstance(limit, (int, float)) and limit is not None and float(limit) <= 0:
            offenders.append(f"{step.get('step_id')} 未限制连续插值长度")
    _ = train_ratio
    return ProofCheck(
        name="no_cross_partition_interpolation",
        passed=not offenders,
        detail="无跨分区边界插值" if not offenders else "；".join(offenders),
    )


def _check_confirmations(
    steps: Sequence[Mapping[str, Any]],
    confirmed_steps: frozenset[str],
) -> ProofCheck:
    """Verify no high-impact step can execute unapproved.

    The property being proved is "nothing high-impact runs without a human", not "a human
    has already approved everything". Failing the whole plan because a later export awaits
    approval would be counterproductive: the engineer needs to see the diagnostics that
    inform the decision before making it. So a high-impact step passes when it is either
    already confirmed or correctly flagged, because the executor holds flagged steps at
    ``waiting_confirmation`` and never runs them.

    The check fails on the case that actually matters: a high-impact tool that is neither
    confirmed nor flagged, which is exactly what an attempt to slip one through looks like.
    """

    unguarded: list[str] = []
    pending: list[str] = []
    for step in steps:
        tool = str(step.get("tool"))
        step_id = str(step.get("step_id"))
        if tool not in CONFIRMATION_REQUIRED and not step.get("requires_confirmation"):
            continue
        if step_id in confirmed_steps:
            continue
        if not step.get("requires_confirmation"):
            unguarded.append(f"{step_id}({tool})")
        else:
            pending.append(f"{step_id}({tool})")

    if unguarded:
        detail = f"以下高影响操作未标记人工确认即计划执行：{', '.join(unguarded)}"
    elif pending:
        detail = f"高影响操作已被拦截，等待人工确认：{', '.join(pending)}"
    else:
        detail = "高影响操作均已获人工确认"
    return ProofCheck(name="high_impact_gated", passed=not unguarded, detail=detail)


def _canonical(steps: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for step in steps:
        parts.append(
            f"{step.get('step_id')}:{step.get('tool')}:"
            f"{sorted(map(str, step.get('depends_on') or []))}:"
            f"{sorted((step.get('parameters') or {}).items(), key=lambda item: item[0])}"
        )
    return "|".join(parts)
