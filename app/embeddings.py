"""Embedding client — Ollama-compatible (OpenAI /v1/embeddings format)."""

import os
from typing import List

import httpx

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://host.docker.internal:11434/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using Ollama-compatible /v1/embeddings API."""
    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        chunk = texts[i : i + EMBEDDING_BATCH_SIZE]
        # Ollama processes one at a time more reliably than batches
        for text in chunk:
            for attempt in range(3):
                try:
                    resp = httpx.post(
                        f"{EMBEDDING_BASE_URL}/embeddings",
                        json={"model": EMBEDDING_MODEL, "input": [text]},
                        timeout=120.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()["data"]
                    all_embeddings.append(data[0]["embedding"])
                    break
                except (httpx.HTTPError, KeyError) as exc:
                    if attempt == 2:
                        raise RuntimeError(f"Embedding failed after 3 attempts: {exc}") from exc
                    import time
                    time.sleep(2**attempt)
    return all_embeddings


def embed_single(text: str) -> List[float]:
    """Embed a single text string."""
    return embed_texts([text])[0]
