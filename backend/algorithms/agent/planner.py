"""Natural-language intent parsing and deterministic plan construction.

The brief asks for an LLM to decompose an engineer's request into a workflow. Two design
choices follow from the deployment target rather than from convenience:

* **The plan is data, not code.** The model never emits Python; it emits a step list drawn
  from a fixed tool whitelist, which is then validated before anything runs. An LLM that
  hallucinates a tool name produces a rejected plan, not an incident.
* **The rule-based planner is the floor, not the fallback.** The system is specified to run
  locally and offline, so intent parsing that only works with a reachable API is not a
  working feature. This module resolves intent deterministically from the request text; an
  LLM provider, when configured, refines wording and parameters on top of the same
  validated structure.

Intent is matched on Chinese and English industrial vocabulary because that is what the
operators of these systems actually type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# The only tools an agent may schedule. Anything else is rejected by the validator.
TOOL_WHITELIST: tuple[str, ...] = (
    "profile_dataset",
    "align_and_resample",
    "detect_anomalies",
    "clean_data",
    "detect_dynamic_segments",
    "estimate_delays",
    "analyze_collinearity",
    "select_variables",
    "fit_arx",
    "evaluate_model",
    "optimize_pipeline",
    "generate_report",
    "export_dataset",
)

# Tools whose effect is expensive or destructive enough to need a human decision first.
CONFIRMATION_REQUIRED: frozenset[str] = frozenset(
    {"select_variables", "optimize_pipeline", "export_dataset"}
)

# Ordering constraints. A tool may only run after everything it depends on.
TOOL_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "profile_dataset": (),
    "align_and_resample": ("profile_dataset",),
    "detect_anomalies": ("profile_dataset",),
    "clean_data": ("detect_anomalies",),
    "detect_dynamic_segments": ("profile_dataset",),
    "estimate_delays": ("profile_dataset",),
    "analyze_collinearity": ("profile_dataset",),
    "select_variables": ("analyze_collinearity",),
    "fit_arx": ("profile_dataset",),
    "evaluate_model": ("fit_arx",),
    "optimize_pipeline": ("profile_dataset",),
    "generate_report": (),
    "export_dataset": (),
}

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "clean": (
        "清洗",
        "异常",
        "缺失",
        "重采样",
        "对齐",
        "规整",
        "去噪",
        "clean",
        "resample",
        "outlier",
    ),
    "segment": (
        "动态",
        "区间",
        "优选",
        "截取",
        "高信噪比",
        "稳态",
        "segment",
        "dynamic",
        "select data",
    ),
    "delay": ("时滞", "滞后", "纯滞后", "延迟", "delay", "lag", "dead time"),
    "collinearity": ("共线", "相关性", "冗余", "降维", "collinear", "vif", "redundant"),
    "model": ("辨识", "建模", "模型", "arx", "identif", "model"),
    "optimize": ("寻优", "闭环", "自动优化", "调参", "最佳", "optimi", "closed loop", "tune"),
    "report": ("报告", "结论", "解释", "report", "explain"),
    "export": ("导出", "交付", "下载", "export", "deliver"),
}


@dataclass(frozen=True)
class ParsedIntent:
    """What the engineer asked for, as flags plus any numbers they specified."""

    goals: frozenset[str]
    parameters: dict[str, Any] = field(default_factory=dict)
    mentioned_columns: tuple[str, ...] = ()

    def wants(self, goal: str) -> bool:
        return goal in self.goals


@dataclass(frozen=True)
class PlannedStep:
    """One validated step of an execution plan."""

    step_id: str
    tool: str
    depends_on: tuple[str, ...]
    parameters: dict[str, Any]
    requires_confirmation: bool


def parse_intent(message: str) -> ParsedIntent:
    """Resolve a free-text request into goal flags and any explicit parameters."""

    lowered = message.lower()
    goals = {
        goal
        for goal, keywords in _KEYWORDS.items()
        if any(keyword.lower() in lowered for keyword in keywords)
    }

    parameters: dict[str, Any] = {}
    trials = re.search(r"(\d+)\s*(?:次|轮)?\s*(?:trial|试验|迭代)", lowered)
    if trials:
        parameters["max_trials"] = max(1, min(int(trials.group(1)), 500))
    window = re.search(r"(?:窗口|窗长|window)\D{0,6}(\d+)", lowered)
    if window:
        parameters["window_size"] = max(5, min(int(window.group(1)), 2000))
    max_lag = re.search(r"(?:最大滞后|max[_ ]?lag)\D{0,6}(\d+)", lowered)
    if max_lag:
        parameters["max_lag"] = max(1, min(int(max_lag.group(1)), 1000))
    segments = re.search(r"(?:保留|选取|取)\s*(\d+)\s*(?:个)?\s*(?:区间|段)", lowered)
    if segments:
        parameters["max_segments"] = max(1, min(int(segments.group(1)), 100))

    columns = tuple(dict.fromkeys(re.findall(r"\b([uy]\d{1,2})\b", lowered)))
    return ParsedIntent(goals=frozenset(goals), parameters=parameters, mentioned_columns=columns)


class RuleBasedPlanner:
    """Build a whitelisted, dependency-ordered plan from a parsed intent.

    The planner is deliberately conservative: an unrecognised request produces a profiling
    step rather than a guess, because silently running a different workflow than the one
    asked for is worse than doing the obvious safe thing and saying so.
    """

    def plan(self, intent: ParsedIntent) -> tuple[list[PlannedStep], list[str], list[str]]:
        """Return ``(steps, assumptions, stop_conditions)``."""

        assumptions: list[str] = []
        emitted: dict[str, str] = {}
        steps: list[PlannedStep] = []

        def emit(tool: str, parameters: dict[str, Any] | None = None) -> str:
            if tool in emitted:
                return emitted[tool]
            depends = tuple(
                emitted[prerequisite]
                for prerequisite in TOOL_PREREQUISITES.get(tool, ())
                if prerequisite in emitted
            )
            step_id = f"s{len(steps) + 1}"
            steps.append(
                PlannedStep(
                    step_id=step_id,
                    tool=tool,
                    depends_on=depends,
                    parameters=parameters or {},
                    requires_confirmation=tool in CONFIRMATION_REQUIRED,
                )
            )
            emitted[tool] = step_id
            return step_id

        # Profiling is unconditional: every later decision reads the quality evidence.
        emit("profile_dataset")

        wants_model = intent.wants("model") or intent.wants("optimize")
        if intent.wants("clean"):
            emit("detect_anomalies")
            emit("clean_data")
        if intent.wants("segment"):
            emit(
                "detect_dynamic_segments",
                _subset(intent.parameters, ("window_size", "max_segments")),
            )
        if intent.wants("delay"):
            emit("estimate_delays", _subset(intent.parameters, ("max_lag",)))
        if intent.wants("collinearity"):
            emit("analyze_collinearity")
            emit("select_variables")
        if wants_model:
            if not intent.wants("segment"):
                emit(
                    "detect_dynamic_segments",
                    _subset(intent.parameters, ("window_size", "max_segments")),
                )
                assumptions.append("建模前默认执行质量门控与 D-最优区间优选。")
            emit("fit_arx")
            emit("evaluate_model")
        if intent.wants("optimize"):
            emit("optimize_pipeline", _subset(intent.parameters, ("max_trials",)))
        if intent.wants("report"):
            emit("generate_report")
        if intent.wants("export"):
            emit("export_dataset")

        if len(steps) == 1:
            assumptions.append(
                "未能从指令中识别出明确的处理意图，仅执行数据质量诊断；请补充说明需要的步骤。"
            )
        if intent.mentioned_columns:
            assumptions.append(
                f"指令中提及的变量：{', '.join(intent.mentioned_columns)}；"
                "实际使用的变量以数据集已确认的列角色为准。"
            )
        assumptions.append("模型评价以验证集自由仿真 FIT 为主指标，一步预测 FIT 仅作诊断。")

        stop_conditions = [
            "达到最大试验次数或超时",
            "连续若干试验目标值无提升",
            "用户取消",
            "任一工具返回不可恢复错误",
        ]
        return steps, assumptions, stop_conditions


def _subset(parameters: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: parameters[key] for key in keys if key in parameters}
