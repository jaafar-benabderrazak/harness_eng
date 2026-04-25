"""Single point of contact with the model. All harnesses route through call().

Any harness that imports a provider SDK (anthropic, ollama) directly is a bug.
The whole point of the experiment is that this module is frozen while the
harnesses change. Two backends are supported:
 - "anthropic": Anthropic Messages API (requires ANTHROPIC_API_KEY + $ credits)
 - "ollama":    local Ollama runtime (free, requires `ollama serve` + model pulled)

Selection via HARNESS_BACKEND env var. Tool-use + message shape is translated
so harnesses can keep speaking the Anthropic content-block vocabulary.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .config import CONFIG

_client: Any = None


@dataclass
class ModelCall:
    input_tokens: int
    output_tokens: int
    latency_s: float
    stop_reason: str
    content: list[dict[str, Any]]
    usage_raw: dict[str, Any]


def call(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    temperature: float | None = None,
) -> ModelCall:
    """Single entry point. Per-call temperature overrides CONFIG default."""
    eff_temp = CONFIG.model.temperature if temperature is None else temperature
    if CONFIG.model.backend == "ollama":
        return _call_ollama(system, messages, tools, temperature=eff_temp)
    return _call_anthropic(system, messages, tools, temperature=eff_temp)


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def _get_client() -> Any:
    global _client
    if _client is None:
        # Deferred import so the module is importable without the SDK installed.
        from anthropic import Anthropic
        _client = Anthropic(max_retries=0)
    return _client


def _call_anthropic(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float,
) -> ModelCall:
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": CONFIG.model.name,
        "max_tokens": CONFIG.model.max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    t0 = time.perf_counter()
    resp = client.messages.create(**kwargs)
    latency = time.perf_counter() - t0

    try:
        usage_raw = resp.usage.model_dump()
    except AttributeError:
        usage_raw = dict(resp.usage.__dict__)

    return ModelCall(
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        latency_s=latency,
        stop_reason=resp.stop_reason or "",
        content=[b.model_dump() for b in resp.content],
        usage_raw=usage_raw,
    )


# ---------------------------------------------------------------------------
# Ollama backend — translates Anthropic content-block shape to/from Ollama's
# ---------------------------------------------------------------------------

def _to_ollama_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic content-block messages -> Ollama role/content/tool_calls messages."""
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for m in messages:
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        # content is a list of blocks — what they mean depends on role
        if role == "assistant":
            text_parts = [b["text"] for b in content if b.get("type") == "text"]
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
            if tool_uses:
                msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tu["name"],
                            "arguments": tu.get("input", {}) or {},
                        }
                    }
                    for tu in tool_uses
                ]
            out.append(msg)
        else:  # user role with a block list — usually tool_result blocks
            for b in content:
                t = b.get("type")
                if t == "tool_result":
                    result = b.get("content", "")
                    if isinstance(result, list):
                        result = "".join(
                            x.get("text", "") if isinstance(x, dict) else str(x)
                            for x in result
                        )
                    out.append({"role": "tool", "content": str(result)})
                elif t == "text":
                    out.append({"role": "user", "content": b.get("text", "")})
    return out


def _to_ollama_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _from_ollama_response(resp: Any, latency: float) -> ModelCall:
    """Ollama chat response -> Anthropic-shape ModelCall."""
    msg = resp.message
    content_blocks: list[dict[str, Any]] = []
    text = getattr(msg, "content", None) or ""
    if text:
        content_blocks.append({"type": "text", "text": text})
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        args = tc.function.arguments
        if not isinstance(args, dict):
            args = dict(args) if args else {}
        content_blocks.append({
            "type": "tool_use",
            "id": f"tu_{uuid.uuid4().hex[:10]}",
            "name": tc.function.name,
            "input": args,
        })
    stop_reason = "tool_use" if tool_calls else "end_turn"
    input_tokens = getattr(resp, "prompt_eval_count", 0) or 0
    output_tokens = getattr(resp, "eval_count", 0) or 0
    usage_raw = {
        "model": getattr(resp, "model", ""),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_duration_ns": getattr(resp, "total_duration", 0),
        "load_duration_ns": getattr(resp, "load_duration", 0),
        "prompt_eval_duration_ns": getattr(resp, "prompt_eval_duration", 0),
        "eval_duration_ns": getattr(resp, "eval_duration", 0),
    }
    return ModelCall(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_s=latency,
        stop_reason=stop_reason,
        content=content_blocks,
        usage_raw=usage_raw,
    )


def _call_ollama(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float,
) -> ModelCall:
    import ollama  # deferred — installed only when backend=ollama

    om = _to_ollama_messages(system, messages)
    ot = _to_ollama_tools(tools)
    options: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": CONFIG.model.max_tokens,
    }
    t0 = time.perf_counter()
    kwargs: dict[str, Any] = {"model": CONFIG.model.name, "messages": om, "options": options}
    if ot:
        kwargs["tools"] = ot
    resp = ollama.chat(**kwargs)
    latency = time.perf_counter() - t0
    return _from_ollama_response(resp, latency)
