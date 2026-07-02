import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from json_utils import parse_json_response


def test_latex_backslashes_survive_parsing():
    payload = r'''
    {
        "cards": [
            {
                "question": "Compute \frac{a}{b} where \alpha is the angle.",
                "answer": "Variance is \sigma^2, and \(\nu\) is degrees of freedom. Also \upsilon and \beta."
            }
        ]
    }
    '''
    result = parse_json_response(payload)
    question = result["cards"][0]["question"]
    answer = result["cards"][0]["answer"]

    assert "\\frac" in question
    assert "\\alpha" in question
    assert "\\sigma" in answer
    assert "\\nu" in answer
    assert "\\upsilon" in answer
    assert "\\beta" in answer

    # Must not have been corrupted into control characters.
    assert "\f" not in question
    assert "\b" not in answer
    assert "\t" not in answer
    assert "\r" not in answer


def test_clean_json_with_genuine_control_escape_still_parses():
    payload = '{"a": "line1\\nline2"}'
    result = parse_json_response(payload)
    assert result["a"] == "line1\nline2"


def test_markdown_fenced_json_still_parses():
    payload = '```json\n{"a": 1, "b": [1, 2, 3]}\n```'
    result = parse_json_response(payload)
    assert result == {"a": 1, "b": [1, 2, 3]}


def test_json_repair_fallback_handles_latex_math_that_breaks_regex_fix():
    # Reproduces the real "problems" batch failure: $...$ / $$...$$ math mixed
    # with a stray doubled backslash (e.g. a LaTeX matrix line-break "\\\\")
    # that the regex-escape-fix still turns into an invalid escape, so
    # json.loads keeps raising "Invalid \escape" even after that fallback.
    payload = (
        r'{"question": "Solve $\frac{1}{n}\sum x_i$", '
        r'"answer": "Note $$\hat\sigma^2$$ and matrix row \\\\ next"}'
    )
    result = parse_json_response(payload)

    assert r"\frac{1}{n}\sum x_i" in result["question"]
    assert r"\hat\sigma^2" in result["answer"]
