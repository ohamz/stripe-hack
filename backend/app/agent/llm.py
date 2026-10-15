"""The one place Tab makes structured LLM calls.

Uses Cognee's LLMGateway (docs: guides/low-level-llm) so Tab and Cognee share one provider,
one key and one model configuration (LLM_PROVIDER / LLM_MODEL / LLM_API_KEY).
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.memory.cognee_client import require_llm

T = TypeVar("T", bound=BaseModel)


class LLMCallFailed(RuntimeError):
    pass


async def structured(system_prompt: str, text: str, response_model: type[T]) -> T:
    require_llm()
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    try:
        result = await LLMGateway.acreate_structured_output(text, system_prompt, response_model)
    except Exception as exc:  # surface the provider's exact error
        raise LLMCallFailed(f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(result, response_model):
        raise LLMCallFailed(f"expected {response_model.__name__}, got {type(result).__name__}")
    return result
