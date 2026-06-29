"""
Robust JSON parsing for LLM outputs that may contain LaTeX backslashes.
"""
import json
import re


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
        # Fix invalid backslash escapes: replace \x (where x is not a valid JSON escape)
        # Valid JSON escapes: \" \\ \/ \b \f \n \r \t \uXXXX
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
        return json.loads(fixed)
