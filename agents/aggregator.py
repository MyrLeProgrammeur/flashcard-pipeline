"""
Aggregator agent : fusionne les thèmes proposés par l'analyst avec le registre
existant. Priorité absolue : réutiliser un thème existant plutôt qu'en créer un nouveau.
"""
import json

from openai import OpenAI

import token_usage
from json_utils import parse_json_response

SYSTEM_PROMPT = """You are a taxonomy manager for educational content.

Your task: resolve proposed themes against a registry of existing themes.

MAIN rule (non-negotiable):
- If a proposed theme matches an existing theme (same meaning, same domain, slightly different wording), use the EXISTING theme.
- Only create a NEW theme if the content is clearly distinct from all existing themes.
- Prefer broadening an existing theme over fragmenting it into new ones.
- Maximum 2 new themes created per call, unless absolutely necessary.
- Canonical theme names MUST be in English only.

Merge AGGRESSIVELY:
- Two proposed themes (or a proposed theme and an existing one) that describe the SAME underlying topic under different phrasing MUST be merged into ONE canonical theme, even if the wording, scope, or emphasis differs noticeably.
- Judge by underlying topic, not by surface wording. A theme that is a specific angle, sub-case, or restatement of a broader existing theme is an ALIAS of that theme, not a new one.
- Examples of same-topic merges you MUST perform:
  - "Markov Processes" + "Markov Property and Order in Time-Series Models" → ONE canonical (e.g. "Markov Processes"), the second is an alias.
  - "Stationarity and Second-Order Properties" + "Stationarity and Unit Roots" → ONE canonical (e.g. "Stationarity"), the second is an alias.
  - "Thermodynamics" + existing "Thermo" → use "Thermo"
  - "Partial derivatives" + existing "Differential calculus" → use "Differential calculus"
  - "Introduction to law" + existing "General law" → use "General law"
- Target roughly 8-12 canonical themes total for a full course/subject. If your resolution would leave noticeably more than that, look again for near-duplicates you missed and merge them.

Do NOT under-merge, but do NOT over-merge either:
- Only keep two themes separate if they cover genuinely distinct topics a student would study separately (not just distinct wording of the same topic).
- When in doubt between merging and keeping separate, prefer merging if both themes would share the majority of their recall content.

HARD coverage rule (non-negotiable):
- EVERY theme in "Themes proposed by the new document" MUST appear exactly once, either as an alias listed under some canonical theme in "resolved", or as an entry in "new_themes". Do not omit any proposed theme — omitting one is a bug. Do not silently drop a proposed theme just because you are unsure where it fits: pick your best canonical (existing or new) and list it there.

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
    result = parse_json_response(raw)
    result["_usage"] = token_usage.extract(response)
    return result
