"""
Semantic de-duplication of generated flashcards.

Runs on the PC (pipeline side): local embeddings (zero API cost) find candidate
near-duplicate pairs (e.g. the same notion generated from a lecture + its exam),
then a single cheap LLM call per candidate pair confirms whether they are truly
redundant before dropping one. Never crashes the pipeline — any failure in the
embedding stack or the LLM call falls back to "no dedup" (cards kept as-is).
"""
import logging

import numpy as np
from openai import OpenAI

from json_utils import parse_json_response

log = logging.getLogger(__name__)

_EMBED_MODEL_FASTEMBED = "BAAI/bge-small-en-v1.5"
_EMBED_MODEL_ST = "all-MiniLM-L6-v2"

TIE_BREAK_SYSTEM_PROMPT = """You compare two flashcards from a spaced-repetition deck.

Your task: decide if they are REDUNDANT — i.e. they test the exact same piece of \
knowledge, so a student who can answer one gains nothing from also reviewing the \
other.

Two cards are REDUNDANT only if they target the same specific fact, definition, \
formula, or problem-solving technique. Two cards that merely share vocabulary or \
topic, but probe a different angle, a different condition, or a different step, are \
NOT redundant — keep both.

Respond ONLY with valid JSON, no markdown:
{"redundant": true or false}"""


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts locally. Tries fastembed (ONNX, no torch) first, falls back to
    sentence-transformers. Raises on failure — caller handles the fallback."""
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=_EMBED_MODEL_FASTEMBED)
        return np.array(list(model.embed(texts)))
    except ImportError:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(_EMBED_MODEL_ST)
        return np.array(model.encode(texts))


def _cosine_sim_matrix(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1e-8
    normalized = embeddings / norms
    return normalized @ normalized.T


def _card_text(card: dict) -> str:
    return f"{card.get('question', '')} {card.get('answer', '')}".strip()


def _llm_confirms_redundant(client: OpenAI, model: str, card_a: dict, card_b: dict) -> bool:
    prompt = f"""Card A:
Question: {card_a.get('question', '')}
Answer: {card_a.get('answer', '')}

Card B:
Question: {card_b.get('question', '')}
Answer: {card_b.get('answer', '')}

Are these two cards redundant?"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=64,
        messages=[
            {"role": "system", "content": TIE_BREAK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    result = parse_json_response(response.choices[0].message.content.strip())
    return bool(result.get("redundant", False))


def deduplicate_cards(
    cards: list[dict], client: OpenAI, model: str, threshold: float = 0.88
) -> tuple[list[dict], int]:
    """
    Remove near-duplicate flashcards.

    1. Embed each card locally (question + answer) — zero API cost.
    2. Flag pairs with cosine similarity >= threshold as candidates.
    3. For each candidate pair, ask a cheap LLM call to confirm true redundancy.
    4. Within a confirmed-redundant cluster, keep the first card, drop the rest.

    Never raises: any failure (missing embedding lib, model error, LLM call error)
    is logged as a warning and returns (cards, 0) — no dedup rather than data loss.
    """
    if len(cards) < 2:
        return cards, 0

    try:
        texts = [_card_text(c) for c in cards]
        embeddings = _embed_texts(texts)
        sims = _cosine_sim_matrix(embeddings)

        n = len(cards)
        dropped: set[int] = set()

        for i in range(n):
            if i in dropped:
                continue
            for j in range(i + 1, n):
                if j in dropped:
                    continue
                if sims[i, j] < threshold:
                    continue
                try:
                    if _llm_confirms_redundant(client, model, cards[i], cards[j]):
                        dropped.add(j)
                except Exception as e:
                    log.warning(f"Dedup tie-break call failed for pair ({i}, {j}): {e}")
                    continue

        if not dropped:
            return cards, 0

        kept = [c for idx, c in enumerate(cards) if idx not in dropped]
        return kept, len(dropped)

    except Exception as e:
        log.warning(f"Dedup skipped (embedding/model failure): {e}")
        return cards, 0
