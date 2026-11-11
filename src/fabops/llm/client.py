"""Single entry point for every LLM call (CLAUDE.md, 成本守則).

- Provider switch: ollama / openai / gemini via OpenAI-compatible APIs; anthropic natively.
- Disk cache whose key includes the caller's permission scope, so a low-privilege user can
  never hit a cached answer produced for a higher-privilege user.
- Usage log (JSONL): tokens, latency, cost. No prompt or answer text is logged (ADR-0007).
- Structured output: JSON validated against a Pydantic model, with one repair retry.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from fabops.authz.scope import Scope
from fabops.config import get_settings
from fabops.llm.pricing import cost_usd

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
    # Gemini's OpenAI-compatible endpoint; confirm against Google's docs before use.
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}
API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    name: str

    def complete(
        self, messages: list[dict], model: str, temperature: float, max_tokens: int
    ) -> Completion: ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
    ):
        from openai import OpenAI

        self.name = name
        # "none" turns off qwen3 thinking on Ollama; `/no_think` in the prompt is ignored
        # there (docs/experiments.md, 2026-11-08).
        self.reasoning_effort = reasoning_effort
        key = api_key or os.environ.get(API_KEY_ENV.get(name, ""), "") or "not-needed"
        self._client = OpenAI(base_url=base_url or DEFAULT_BASE_URLS[name], api_key=key)

    def complete(self, messages, model, temperature, max_tokens) -> Completion:
        extra = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
        r = self._client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **extra
        )
        return Completion(r.choices[0].message.content or "", *billed_tokens(r.usage))


def billed_tokens(u) -> tuple[int, int]:
    """(input, output) tokens. Gemini's OpenAI-compatible usage leaves thinking tokens out of
    `completion_tokens` but counts them in `total_tokens`; they are billed as output, so the
    output is taken as `total - prompt` whenever that is larger."""
    if u is None:
        return 0, 0
    prompt, completion = u.prompt_tokens or 0, u.completion_tokens or 0
    total = getattr(u, "total_tokens", None) or 0
    return prompt, max(completion, total - prompt)


# How each model turns thinking off. Claude Sonnet 5.5 rejects `disabled` and asks for
# `between_tools` (it then only thinks between tool calls; we never send tools, so it does not
# think at all). Found on the first Phase 3 run, 2026-11-11 (400 before any output).
THINKING_OFF: dict[str, dict] = {"claude-sonnet-5-5": {"type": "between_tools"}}


class AnthropicProvider:
    """Claude via the official SDK.

    The current API (2026-10-21) rejects sampling parameters, so `temperature` is accepted
    for the Provider interface but never sent. `reasoning_effort="none"` turns thinking off
    (`thinking: disabled`, accepted by Claude Haiku 5.5 at its default effort), matching the
    no-think setting used for qwen3; any other value leaves the model's default thinking on.
    """

    name = "anthropic"

    def __init__(self, api_key: str | None = None, reasoning_effort: str | None = None):
        import anthropic

        self.reasoning_effort = reasoning_effort
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def request_kwargs(self, messages: list[dict], model: str, max_tokens: int) -> dict:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        rest = [m for m in messages if m["role"] != "system"]
        kwargs: dict = {"model": model, "messages": rest, "max_tokens": max_tokens}
        if system:
            kwargs["system"] = system
        if self.reasoning_effort == "none":
            kwargs["thinking"] = THINKING_OFF.get(model, {"type": "disabled"})
        return kwargs

    def complete(self, messages, model, temperature, max_tokens) -> Completion:
        r = self._client.messages.create(**self.request_kwargs(messages, model, max_tokens))
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens)


def make_provider(
    name: str,
    base_url: str | None = None,
    api_key: str | None = None,
    reasoning_effort: str | None = None,
) -> Provider:
    if name == "anthropic":
        return AnthropicProvider(api_key, reasoning_effort)
    return OpenAICompatibleProvider(name, base_url, api_key, reasoning_effort)


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: int
    cached: bool


class LLMClient:
    def __init__(
        self,
        provider: Provider,
        model: str,
        cache_dir: str | Path = ".cache/llm",
        usage_log: str | Path = ".cache/usage.jsonl",
        *,
        unsafe_share_cache_across_scopes: bool = False,
    ):
        # True only for the "no exit checks" leak-test baseline (PLAN Phase 1): it shows
        # what leaks through the cache when the scope is left out of the key.
        self.unsafe_share_cache = unsafe_share_cache_across_scopes
        self.provider = provider
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.usage_log = Path(usage_log)

    @classmethod
    def from_env(cls) -> LLMClient:
        """Build a client from `.env` / environment variables (see fabops.config)."""
        cfg = get_settings()
        return cls(
            make_provider(
                cfg.llm_provider,
                cfg.llm_base_url,
                cfg.api_key(cfg.llm_provider),
                cfg.llm_reasoning_effort,
            ),
            cfg.llm_model,
            cfg.fabops_cache_dir,
            cfg.fabops_usage_log,
        )

    # ------------------------------------------------------------------ core

    def cache_key(
        self, messages: list[dict], scope: Scope, temperature: float, max_tokens: int
    ) -> str:
        payload = {
            "provider": self.provider.name,
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": getattr(self.provider, "reasoning_effort", None),
            # never share cached answers across permission scopes
            "scope": "shared" if self.unsafe_share_cache else scope.key(),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def chat(
        self,
        messages: list[dict],
        scope: Scope,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        purpose: str = "chat",
    ) -> LLMResult:
        key = self.cache_key(messages, scope, temperature, max_tokens)
        path = self.cache_dir / f"{key}.json"
        start = time.perf_counter()
        cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        # Exit check on the cache: an entry is only served to the scope that produced it.
        # The key already includes the scope; this guards against key collisions, a copied
        # cache directory, or a future change that drops the scope from the key.
        if (
            cached is not None
            and not self.unsafe_share_cache
            and cached.get("scope") != scope.key()
        ):
            cached = None
        if cached is not None:
            c = cached
            result = LLMResult(c["text"], c["input_tokens"], c["output_tokens"], 0.0, 0, True)
        else:
            comp = self.provider.complete(messages, self.model, temperature, max_tokens)
            latency = int((time.perf_counter() - start) * 1000)
            cost = cost_usd(self.provider.name, self.model, comp.input_tokens, comp.output_tokens)
            result = LLMResult(
                comp.text, comp.input_tokens, comp.output_tokens, cost, latency, False
            )
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "scope": scope.key(),
                        "text": comp.text,
                        "input_tokens": comp.input_tokens,
                        "output_tokens": comp.output_tokens,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        self._log(result, scope, purpose)
        return result

    def structured(
        self,
        messages: list[dict],
        schema: type[T],
        scope: Scope,
        *,
        max_tokens: int = 1024,
        purpose: str = "structured",
    ) -> tuple[T, list[LLMResult]]:
        """Ask for JSON matching `schema`; retry once with the validation error."""
        instruction = "只輸出一個 JSON 物件，不要有其他文字。JSON Schema：\n" + json.dumps(
            schema.model_json_schema(), ensure_ascii=False
        )
        msgs = [{"role": "system", "content": instruction}, *messages]
        results = []
        for attempt in range(2):
            r = self.chat(msgs, scope, max_tokens=max_tokens, purpose=f"{purpose}#{attempt}")
            results.append(r)
            try:
                return schema.model_validate_json(extract_json(r.text)), results
            except (ValidationError, ValueError) as e:
                msgs = [
                    *msgs,
                    {"role": "assistant", "content": r.text},
                    {"role": "user", "content": f"輸出不符合 schema，請修正後重新輸出：{e}"},
                ]
        raise ValueError(f"model output did not match {schema.__name__} after retry")

    # ------------------------------------------------------------------ logging

    def _log(self, r: LLMResult, scope: Scope, purpose: str) -> None:
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "purpose": purpose,
            "provider": self.provider.name,
            "model": self.model,
            "scope": scope.key(),
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "cached": r.cached,
        }
        with self.usage_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> str:
    """Return the JSON object in a model reply (handles code fences and <think> blocks)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = _JSON_BLOCK.search(text)
    if m:
        return m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return text[start : end + 1]
