"""LLM provider abstraction for plan generation and report narration.

The A14 brief requires an open large language model (DeepSeek, ChatGLM, LLaMA, Ollama…) to
drive the workflow. Two design constraints shape how it is wired in:

* **The deployment target is local and offline.** A planner that only works with a reachable
  API is not a working feature at a competition venue, so the rule-based planner stays the
  floor and the LLM is a refinement on top of it. When no provider is configured, or the
  provider fails, the system degrades to the deterministic path and says so.
* **The model's output is data, not authority.** A generated plan goes through the same
  Pydantic validation and the same static compliance proof as any other plan; a generated
  report goes through the same numeral validator. The model can be wrong, unavailable, or
  adversarial, and the worst it produces is a rejected artifact.

Providers speak the OpenAI-compatible chat-completions shape, which DeepSeek, Ollama,
vLLM, Xinference and most self-hosted ChatGLM/LLaMA deployments all expose. That keeps one
client working across every option the brief lists.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

# Models routinely wrap JSON in prose or a fenced block; both are recovered rather than
# treated as a failure, because a retry costs a round trip and usually returns the same
# shape.
_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


class LlmUnavailableError(Exception):
    """Raised when no provider is configured or the configured one cannot be reached."""


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str


@dataclass
class LlmResult:
    """A completion plus enough provenance to audit which model produced it."""

    text: str
    provider: str
    model: str
    latency_ms: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


class LlmProvider(Protocol):
    """Anything that can turn a message list into a completion."""

    name: str
    model: str

    def complete(self, messages: list[LlmMessage], *, temperature: float = 0.0) -> LlmResult:
        """Return a completion, or raise :class:`LlmUnavailableError`."""


@dataclass
class NullProvider:
    """The provider used when none is configured. Always unavailable, never silent.

    Having an explicit null implementation rather than ``None`` keeps every call site on one
    path: callers handle ``LlmUnavailableError`` and fall back, instead of scattering
    ``if provider is not None`` checks that are easy to get wrong.
    """

    name: str = "none"
    model: str = "none"

    def complete(self, messages: list[LlmMessage], *, temperature: float = 0.0) -> LlmResult:
        raise LlmUnavailableError("未配置大模型 Provider；系统使用确定性规则解析。")


@dataclass
class OpenAiCompatibleProvider:
    """Chat-completions client for DeepSeek, Ollama, vLLM, Xinference and similar.

    Uses ``urllib`` rather than an HTTP library so the offline deployment has one less
    dependency to vendor; the request shape is small and stable enough that it is not worth
    a package.
    """

    base_url: str
    model: str
    api_key: str = ""
    name: str = "openai_compatible"
    timeout_seconds: float = 60.0

    def complete(self, messages: list[LlmMessage], *, temperature: float = 0.0) -> LlmResult:
        import time
        import urllib.error
        import urllib.request

        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": message.role, "content": message.content} for message in messages
                ],
                "temperature": temperature,
                "stream": False,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started = time.perf_counter()
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise LlmUnavailableError(f"大模型服务不可用：{error}") from error

        try:
            text = str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise LlmUnavailableError(f"大模型返回结构不符合预期：{payload}") from error

        return LlmResult(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            raw=payload,
        )


@dataclass
class StaticProvider:
    """Returns canned completions. Used by tests and by the offline demonstration mode."""

    responses: list[str]
    name: str = "static"
    model: str = "static"
    _index: int = 0

    def complete(self, messages: list[LlmMessage], *, temperature: float = 0.0) -> LlmResult:
        if not self.responses:
            raise LlmUnavailableError("StaticProvider 未配置任何响应。")
        text = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        return LlmResult(text=text, provider=self.name, model=self.model)


def build_provider(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    timeout_seconds: float = 60.0,
) -> LlmProvider:
    """Construct the configured provider, or the null one when disabled."""

    kind = (provider or "none").strip().lower()
    if kind in {"", "none", "disabled", "off"}:
        return NullProvider()
    if not base_url or not model:
        return NullProvider()
    return OpenAiCompatibleProvider(
        base_url=base_url,
        model=model,
        api_key=api_key,
        name=kind,
        timeout_seconds=timeout_seconds,
    )


def extract_json(text: str) -> Any:
    """Pull the first JSON value out of a completion.

    Raises :class:`ValueError` when nothing parses, which callers treat exactly like an
    unavailable provider: fall back to the deterministic path rather than guess.
    """

    candidate = text.strip()
    for pattern in (_FENCED_JSON, _BARE_JSON):
        match = pattern.search(candidate)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(f"大模型输出中未找到合法 JSON：{candidate[:200]}") from error
