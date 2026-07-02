"""
Analyst agent: reads a DocumentGroup (lecture + annotated, or TD + corrected)
and extracts structured concepts and exercises. Always outputs in English.
"""
from pathlib import Path

from openai import OpenAI

from json_utils import parse_json_response

SYSTEM_PROMPT = """You are an expert mathematical and scientific teaching assistant analyzing graduate-level course materials (M1/M2 level).

You will receive one or more documents belonging to the same course unit — for example:
- A base lecture + its annotated version (same content, annotations add extra insight)
- A problem set (TD) + its corrected version (same exercises, corrections show the solution method)

Your task:
1. Treat related documents as a SINGLE source. Do NOT generate duplicate content across them.
   - Annotated lecture = same as base lecture, but richer. Merge annotations into the base concepts.
   - Corrected TD = same exercises as the TD, but with solutions. Use the solutions to enrich exercise descriptions.
2. Identify the SUBJECT (e.g., "Foundations of Machine Learning", "Martingales", "Reinforcement Learning").
3. Extract 2–6 THEMES representing the key chapters/concepts of the material. Themes must be generic and reusable across multiple documents (e.g., "Confidence Intervals", "Hypothesis Testing", "PAC Learning").
4. For each theme, extract:
   - RECALL content: definitions, theorems, properties, key formulas, important results — things to memorize.
   - PROBLEM content: exercise types/patterns that require calculation or proof on paper. Describe the problem TYPE (e.g., "Construct a CI for a Gamma-distributed sample using a pivot"), not a specific numerical instance.

Output ONLY valid JSON, no markdown:
{
  "subject": "string",
  "themes": [
    {
      "name": "string",
      "recall_concepts": ["string", ...],
      "problem_types": ["string", ...]
    }
  ]
}

Language: always English, regardless of the document language."""


def analyze_group(
    client: OpenAI,
    model: str,
    documents: dict[str, tuple[Path, str]],
) -> dict:
    """
    documents: { doc_type: (filepath, content) }
    doc_type in: lecture, lecture_annotated, td, td_corrected

    Returns: { "subject": str, "themes": [{"name": str, "recall_concepts": [...], "problem_types": [...]}] }
    """
    parts = []
    for doc_type, (filepath, content) in documents.items():
        label = {
            "lecture": "BASE LECTURE NOTES",
            "lecture_annotated": "ANNOTATED LECTURE NOTES (same content as base, with extra student annotations)",
            "td": "PROBLEM SET (TD)",
            "td_corrected": "CORRECTED PROBLEM SET (solutions to the TD above)",
        }.get(doc_type, doc_type.upper())

        parts.append(f"=== {label} — {filepath.name} ===\n{content[:8000]}")

    prompt = "\n\n".join(parts)

    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()
    return parse_json_response(raw)
