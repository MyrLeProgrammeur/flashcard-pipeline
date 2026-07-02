"""
Builder agent: generates flashcards from a theme's content.
Produces two card types: RECALL (memorization) and PROBLEM (reasoning/calculation).
All output in English.
"""
import json

from openai import OpenAI

from json_utils import parse_json_response

RECALL_SYSTEM_PROMPT = """You are an expert in spaced repetition pedagogy for graduate-level mathematics and machine learning.

Your task: create high-quality RECALL flashcards from the provided concepts of a math/ML/stats course.

Rules:
- Each question targets ONE specific concept, definition, theorem, or formula.
- Answers must be concise (1–4 lines), self-contained, and work out of context.
- Assume the reader has solid undergraduate math background (linear algebra, calculus, probability).
- Do NOT ask "what is X" if X has too broad an answer — prefer "State the definition of X", "What are the conditions for X", "What does the Y theorem say about X".
- Vary formats: definition, statement of theorem, key formula, crucial distinction between two concepts, "why does X hold".
- Generate 5–15 cards depending on content richness.
- Avoid duplicating any of the existing questions listed.
- Math notation: whenever a card's question, answer, or note contains ANY mathematical notation — a variable, a function like f(x), a Greek letter, a sub/superscript (e.g. sigma^2), a sum, a fraction, an operator, or a full formula, however trivial — you MUST wrap it in LaTeX. Never write math as plain text. Use $...$ for inline math and $$...$$ for standalone display formulas.

Output ONLY valid JSON, no markdown:
{
  "flashcards": [
    {"question": "string", "answer": "string", "note": "string"}
  ]
}

The "note" field is optional — use it for an example, a mnemonic, or a precision (can be empty "").
Language: English only."""


PROBLEM_SYSTEM_PROMPT = """You are an expert in spaced repetition pedagogy for graduate-level mathematics and machine learning.

Your task: create PROBLEM-TYPE flashcards from the provided exercise patterns of a math/ML/stats course.

These cards are NOT about memorization — they are reminders of PROBLEM TYPES that require pen-and-paper calculation or proof.

Rules:
- The question describes a PROBLEM TYPE or TECHNIQUE (not a specific numerical instance): e.g., "How do you construct a confidence interval for the mean of a Gamma(α, β) distribution using a pivot?".
- The answer describes the METHOD and KEY STEPS: what pivot to use, what theorem to invoke, what the structure of the solution looks like. It does NOT give a full numerical answer.
- Include in "note" any key formulas or results needed (e.g., "Recall: 2nX̄/β ~ χ²(2n)").
- These cards tell the student "I need to know how to solve this CLASS of problem" — not just recall a fact.
- Generate 3–8 cards depending on the number of distinct problem types.
- Avoid duplicating any of the existing questions listed.
- Math notation: whenever a card's question, answer, or note contains ANY mathematical notation — a variable, a function like f(x), a Greek letter, a sub/superscript (e.g. sigma^2), a sum, a fraction, an operator, or a full formula, however trivial — you MUST wrap it in LaTeX. Never write math as plain text. Use $...$ for inline math and $$...$$ for standalone display formulas.

Output ONLY valid JSON, no markdown:
{
  "flashcards": [
    {"question": "string", "answer": "string", "note": "string"}
  ]
}

Language: English only."""


def build_recall_flashcards(
    client: OpenAI,
    model: str,
    subject: str,
    theme: str,
    recall_concepts: list[str],
    existing_questions: list[str],
) -> list[dict]:
    existing_section = ""
    if existing_questions:
        existing_section = f"\nAlready existing questions for this theme (DO NOT duplicate):\n{json.dumps(existing_questions[:30], ensure_ascii=False)}\n"

    prompt = f"""Subject: {subject}
Theme: {theme}

Concepts to cover:
{chr(10).join(f"- {c}" for c in recall_concepts)}
{existing_section}
Generate RECALL flashcards."""

    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": RECALL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return parse_json_response(response.choices[0].message.content.strip()).get("flashcards", [])


def build_problem_flashcards(
    client: OpenAI,
    model: str,
    subject: str,
    theme: str,
    problem_types: list[str],
    existing_questions: list[str],
) -> list[dict]:
    if not problem_types:
        return []

    existing_section = ""
    if existing_questions:
        existing_section = f"\nAlready existing problem questions for this theme (DO NOT duplicate):\n{json.dumps(existing_questions[:20], ensure_ascii=False)}\n"

    prompt = f"""Subject: {subject}
Theme: {theme}

Problem types / exercise patterns to cover:
{chr(10).join(f"- {p}" for p in problem_types)}
{existing_section}
Generate PROBLEM-TYPE flashcards."""

    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": PROBLEM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return parse_json_response(response.choices[0].message.content.strip()).get("flashcards", [])
