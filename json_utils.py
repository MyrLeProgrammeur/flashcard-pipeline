"""
Robust JSON parsing for LLM outputs that may contain LaTeX backslashes.
"""
import json
import re

from json_repair import repair_json


def parse_json_response(raw: str) -> dict | list:
    """
    Parse JSON from an LLM response, handling common issues:
    - Markdown code fences (```json ... ```)
    - Invalid backslash escapes from LaTeX (e.g. \alpha, \frac)
    """
    text = raw.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix invalid backslash escapes: replace \x with \\x unless \x is a genuine
    # JSON escape. A backslash is left alone only when it is:
    #   - a structural escape: \" \\ \/
    #   - one of \b \f \n \r \t NOT followed by a letter (a real control escape,
    #     not the start of a LaTeX command like \nu, \tau, \beta)
    #   - \uXXXX with exactly 4 hex digits (real unicode escape)
    # Everything else (LaTeX commands such as \frac, \alpha, \sigma, \upsilon,
    # \( ...) gets its backslash doubled so it survives as a literal backslash.
    try:
        fixed = re.sub(r'\\(?!["\\/]|[bfnrt](?![A-Za-z])|u[0-9A-Fa-f]{4})', r'\\\\', text)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: json-repair handles malformed LLM JSON (bad escapes, LaTeX,
    # truncation, etc.) that the regex heuristic above can't fix on its own
    # (e.g. mixed clean/broken escapes in the same payload).
    try:
        result = repair_json(text, return_objects=True)
    except Exception as exc:
        raise ValueError(
            f"parse_json_response: all fallbacks failed (json.loads, regex fix, "
            f"json_repair) on text starting with: {text[:200]!r}"
        ) from exc

    if result in ("", {}, []) and text.strip() not in ("", "{}", "[]"):
        raise ValueError(
            f"parse_json_response: json_repair returned empty result for non-empty "
            f"text starting with: {text[:200]!r}"
        )

    return result
