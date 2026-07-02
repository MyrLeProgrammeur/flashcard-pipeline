"""
Aggregator agent : fusionne les thèmes proposés par l'analyst avec le registre
existant. Priorité absolue : réutiliser un thème existant plutôt qu'en créer un nouveau.
"""
import json

from openai import OpenAI

from json_utils import parse_json_response

SYSTEM_PROMPT = """You are a taxonomy manager for educational content.

Your task: resolve proposed themes against a registry of existing themes.

MAIN rule (non-negotiable):
- If a proposed theme matches an existing theme (same meaning, same domain, slightly different wording), use the EXISTING theme.
- Only create a NEW theme if the content is clearly distinct from all existing themes.
- Prefer broadening an existing theme over fragmenting it into new ones.
- Maximum 2 new themes created per call, unless absolutely necessary.
- Canonical theme names MUST be in English only.

Do NOT over-merge:
- Merge only near-identical themes (same concept, trivially different wording).
- Keep distinct chapters/topics as distinct themes, even within the same broad domain.
- When in doubt between merging and keeping separate, keep the granularity stable — do not collapse multiple distinct topics into one just because they are related.

Examples of expected fusions:
- "Thermodynamics" + existing "Thermo" → use "Thermo"
- "Partial derivatives" + existing "Differential calculus" → use "Differential calculus"
- "Introduction to law" + existing "General law" → use "General law"

Respond ONLY in valid JSON, no markdown:
{
  "resolved": {
    "canonical_theme_name": ["proposed_alias_1", "proposed_alias_2"]
  },
  "new_themes": ["truly_new_theme"]
}"""


def aggregate_themes(
    client: OpenAI,
    model: str,
    subject: str,
    existing_themes: list[str],
    proposed_themes: list[str],
) -> dict:
    """
    Retourne: { "resolved": {canonical: [aliases]}, "new_themes": [str] }
    """
    prompt = f"""Subject: {subject}

Existing themes in the registry:
{json.dumps(existing_themes, ensure_ascii=False) if existing_themes else "[] (none yet)"}

Themes proposed by the new document:
{json.dumps(proposed_themes, ensure_ascii=False)}

Resolve each proposed theme against the existing themes."""

    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()
    return parse_json_response(raw)
