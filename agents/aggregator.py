"""
Aggregator agent : fusionne les thèmes proposés par l'analyst avec le registre
existant. Priorité absolue : réutiliser un thème existant plutôt qu'en créer un nouveau.
"""
import json

from openai import OpenAI

from json_utils import parse_json_response

SYSTEM_PROMPT = """Tu es un gestionnaire de taxonomie pédagogique.

Ta tâche : résoudre des thèmes proposés contre un registre de thèmes existants.

Règle PRINCIPALE (non négociable) :
- Si un thème proposé correspond à un thème existant (même sens, même domaine, formulation légèrement différente), utilise le thème EXISTANT.
- Ne crée un NOUVEAU thème que si le contenu est clairement distinct de tous les thèmes existants.
- Préfère élargir un thème existant plutôt qu'en fragmenter en nouveaux.
- Maximum 2 nouveaux thèmes créés par appel, sauf si absolument nécessaire.

Exemples de fusions attendues :
- "Thermodynamique" + existant "Thermo" → utiliser "Thermo"
- "Dérivées partielles" + existant "Calcul différentiel" → utiliser "Calcul différentiel"
- "Introduction au droit" + existant "Droit général" → utiliser "Droit général"

Réponds UNIQUEMENT en JSON valide, sans markdown :
{
  "resolved": {
    "nom_theme_canonique": ["alias_propose_1", "alias_propose_2"]
  },
  "new_themes": ["theme_vraiment_nouveau"]
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
    prompt = f"""Matière : {subject}

Thèmes existants dans le registre :
{json.dumps(existing_themes, ensure_ascii=False) if existing_themes else "[] (aucun pour l'instant)"}

Thèmes proposés par le nouvel document :
{json.dumps(proposed_themes, ensure_ascii=False)}

Résous chaque thème proposé contre les thèmes existants."""

    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()
    return parse_json_response(raw)
