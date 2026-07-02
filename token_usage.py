"""
Tiny helpers to extract and accumulate OpenAI-compatible token usage
(prompt_tokens, completion_tokens, total_tokens) across pipeline calls.
Pure functions only — no shared state, so callers stay thread-safety-free
as long as they aggregate results in the main thread (as the pipeline does).
"""


def zero() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def extract(response) -> dict:
    """Pull usage out of a chat.completions.create() response, defaulting to zero."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return zero()
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
