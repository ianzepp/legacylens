"""LLM model registry and multi-provider call abstraction."""

import os
import time
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for a single LLM to benchmark."""

    name: str  # display name, e.g. "gpt-4o-mini"
    provider: str  # "openai" or "anthropic"
    model_id: str  # API model ID
    temperature: float = 0.0
    max_tokens: int = 2048


# Example defaults — override via --models CLI flag
DEFAULT_MODELS: list[LLMConfig] = [
    LLMConfig(name="gpt-4o-mini", provider="openai", model_id="gpt-4o-mini"),
    LLMConfig(name="gpt-4o", provider="openai", model_id="gpt-4o"),
]

DEFAULT_GRADER = LLMConfig(
    name="claude-opus",
    provider="anthropic",
    model_id="claude-opus-4-20250514",
    max_tokens=1024,
)

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 8, 32]


def parse_model_spec(spec: str) -> LLMConfig:
    """Parse a 'provider:model_id' string into an LLMConfig.

    Examples:
        'openai:gpt-4o-mini' -> LLMConfig(name='gpt-4o-mini', provider='openai', ...)
        'anthropic:claude-sonnet-4-20250514' -> LLMConfig(name='claude-sonnet-4-20250514', ...)
    """
    parts = spec.split(":", 1)
    if len(parts) != 2 or parts[0] not in ("openai", "anthropic"):
        raise ValueError(
            f"Invalid model spec '{spec}'. Expected 'openai:<model>' or 'anthropic:<model>'"
        )
    provider, model_id = parts
    return LLMConfig(name=model_id, provider=provider, model_id=model_id)


def call_llm(
    config: LLMConfig, system_prompt: str, user_prompt: str
) -> tuple[str, float]:
    """Call an LLM and return (response_text, elapsed_seconds).

    Retries up to MAX_RETRIES times on transient errors.
    On final failure, returns ("ERROR: <message>", elapsed) instead of raising.
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            start = time.perf_counter()
            text = _call_provider(config, system_prompt, user_prompt)
            elapsed = time.perf_counter() - start
            return text, elapsed
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {wait}s: {e}")
                time.sleep(wait)

    elapsed = time.perf_counter() - start
    return f"ERROR: {last_error}", elapsed


def _call_provider(
    config: LLMConfig, system_prompt: str, user_prompt: str
) -> str:
    """Dispatch to the appropriate provider API."""
    if config.provider == "openai":
        return _call_openai(config, system_prompt, user_prompt)
    elif config.provider == "anthropic":
        return _call_anthropic(config, system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown provider: {config.provider}")


def _call_openai(
    config: LLMConfig, system_prompt: str, user_prompt: str
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=config.model_id,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def _call_anthropic(
    config: LLMConfig, system_prompt: str, user_prompt: str
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=config.model_id,
        system=system_prompt,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text
