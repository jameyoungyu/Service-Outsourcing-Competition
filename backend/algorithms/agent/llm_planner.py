"""LLM-authored plans and report narration, constrained by the existing validators.

The model is given the tool whitelist and asked for a JSON plan. What comes back is then
put through exactly the checks a rule-based plan goes through — unknown tool names, cycles,
dangling dependencies, test-partition access and high-impact gating — so the LLM's role is
to *propose*, never to authorise.

Report narration is constrained harder still: the model is told it may not write digits,
and :func:`algorithms.report.provenance.validate_draft` rejects the draft if it does. That
turns "please do not hallucinate numbers" from a request into a property of the pipeline.

Every path degrades to the deterministic implementation. A missing API key, an unreachable
Ollama, a malformed completion and a plan that fails its proof all land in the same place:
the rule-based result, plus a stated reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from algorithms.agent.compliance import verify_plan
from algorithms.agent.llm import (
    LlmMessage,
    LlmProvider,
    LlmUnavailableError,
    extract_json,
)
from algorithms.agent.planner import (
    CONFIRMATION_REQUIRED,
    TOOL_WHITELIST,
    ParsedIntent,
    PlannedStep,
    RuleBasedPlanner,
)

PLANNER_SYSTEM_PROMPT = f"""你是流程工业建模数据预处理系统的调度中枢。
把工程师的自然语言需求拆解为结构化工作流，只能使用以下工具，不得发明新工具：

{", ".join(TOOL_WHITELIST)}

严格输出 JSON，不要输出任何解释文字，格式为：
{{
  "steps": [
    {{"step_id": "s1", "tool": "profile_dataset", "depends_on": [], "parameters": {{}}}}
  ],
  "assumptions": ["..."]
}}

规则：
1. 第一步必须是 profile_dataset。
2. clean_data 必须在 detect_anomalies 之后；evaluate_model 必须在 fit_arx 之后。
3. select_variables、optimize_pipeline、export_dataset 属于高影响操作。
4. parameters 只填工程师明确给出的数值（如窗口长度、最大滞后、试验次数），不要臆造。
5. 不得引用测试集，不得让任何拟合型变换使用训练集以外的数据。"""

NARRATOR_SYSTEM_PROMPT = """你是工业过程辨识专家，负责撰写建模数据优选与辨识报告的结论段落。

**硬性规则：你绝对不能写出任何数字。** 一个阿拉伯数字都不许出现在正文里。
所有数值必须写成占位符 {{run:<运行编号>.<字段路径>}}，由系统从运行数据库解析后填入。

可用的运行编号与字段路径会在用户消息中给出。只能引用给定的路径，不得臆造字段。
输出中文段落，聚焦工程含义：为什么这样处理、结论对 APC 部署意味着什么、有什么局限。
不要输出 Markdown 标题，只输出正文段落。"""


@dataclass
class PlanOutcome:
    """A plan plus how it was produced, so the UI can be honest about provenance."""

    steps: list[PlannedStep]
    assumptions: list[str]
    stop_conditions: list[str]
    source: str = "rule_based"
    provider: str = "none"
    model: str = "none"
    fallback_reason: str | None = None
    raw_completion: str = ""
    latency_ms: float = 0.0

    @property
    def llm_authored(self) -> bool:
        return self.source == "llm"


@dataclass
class NarrationOutcome:
    """An LLM narrative that passed the numeral check, or the reason it did not."""

    text: str = ""
    source: str = "template"
    provider: str = "none"
    model: str = "none"
    fallback_reason: str | None = None
    attempts: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)


class LlmPlanner:
    """Ask the model for a plan; accept it only if it survives every validator."""

    def __init__(self, provider: LlmProvider, *, code_version: str = "1.0.0") -> None:
        self._provider = provider
        self._code_version = code_version
        self._fallback = RuleBasedPlanner()

    def plan(self, message: str, intent: ParsedIntent) -> PlanOutcome:
        steps, assumptions, stop_conditions = self._fallback.plan(intent)
        baseline = PlanOutcome(
            steps=steps,
            assumptions=list(assumptions),
            stop_conditions=list(stop_conditions),
        )

        try:
            result = self._provider.complete(
                [
                    LlmMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
                    LlmMessage(role="user", content=message),
                ]
            )
        except LlmUnavailableError as error:
            baseline.fallback_reason = str(error)
            return baseline

        try:
            payload = extract_json(result.text)
            candidate = _coerce_steps(payload)
        except (ValueError, KeyError, TypeError) as error:
            baseline.fallback_reason = f"大模型输出无法解析为合法计划：{error}"
            baseline.provider, baseline.model = result.provider, result.model
            baseline.raw_completion = result.text
            return baseline

        if not candidate:
            baseline.fallback_reason = "大模型返回了空计划。"
            baseline.provider, baseline.model = result.provider, result.model
            baseline.raw_completion = result.text
            return baseline

        proof = verify_plan(
            [
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "depends_on": list(step.depends_on),
                    "parameters": dict(step.parameters),
                    "requires_confirmation": step.requires_confirmation,
                }
                for step in candidate
            ],
            code_version=self._code_version,
        )
        if not proof.passed:
            # The model proposed something the rules forbid. Falling back is the safe
            # outcome, and the reason is surfaced rather than swallowed.
            baseline.fallback_reason = "大模型计划未通过合规校验：" + "；".join(
                check.detail for check in proof.failures
            )
            baseline.provider, baseline.model = result.provider, result.model
            baseline.raw_completion = result.text
            return baseline

        llm_assumptions = list(_coerce_assumptions(payload))
        llm_assumptions.append(
            f"本计划由大模型 {result.provider}/{result.model} 生成，并已通过白名单与合规静态校验。"
        )
        return PlanOutcome(
            steps=candidate,
            assumptions=llm_assumptions + list(assumptions),
            stop_conditions=list(stop_conditions),
            source="llm",
            provider=result.provider,
            model=result.model,
            raw_completion=result.text,
            latency_ms=result.latency_ms,
        )


class LlmNarrator:
    """Ask the model for prose; reject it if it contains a single unbound digit."""

    def __init__(self, provider: LlmProvider, *, max_attempts: int = 3) -> None:
        self._provider = provider
        self._max_attempts = max_attempts

    def narrate(self, *, context: str, available_paths: list[str]) -> NarrationOutcome:
        from algorithms.report.provenance import validate_draft

        outcome = NarrationOutcome()
        paths = "\n".join(f"- {{{{run:{path}}}}}" for path in available_paths)
        user_message = f"{context}\n\n可引用的占位符：\n{paths}"

        for attempt in range(1, self._max_attempts + 1):
            outcome.attempts = attempt
            try:
                result = self._provider.complete(
                    [
                        LlmMessage(role="system", content=NARRATOR_SYSTEM_PROMPT),
                        LlmMessage(role="user", content=user_message),
                    ],
                    temperature=0.2,
                )
            except LlmUnavailableError as error:
                outcome.fallback_reason = str(error)
                return outcome

            outcome.provider, outcome.model = result.provider, result.model
            violations = validate_draft(result.text)
            if not violations:
                outcome.text = result.text.strip()
                outcome.source = "llm"
                return outcome

            outcome.violations = [violation.to_payload() for violation in violations[:10]]
            user_message = (
                f"{context}\n\n可引用的占位符：\n{paths}\n\n"
                f"上一次输出被拒绝，因为它包含了未溯源的数字："
                f"{', '.join(violation.text for violation in violations[:5])}。"
                "请重写，任何数值都必须写成占位符。"
            )

        outcome.fallback_reason = (
            f"大模型连续 {self._max_attempts} 次输出未溯源数字，已回退到模板化结论。"
        )
        return outcome


def _coerce_steps(payload: Any) -> list[PlannedStep]:
    """Turn raw model output into typed steps, rejecting anything unrecognised."""

    raw_steps = payload.get("steps") if isinstance(payload, dict) else payload
    if not isinstance(raw_steps, list):
        raise TypeError("steps 必须是数组")

    steps: list[PlannedStep] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            raise TypeError("每个步骤必须是对象")
        tool = str(item.get("tool", "")).strip()
        if tool not in TOOL_WHITELIST:
            raise ValueError(f"非白名单工具：{tool!r}")
        step_id = str(item.get("step_id") or f"s{index}").strip() or f"s{index}"
        if step_id in seen:
            raise ValueError(f"步骤编号重复：{step_id}")
        seen.add(step_id)

        depends = item.get("depends_on") or []
        if not isinstance(depends, list):
            raise TypeError("depends_on 必须是数组")
        parameters = item.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise TypeError("parameters 必须是对象")

        steps.append(
            PlannedStep(
                step_id=step_id,
                tool=tool,
                depends_on=tuple(str(value) for value in depends),
                parameters={str(key): value for key, value in parameters.items()},
                # The flag is set from the whitelist, not from the model: a model that
                # forgot it must not thereby unlock an unconfirmed export.
                requires_confirmation=tool in CONFIRMATION_REQUIRED,
            )
        )
    return steps


def _coerce_assumptions(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("assumptions") or []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()][:10]
